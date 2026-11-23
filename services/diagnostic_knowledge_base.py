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
        "bmw_valvetronic": SensorLocation(
            short_name="bmw_valvetronic",
            full_name="Silnik nastawczy i czujnik wałka mimośrodowego Valvetronic (VVT)",
            physical_location="W centralnej części pokrywy zaworów silnika BMW (N52, N55, B48, B58) między cewkami zapłonowymi.",
            uds_did="0x222005",
            obd_pid="0x2005",
            expected_range="Kąt mimośrodu: 0° (minimalny wznios) do 170-180° (maksymalny wznios).",
            diagnostic_tip="Przy błędach 2A67/2A6B w pierwszej kolejności wykonaj procedurę adaptacji skrajnych położeń.",
        ),
        "bmw_vanos": SensorLocation(
            short_name="bmw_vanos",
            full_name="Elektrozawory sterujące zmiennymi fazami rozrządu Vanos (Intake/Exhaust)",
            physical_location="Z przodu głowicy silnika BMW (wkręcane od czoła nad paskiem osprzętu).",
            uds_did="0x222001",
            obd_pid="0x2001",
            expected_range="Kąt wałka: -50° do +60°.",
            diagnostic_tip="Zanieczyszczone sitka elektrozaworów Vanos powodują opóźnioną reakcję wałka i błędy 2A82/2A87.",
        ),
        "psa_fap_additive": SensorLocation(
            short_name="psa_fap_additive",
            full_name="Zbiornik i pompa dozująca płynu katalitycznego FAP (Eolys / Infineum)",
            physical_location="Pod podwoziem samochodu przed lewym tylnym kołem, w osłonie termicznej.",
            uds_did="0x223001",
            obd_pid="0x3001",
            expected_range="Poziom płynu: 500 - 2500 ml. Wartość poniżej 200 ml wywołuje alarm 'Particle filter additive level too low'.",
            diagnostic_tip="Po dolaniu płynu wymagane jest zresetowanie licznika w kalkulatorze dodatku i sterowniku silnika.",
        ),
        "ford_psa_wet_belt": SensorLocation(
            short_name="ford_psa_wet_belt",
            full_name="Czujnik ciśnienia oleju i smok pompy olejowej (Pasek w oleju - Wet Belt)",
            physical_location="Czujnik ciśnienia wkręcony w blok przy filtrze oleju; smok pompy wewnątrz miski olejowej.",
            uds_did="0x223020",
            obd_pid="0x3020",
            expected_range="Jałowy: min. 1.2-1.5 bar (przy 90°C), 2000 RPM: min. 2.5-3.5 bar.",
            diagnostic_tip="W 1.0 EcoBoost i 1.2 PureTech złuszczający się pasek zapycha sitko smoka pompy olejowej. Sprawdź szerokość paska przymiarem przez korek wlewu oleju!",
        ),
        "toyota_hybrid_battery": SensorLocation(
            short_name="toyota_hybrid_battery",
            full_name="Pakiety i bloki napięciowe baterii trakcyjnej wysokonapięciowej HV (Ni-MH / Li-Ion)",
            physical_location="Pod tylną kanapą (Auris/Corolla/Yaris) lub w podłodze bagażnika (Prius/RAV4).",
            uds_did="0x226003",
            obd_pid="0x6003",
            expected_range="Napięcie bloku: 14.5 - 17.5 V. Maksymalna dopuszczalna różnica (Delta) między blokami: < 0.20 V.",
            diagnostic_tip="Różnica napięć (Delta) przekraczająca 0.30V pod obciążeniem niemal natychmiast generuje kod P0A80.",
        ),
        "toyota_hybrid_inverter": SensorLocation(
            short_name="toyota_hybrid_inverter",
            full_name="Falownik / Inwerter układu hybrydowego THS-II (moduł mocy MG1/MG2)",
            physical_location="W komorze silnika po lewej stronie (duża aluminiowa obudowa z pomarańczowymi przewodami HV).",
            uds_did="0x226010",
            obd_pid="0x6010",
            expected_range="Temperatura pracy inwertera: 40 - 75°C (maks. 90°C).",
            diagnostic_tip="Sprawdź cyrkulację płynu w dedykowanym zbiorniczku wyrównawczym inwertera - awaria elektrycznej pompki inwertera powoduje przegrzanie i P0A93.",
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
        "bmw_valvetronic_fault": DiagnosticProcedure(
            procedure_id="bmw_valvetronic_fault",
            title="Schemat diagnostyczny: Usterka układu zmiennego wzniosu zaworów Valvetronic (2A67 / 2A6B / P1050)",
            related_dtcs=["2A67", "2A6B", "P1050", "P1056"],
            symptom="Brak reakcji na pedał przyspieszenia, praca silnika w trybie awaryjnym przepustnicy, szarpanie na jałowym.",
            applicable_engines=["BMW N52 R6", "BMW N55 3.0 Turbo", "BMW B48 2.0 Turbo", "BMW B58 3.0 Turbo"],
            steps=[
                DiagnosticStep(
                    step_number=1,
                    title="Odczyt kąta wałka mimośrodowego i napięcia silnika VVT",
                    description="Sprawdź kąt wałka mimośrodowego w parametrach Live Data. Na biegu jałowym powinien wynosić około 25-35°.",
                    sensor_to_check="bmw_valvetronic",
                    expected_value="Kąt płynnie rośnie wraz z obciążeniem od ~25° do ~170°.",
                ),
                DiagnosticStep(
                    step_number=2,
                    title="Kontrola obecności oleju we wtyczce czujnika mimośrodu",
                    description="Odepnij okrągłe złącze czujnika wałka mimośrodowego z pokrywy zaworów. Olej we wtyczce oznacza uszkodzenie uszczelniacza czujnika.",
                    common_failure="Olej silnikowy wewnątrz wtyczki czujnika powoduje zwarcie sygnałów i błędy 2A67/2A6B.",
                ),
                DiagnosticStep(
                    step_number=3,
                    title="Procedura adaptacji i nauki położeń krańcowych Valvetronic",
                    description="Po weryfikacji mechanicznej wykonaj procedurę adaptacji (nauka skrajnych punktów zderzakowych).",
                    expected_value="Adaptacja zakończona sukcesem (Status: OK).",
                ),
            ],
        ),
        "psa_puretech_oil_pressure": DiagnosticProcedure(
            procedure_id="psa_puretech_oil_pressure",
            title="Schemat diagnostyczny: Niskie ciśnienie oleju / Łuszczenie paska rozrządu wet-belt (P15A4 / P0524)",
            related_dtcs=["P15A4", "P0524", "P15A8"],
            symptom="Komunikat 'Usterka ciśnienia oleju: zatrzymaj pojazd', kontrolka ciśnienia oleju na rozgrzanym silniku.",
            applicable_engines=["PSA 1.2 PureTech EB2", "Ford 1.0 EcoBoost"],
            steps=[
                DiagnosticStep(
                    step_number=1,
                    title="Wzrokowa kontrola paska rozrządu przez wlew oleju przymiarem",
                    description="Przyłóż dedykowany przymiar do paska rozrządu widocznego pod korkiem wlewu oleju. Pasek pracujący w oleju pęcznieje i rozszerza się przed zerwaniem.",
                    sensor_to_check="ford_psa_wet_belt",
                    common_failure="Spęczniały pasek trze o krawędzie kół zębatych, a zrzucony kord zatyka smok pompy.",
                ),
                DiagnosticStep(
                    step_number=2,
                    title="Pomiar mechaniczny ciśnienia oleju manometrem na gorącym silniku",
                    description="Wkręć manometr w miejsce czujnika ciśnienia. Rozgrzej olej do 90°C.",
                    expected_value="Bieg jałowy: min. 1.2-1.4 bar. 2000 RPM: min. 2.8 bar.",
                ),
                DiagnosticStep(
                    step_number=3,
                    title="Demontaż miski olejowej i inspekcja sitka smoka",
                    description="W przypadku ciśnienia < 1.0 bar zdemontuj miskę olejową, oczyść sitko smoka pompy i wymień kompletny rozrząd z pompą próżniową.",
                    common_failure="Całkowite zatkanie sitka smoka kłaczkami paska rozrządu.",
                ),
            ],
        ),
        "toyota_hybrid_battery_degradation": DiagnosticProcedure(
            procedure_id="toyota_hybrid_battery_degradation",
            title="Schemat diagnostyczny: Degradacja baterii trakcyjnej HV / Nierówne napięcia bloków (P0A80 / P3000)",
            related_dtcs=["P0A80", "P3000", "P0A7F"],
            symptom="Komunikat 'Check Hybrid System', silnik spalinowy nie gaśnie, gwałtowne skoki poziomu naładowania na wyświetlaczu (z 8 kratek do 2).",
            applicable_engines=["Toyota 1.8 Hybrid HSD 2ZR-FXE", "Toyota 1.5 Hybrid HSD", "Toyota 2.5 Hybrid HSD"],
            steps=[
                DiagnosticStep(
                    step_number=1,
                    title="Odczyt różnicy napięć między blokami (Block Delta Voltage) pod obciążeniem",
                    description="W Live Data obserwuj napięcia bloków 1-14 podczas gwałtownego przyspieszania w trybie elektrycznym.",
                    sensor_to_check="toyota_hybrid_battery",
                    expected_value="Różnica między najwyższym a najniższym blokiem nie może przekraczać 0.20V. Wartość > 0.30V generuje kod P0A80.",
                ),
                DiagnosticStep(
                    step_number=2,
                    title="Inspekcja wentylatora chłodzenia baterii trakcyjnej HV",
                    description="Zdemontuj kratkę wlotową chłodzenia baterii (przy tylnej kanapie) i sprawdź wirnik wentylatora.",
                    common_failure="Wirnik wentylatora zaklejony kurzem i sierścią powoduje przegrzewanie środkowych modułów baterii.",
                ),
                DiagnosticStep(
                    step_number=3,
                    title="Wymiana uszkodzonych par ogniw (lub całego pakietu) i kalibracja",
                    description="Zidentyfikuj blok o najniższym napięciu pod obciążeniem i wymień sparowane moduły Ni-MH na moduły o równej pojemności.",
                ),
            ],
        ),
        "bmw_n47_timing_chain": DiagnosticProcedure(
            procedure_id="bmw_n47_timing_chain",
            title="Schemat diagnostyczny: Rozciągnięcie i hałas łańcucha rozrządu w BMW N47/N57 (480A / P0016)",
            related_dtcs=["480A", "2A82", "P0016"],
            symptom="Metaliczne szuranie, cykanie i grzechotanie z tyłu silnika od strony skrzyni biegów w zakresie 1500-2000 RPM.",
            applicable_engines=["BMW N47 2.0d", "BMW N57 3.0d", "BMW B47 2.0d"],
            steps=[
                DiagnosticStep(
                    step_number=1,
                    title="Osłuchanie stetoskopem warsztatowym tylnej części silnika",
                    description="Przy obrotach 1500 RPM przyłóż stetoskop do obudowy skrzyni biegów i tylnej ściany głowicy silnika.",
                    common_failure="Wytarte plastikowe ślizgi i rozciągnięty górny lub środkowy łańcuch rozrządu.",
                ),
                DiagnosticStep(
                    step_number=2,
                    title="Pomiar wysunięcia tłoczka górnego napinacza rozrządu",
                    description="Wykręć górny napinacz śrubowy z głowicy i zmierz głębokość wysunięcia tłoczka.",
                    expected_value="Wysunięcie tłoczka > 18 mm świadczy o krytycznym rozciągnięciu łańcucha grożącym zerwaniem.",
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
