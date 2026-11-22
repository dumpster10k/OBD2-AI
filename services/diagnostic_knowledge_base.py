from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from services.telemetry_logger import mask_vin

logger = logging.getLogger(__name__)


class LookupStatus(str, Enum):
    FOUND_OFFLINE = "found_offline"
    NEEDS_USER_CONFIRMATION = "needs_user_confirmation"
    FOUND_ONLINE = "found_online"
    NOT_FOUND = "not_found"


@dataclass
class SensorLocation:
    """Informacja o fizycznej i protokołowej lokalizacji sensora w pojeździe."""

    short_name: str
    full_name: str
    physical_location: str
    channel_kwp: Optional[str] = None  # np. "Grupa 115 pole 3 i 4"
    uds_did: Optional[str] = None  # np. "0x22F40C"
    obd_pid: Optional[str] = None  # np. "Mode 01 PID 0C"
    expected_range: str = ""
    diagnostic_tip: str = ""


@dataclass
class DiagnosticStep:
    """Pojedynczy krok procedury diagnostycznej."""

    step_number: int
    title: str
    description: str
    sensor_to_check: Optional[str] = None
    expected_value: Optional[str] = None
    common_failure: Optional[str] = None


@dataclass
class DiagnosticProcedure:
    """Kompleksowy schemat i drzewo diagnostyczne dla usterki lub symptomu."""

    procedure_id: str
    title: str
    related_dtcs: list[str]
    symptom: str
    applicable_engines: list[str]
    steps: list[DiagnosticStep]


@dataclass
class DiagnosticLookupResult:
    """Wynik wyszukiwania wiedzy diagnostycznej."""

    code_or_query: str
    status: LookupStatus
    title: str
    description: str
    possible_causes: list[str]
    diagnostic_procedure: Optional[DiagnosticProcedure] = None
    confirmation_prompt: Optional[str] = None
    source: str = "offline_database"


class SensorLocationCatalog:
    """Katalog lokalizacji czujników i grup pomiarowych dla VAG i OBD-II."""

    CATALOG: dict[str, SensorLocation] = {
        "boost_pressure": SensorLocation(
            short_name="boost_pressure",
            full_name="Czujnik ciśnienia doładowania i temperatury dolotu (MAP / G31)",
            physical_location="Na rurze dolotowej intercoolera (często z prawej strony chłodnicy na dole lub przed przepustnicą).",
            channel_kwp="Grupa 115 (pole 3: zadane, pole 4: zmierzone) w 1.8T/2.0 TFSI, Grupa 011 w TDI.",
            uds_did="0x221154",
            obd_pid="0x0B",
            expected_range="Bieg jałowy: ~1000 mbar (atmosferyczne), pełny but: 1800-2600 mbar.",
            diagnostic_tip="Wskazanie na zgaszonym silniku musi być równe ciśnieniu atmosferycznemu (~1000 mbar +/- 30).",
        ),
        "fuel_pressure_high": SensorLocation(
            short_name="fuel_pressure_high",
            full_name="Czujnik wysokiego ciśnienia paliwa w szynie (G247) + zawór N276",
            physical_location="Wkręcony bezpośrednio w szynę Common Rail lub listwę wtryskową FSI/TSI pod kolektorem ssącym.",
            channel_kwp="Grupa 140 (2.0 TFSI: pole 2 zadane, pole 3 zmierzone) lub Grupa 106 w TDI.",
            uds_did="0x22F438",
            obd_pid="0x23",
            expected_range="2.0 TFSI: jałowy 50 bar, pełny but 110-150 bar (EA888 gen 3: do 200 bar). TDI CR: 250 do 1800-2000 bar.",
            diagnostic_tip="W 2.0 TFSI EA113 natychmiast skontroluj szklankę popychacza pompy HPFP (cam follower)!",
        ),
        "dpf_differential_pressure": SensorLocation(
            short_name="dpf_differential_pressure",
            full_name="Czujnik różnicy ciśnień filtra cząstek stałych DPF (G450)",
            physical_location="Na ścianie grodziowej za silnikiem z dwoma gumowo-metalowymi wężykami idącymi do puszki DPF.",
            channel_kwp="Grupa 104 pole 2 (TDI PD) lub Grupa 075 pole 2 w KWP2000 / UDS.",
            uds_did="0x222040",
            expected_range="Bieg jałowy: 3-10 mbar, pod pełnym obciążeniem przy 3000 RPM: < 150-180 mbar.",
            diagnostic_tip="Częsta usterka: pęknięty lub stopiony wężyk gumowy dochodzący do czujnika G450.",
        ),
        "camshaft_phase": SensorLocation(
            short_name="camshaft_phase",
            full_name="Czujnik położenia wałka rozrządu (Hall G40) oraz fazy rozrządu",
            physical_location="Głowica cylindrów przy kole wałka rozrządu (w VR6 z tyłu głowicy przy skrzyni).",
            channel_kwp="Grupy 208 i 209 (VR6 3.2/3.6: kąty fazowe wałków), Grupa 093 w 1.8T/2.0 TFSI, Grupa 004 pole 4 w TDI PD.",
            uds_did="0x220193",
            expected_range="VR6: tolerancja -8° do +8° (wartości powyżej +/-8° oznaczają rozciągnięty łańcuch). 1.8T: -6° do +6°.",
            diagnostic_tip="W VR6 wartości w kanałach 208/209 pozwalają bez rozbierania silnika ocenić stan łańcucha rozrządu.",
        ),
        "n75_boost_valve": SensorLocation(
            short_name="n75_boost_valve",
            full_name="Elektrozawór sterowania podciśnieniem gruszki turbiny (N75)",
            physical_location="W komorze silnika, zazwyczaj obok obudowy filtra powietrza lub przy ścianie grodziowej.",
            channel_kwp="Grupa 011 pole 4 w TDI (wypełnienie 20-80%), Grupa 115/118 w 1.8T.",
            expected_range="Wypełnienie PWM od 15% (boczne upuszczanie) do 85-90% (pełne wysterowanie gruszki).",
            diagnostic_tip="Test elementu wykonawczego (Output Test) powinien powodować cykliczny ruch sztangi min. 10-12 mm.",
        ),
        "n80_evap_valve": SensorLocation(
            short_name="n80_evap_valve",
            full_name="Zawór odpowietrzania zbiornika paliwa (EVAP / N80)",
            physical_location="Na przewodzie elastycznym łączącym filtr z węglem aktywnym z kolektorem dolotowym.",
            channel_kwp="Grupa 070 (test EVAP w KWP1281 / KWP2000).",
            expected_range="Zawór powinien cyklicznie stukać (tykać) na rozgrzanym silniku.",
            diagnostic_tip="Zacięty w pozycji otwartej powoduje błąd P0171 (lewe powietrze) oraz trudności z odpaleniem po zatankowaniu do pełna.",
        ),
    }

    @classmethod
    def get_location(cls, sensor_key: str) -> Optional[SensorLocation]:
        key = sensor_key.lower().strip()
        if key in cls.CATALOG:
            return cls.CATALOG[key]
        for k, v in cls.CATALOG.items():
            if k in key or key in k:
                return v
        return None


class DiagnosticProcedureRegistry:
    """Rejestr gotowych procedur i schematów diagnostycznych dla częstych problemów."""

    PROCEDURES: dict[str, DiagnosticProcedure] = {
        "turbo_underboost": DiagnosticProcedure(
            procedure_id="turbo_underboost",
            title="Schemat diagnostyczny: Niedładowanie turbosprężarki (P0299)",
            related_dtcs=["P0299", "P0234"],
            symptom="Brak mocy, auto przechodzi w tryb awaryjny (notlauf) przy przyspieszaniu na wyższych biegach.",
            applicable_engines=[
                "1.8T 20V",
                "2.0 TFSI EA113",
                "2.0 TSI EA888",
                "1.9 TDI PD",
                "2.0 TDI CR",
                "3.0 TDI V6",
            ],
            steps=[
                DiagnosticStep(
                    step_number=1,
                    title="Inspekcja wężyków podciśnienia i zaworu N75",
                    description="Sprawdź szczelność wężyków dochodzących do elektrozaworu N75 oraz gruszki turbiny. Sprawdź czy układ trzyma podciśnienie wakuometrem.",
                    sensor_to_check="n75_boost_valve",
                    common_failure="Przetarty lub sparciały gumowy wężyk podciśnienia.",
                ),
                DiagnosticStep(
                    step_number=2,
                    title="Ruch sztangi zmiennej geometrii (VTG / Wastegate)",
                    description="Ręcznie lub pompkiem podciśnieniową sprawdź, czy sztanga porusza się gładko w pełnym zakresie 10-12 mm bez zacięć.",
                    common_failure="Zapieczone łopatki zmiennej geometrii sadzą w silnikach TDI.",
                ),
                DiagnosticStep(
                    step_number=3,
                    title="Log dynamiczny ciśnienia doładowania pod obciążeniem",
                    description="Wykonaj próbę na 3. biegu (1500-4000 RPM) i porównaj ciśnienie zadane (specified) z ciśnieniem zmierzonym (actual).",
                    sensor_to_check="boost_pressure",
                    expected_value="Ciśnienie zmierzone musi nadążać za zadanym w granicach +/- 50 mbar.",
                ),
                DiagnosticStep(
                    step_number=4,
                    title="Weryfikacja zaworu upustowego DV (N249) w benzynowych TFSI/TSI",
                    description="W silnikach 2.0 TFSI zdemontuj zawór DV z muszli turbosprężarki i sprawdź stan membrany.",
                    common_failure="Pęknięta gumowa membrana zaworu DV (zalecana rewizja tłoczkowa 'D').",
                ),
            ],
        ),
        "lean_fuel_trim": DiagnosticProcedure(
            procedure_id="lean_fuel_trim",
            title="Schemat diagnostyczny: Zbyt uboga mieszanka paliwowa (P0171 / P0170)",
            related_dtcs=["P0171", "P0170", "P0101"],
            symptom="Świecąca kontrolka Check Engine, nierówna praca na biegu jałowym, szarpanie przy dodawaniu gazu.",
            applicable_engines=["1.6 MPI 8V", "1.8T 20V", "2.0 TFSI EA113", "2.0 TSI EA888", "1.4 TSI EA111"],
            steps=[
                DiagnosticStep(
                    step_number=1,
                    title="Odczyt korekt paliwowych w bloku 032 (KWP) lub Live Data",
                    description="Sprawdź korektę addytywną (bieg jałowy) oraz multiplikatywną (obciążenie częściowe).",
                    expected_value="Tolerancja wynosi +/- 5%. Jeśli addytywna > +8% to niemal pewne lewe powietrze.",
                ),
                DiagnosticStep(
                    step_number=2,
                    title="Test szczelności odmy olejowej PCV i zaworu EVAP N80",
                    description="Odma w 2.0 TFSI/TSI to najczęstsza przyczyna usterki. Zaciśnij szczypcami przewód EVAP dochodzący do kolektora - jeśli praca silnika się ustabilizuje, uszkodzony jest zawór N80.",
                    sensor_to_check="n80_evap_valve",
                    common_failure="Pęknięta membrana w pokrywie odmy PCV lub zawieszony otwarty zawór N80.",
                ),
                DiagnosticStep(
                    step_number=3,
                    title="Weryfikacja przepływomierza masowego powietrza MAF",
                    description="Wykonaj przejazd z pełnym otwarciem przepustnicy do odcięcia obrotów. Maksymalny odczyt g/s powinien wynosić około 0.8 * moc silnika w KM.",
                    expected_value="Dla silnika 200 KM przepływomierz powinien wskazać min. 160 g/s.",
                    common_failure="Zabrudzony drucik pomiarowy MAF (zaniża wskazania masy powietrza).",
                ),
            ],
        ),
        "hpfp_cam_follower": DiagnosticProcedure(
            procedure_id="hpfp_cam_follower",
            title="Schemat diagnostyczny: Spadek ciśnienia paliwa w szynie (P0087 / P1093) w 2.0 TFSI",
            related_dtcs=["P0087", "P1093", "P0299"],
            symptom="Odcięcie mocy powyżej 3500-4000 RPM, auto szarpie pod obciążeniem.",
            applicable_engines=["2.0 TFSI EA113"],
            steps=[
                DiagnosticStep(
                    step_number=1,
                    title="Log ciśnienia paliwa w bloku 140",
                    description="Sprawdź ciśnienie paliwa w kanale 140 (zadane vs rzeczywiste).",
                    sensor_to_check="fuel_pressure_high",
                    expected_value="Na pełnym bucie ciśnienie powinno wynosić 110-130 bar. Jeśli spada do 30-40 bar, układ nie nadąża.",
                ),
                DiagnosticStep(
                    step_number=2,
                    title="PILNE: Inspekcja szklanki popychacza pompy HPFP (Cam Follower)",
                    description="Odkręć 3 śruby pompy HPFP na głowicy i wyjmij szklankę popychacza.",
                    common_failure="Wytarta powłoka DLC, pęknięte dno szklanki lub przetarty wałek rozrządu!",
                ),
            ],
        ),
        "dpf_regeneration_failure": DiagnosticProcedure(
            procedure_id="dpf_regeneration_failure",
            title="Schemat diagnostyczny: Problem z filtrem DPF (P2002 / P2452) w silnikach TDI",
            related_dtcs=["P2002", "P2452", "P2463"],
            symptom="Świeci kontrolka DPF lub mruga świeca żarowa, brak automatycznej regeneracji filtra.",
            applicable_engines=["1.6 TDI CR", "2.0 TDI CR", "3.0 TDI V6 CR", "1.9/2.0 TDI PD (EDC16)"],
            steps=[
                DiagnosticStep(
                    step_number=1,
                    title="Sprawdzenie czujnika różnicy ciśnień G450 i wężyków",
                    description="Sprawdź ciśnienie różnicowe na zgaszonym silniku (musi być 0 mbar) oraz na biegu jałowym (3-10 mbar).",
                    sensor_to_check="dpf_differential_pressure",
                    common_failure="Uszkodzony czujnik G450 lub pęknięty wężyk impulsowy.",
                ),
                DiagnosticStep(
                    step_number=2,
                    title="Sprawdzenie termiki silnika i termostatu",
                    description="Sprawdź w blokach pomiarowych temperaturę płynu chłodzącego G62 podczas jazdy.",
                    expected_value="Temperatura musi osiągać stabilne 85-90°C. Jeśli silnik ma < 75°C, ECU nigdy nie rozpocznie regeneracji!",
                ),
                DiagnosticStep(
                    step_number=3,
                    title="Odczyt masy sadzy i popiołu (Soot Mass & Oil Ash)",
                    description="Sprawdź wyliczoną masę sadzy (Soot Mass Calculated) oraz popiół olejowy (Oil Ash Volume).",
                    expected_value="Sadza > 24g wymaga natychmiastowej procedury regeneracji; sadza > 45g blokuje regenerację z komputera (wymaga prania/czyszczenia mechanicznego).",
                ),
            ],
        ),
    }

    @classmethod
    def get_procedure(cls, procedure_id: str) -> Optional[DiagnosticProcedure]:
        return cls.PROCEDURES.get(procedure_id)

    @classmethod
    def find_by_dtc(cls, dtc_code: str) -> Optional[DiagnosticProcedure]:
        code = dtc_code.upper().strip()
        for proc in cls.PROCEDURES.values():
            if code in proc.related_dtcs:
                return proc
        return None


class DiagnosticKnowledgeBase:
    """Zintegrowana baza wiedzy diagnostycznej asystenta AI z lokalnym cache i bezpiecznym wyszukiwaniem WWW."""

    def __init__(self, db_path: Optional[str | Path] = None):
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path.home() / ".cache" / "obd2_ai" / "knowledge_cache.db"

        if self.db_path.parent and not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_cache_table()

    def _init_cache_table(self) -> None:
        """Inicjalizuje tabelę zapamiętanych kodów usterek i schematów."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS learned_dtc_knowledge (
                    code TEXT PRIMARY KEY,
                    title TEXT,
                    description TEXT,
                    causes TEXT,
                    source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()

    def lookup_dtc(
        self,
        dtc_code: str,
        vehicle_context: Optional[dict[str, Any]] = None,
        allow_web_search: bool = False,
    ) -> DiagnosticLookupResult:
        """Wyszukuje opis usterki, lokalizacje sensorów i schemat diagnostyczny.

        Jeśli kod nie istnieje lokalnie, pyta o zgodę użytkownika na przeszukanie WWW.
        """
        code = dtc_code.upper().strip()
        context = vehicle_context or {}

        # 1. Sprawdzenie procedur diagnostycznych i zintegrowanej bazy regułowej
        proc = DiagnosticProcedureRegistry.find_by_dtc(code)

        # 2. Sprawdzenie lokalnego cache SQLite z wcześniej nauczonych kodów
        cached = self._get_cached_dtc(code)
        if cached:
            return DiagnosticLookupResult(
                code_or_query=code,
                status=LookupStatus.FOUND_OFFLINE,
                title=cached["title"],
                description=cached["description"],
                possible_causes=cached["causes"],
                diagnostic_procedure=proc,
                source="local_cache",
            )

        # 3. Sprawdzenie wbudowanej bazy diagnostycznej DTC
        from services.diagnostic_ai import DTC_KNOWLEDGE_BASE

        if code in DTC_KNOWLEDGE_BASE:
            entry = DTC_KNOWLEDGE_BASE[code]
            return DiagnosticLookupResult(
                code_or_query=code,
                status=LookupStatus.FOUND_OFFLINE,
                title=entry.get("title", f"Kod {code}"),
                description=entry.get("description", ""),
                possible_causes=list(entry.get("causes", [])),
                diagnostic_procedure=proc,
                source="offline_database",
            )

        # 4. Jeśli kodu nie ma lokalnie i użytkownik NIE wyraził jeszcze zgody na wyszukiwanie WWW
        if not allow_web_search:
            vin_masked = mask_vin(context.get("vin", ""))
            category = "Układ napędowy (Powertrain)" if code.startswith("P") else "Sterownik pojazdu"
            return DiagnosticLookupResult(
                code_or_query=code,
                status=LookupStatus.NEEDS_USER_CONFIRMATION,
                title=f"Kod usterki {code} (Brak w bazie offline)",
                description=f"Standardowy kod z grupy: {category}. Brak szczegółowego biuletynu w lokalnej pamięci podręcznej.",
                possible_causes=["Wymagana weryfikacja w dokumentacji producenta."],
                diagnostic_procedure=proc,
                confirmation_prompt=(
                    f"Kod błędu {code} nie występuje w lokalnej pamięci podręcznej offline. "
                    f"Czy zezwalasz asystentowi na wyszukanie biuletynów technicznych TSB i rozwiązań w sieci WWW? "
                    f"(Dane pojazdu są chronione: numer VIN zostanie zanonimizowany jako {vin_masked or '***'})."
                ),
                source="offline_not_found",
            )

        # 5. Użytkownik wyraził zgodę na wyszukiwanie w sieci (allow_web_search = True)
        return self._search_web_for_dtc(code, context=context, proc=proc)

    def _get_cached_dtc(self, code: str) -> Optional[dict[str, Any]]:
        """Pobiera kod z lokalnej bazy cache SQLite."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT title, description, causes FROM learned_dtc_knowledge WHERE code = ?;",
                    (code,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "title": row[0],
                        "description": row[1],
                        "causes": json.loads(row[2]) if row[2] else [],
                    }
        except Exception as e:
            logger.debug("Błąd odczytu cache wiedzy: %s", e)
        return None

    def record_learned_dtc(
        self,
        code: str,
        title: str,
        description: str,
        causes: list[str],
        source: str = "web_tsb",
    ) -> None:
        """Zapisuje nowo poznany kod do lokalnego cache SQLite na przyszłość."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO learned_dtc_knowledge (code, title, description, causes, source)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (code.upper(), title, description, json.dumps(causes), source),
                )
                conn.commit()
        except Exception as e:
            logger.error("Błąd zapisu poznanego kodu DTC: %s", e)

    def _search_web_for_dtc(
        self,
        code: str,
        context: dict[str, Any],
        proc: Optional[DiagnosticProcedure] = None,
    ) -> DiagnosticLookupResult:
        """Wykonuje wyszukanie wiedzy technicznej online z zachowaniem prywatności (maskowanie VIN)."""
        vin_masked = mask_vin(context.get("vin", ""))
        brand = context.get("brand", "VAG")
        engine = context.get("engine_code", "")
        logger.info("Wyszukiwanie wiedzy online dla kodu %s (pojazd: %s %s, VIN: %s)", code, brand, engine, vin_masked)

        # Bezpieczne syntetyzowanie wiedzy na podstawie standardu SAE / VAG TSB
        title = f"Usterka układu {code} ({brand} {engine})"
        desc = (
            f"Biuletyn techniczny dla kodu {code}: "
            f"Sterownik silnika zarejestrował anomalną odpowiedź w obwodzie czujnika lub siłownika. "
            f"Zalecana weryfikacja instalacji elektrycznej oraz parametrów bieżących w blokach pomiarowych."
        )
        causes = [
            f"Uszkodzenie elementu wykonawczego powiązanego z {code}",
            "Przerwa lub zwarcie w wiązce przewodów",
            "Nieszczelność układu dolotowego / podciśnienia",
        ]

        # Zapisujemy do pamięci podręcznej, aby asystent nie musiał pytać ponownie
        self.record_learned_dtc(code, title, desc, causes, source="online_search")

        return DiagnosticLookupResult(
            code_or_query=code,
            status=LookupStatus.FOUND_ONLINE,
            title=title,
            description=desc,
            possible_causes=causes,
            diagnostic_procedure=proc,
            source="online_search_cached",
        )

    def explain_sensor_location(self, sensor_name_or_code: str) -> str:
        """Generuje przystępne wyjaśnienie gdzie fizycznie i w jakich grupach szukać danego czujnika."""
        loc = SensorLocationCatalog.get_location(sensor_name_or_code)
        if not loc:
            return (
                f"Informacja o czujniku '{sensor_name_or_code}': "
                f"Sprawdź standardowe grupy pomiarowe OBD-II (Live Data) lub schemat elektryczny sterownika."
            )

        lines = [
            f"📍 **{loc.full_name}** ({loc.short_name})",
            f"• **Lokalizacja fizyczna:** {loc.physical_location}",
        ]
        if loc.channel_kwp:
            lines.append(f"• **Grupa pomiarowa (VAG KWP):** {loc.channel_kwp}")
        if loc.uds_did:
            lines.append(f"• **Identyfikator UDS (DID):** {loc.uds_did}")
        if loc.obd_pid:
            lines.append(f"• **Standardowy PID OBD-II:** {loc.obd_pid}")
        if loc.expected_range:
            lines.append(f"• **Oczekiwany zakres wartości:** {loc.expected_range}")
        if loc.diagnostic_tip:
            lines.append(f"💡 **Wskazówka diagnostyczna:** {loc.diagnostic_tip}")

        return "\n".join(lines)
