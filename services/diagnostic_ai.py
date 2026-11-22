from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DTCFinding:
    code: str
    title: str
    description: str
    urgency: str  # "info", "warning", "critical"
    possible_causes: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    freeze_frame_notes: str = ""


@dataclass
class DiagnosisReport:
    dtc_findings: list[DTCFinding]
    overall_urgency: str  # "info", "warning", "critical"
    safe_to_drive: bool
    summary: str
    safety_warnings: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class DiagnosticAI(ABC):
    """Bazowy interfejs warstwy diagnostycznej AI w trybie offline-first."""

    @abstractmethod
    def analyze(self, vehicle_context: dict[str, Any]) -> DiagnosisReport:
        """Przeprowadza analizę kontekstu pojazdu i zwraca raport."""
        raise NotImplementedError


# Standardowa baza wiedzy DTC dla trybu offline
STANDARD_DTC_DATABASE: dict[str, dict[str, Any]] = {
    # ---------------- Układ dolotowy i zasilania (MAF / MAP / Przepustnica) ----------------
    "P0100": {
        "title": "Przepływomierz masowy powietrza (MAF) - usterka obwodu",
        "description": "Brak prawidłowego sygnału elektrycznego z przepływomierza powietrza MAF.",
        "urgency": "warning",
        "causes": [
            "Uszkodzone złącze lub przerwa w wiązce elektrycznej czujnika MAF",
            "Brak zasilania lub masy czujnika MAF",
            "Uszkodzony element pomiarowy przepływomierza",
        ],
        "actions": [
            "Sprawdź wtyczkę i przewody zasilające przepływomierza",
            "Zweryfikuj bezpiecznik zasilania czujników osprzętu silnika",
        ],
    },
    "P0101": {
        "title": "Przepływomierz powietrza (MAF) - sygnał poza zakresem",
        "description": "Ilość powietrza zmierzona przez MAF nie zgadza się z obrotami i obciążeniem silnika.",
        "urgency": "warning",
        "causes": [
            "Zabrudzony drucik pomiarowy lub termistor w przepływomierzu MAF",
            "Nieszczelność układu dolotowego (lewe powietrze za przepływomierzem)",
            "Pęknięta rura dolotowa, uszkodzona odma lub sparciałe wężyki podciśnienia",
            "Zablokowany lub mocno zanieczyszczony filtr powietrza",
        ],
        "actions": [
            "Sprawdź wizualnie szczelność gumowych rur dolotu między MAF a przepustnicą",
            "Wyczyść sensor dedykowanym preparatem do czyszczenia przepływomierzy (Air Flow Sensor Cleaner)",
            "Skontroluj stan i drożność filtra powietrza",
        ],
    },
    "P0102": {
        "title": "Przepływomierz powietrza (MAF) - sygnał za niski",
        "description": "Napięcie lub częstotliwość sygnału z MAF jest poniżej dolnej granicy normy.",
        "urgency": "warning",
        "causes": [
            "Zwarcie do masy lub przerwa w obwodzie sygnałowym MAF",
            "Duża nieszczelność dolotu przed przepustnicą",
            "Uszkodzony czujnik MAF",
        ],
        "actions": [
            "Zmierz napięcie zasilania i sygnału na wtyczce MAF",
            "Sprawdź szczelność dolotu",
        ],
    },
    "P0103": {
        "title": "Przepływomierz powietrza (MAF) - sygnał za wysoki",
        "description": "Napięcie sygnału z czujnika MAF jest nienaturalnie wysokie.",
        "urgency": "warning",
        "causes": [
            "Zwarcie do plusa zasilania w wiązce MAF",
            "Uszkodzenie wewnętrzne czujnika przepływu",
        ],
        "actions": ["Sprawdź wiązkę pod kątem zwarcia do napięcia akumulatora"],
    },
    "P0106": {
        "title": "Czujnik ciśnienia w kolektorze (MAP) - sygnał poza zakresem",
        "description": "Odczyt podciśnienia z czujnika MAP nie odpowiada warunkom pracy silnika.",
        "urgency": "warning",
        "causes": [
            "Nieszczelność uszczelek kolektora ssącego",
            "Zabrudzony olejem lub nagarem czujnik MAP",
            "Nieszczelność przewodu podciśnienia do czujnika",
        ],
        "actions": ["Wyczyść czujnik MAP z nagaru i sprawdź szczelność kolektora"],
    },
    "P0110": {
        "title": "Czujnik temperatury powietrza dolotowego (IAT) - usterka obwodu",
        "description": "Brak prawidłowego odczytu temperatury zasysanego powietrza.",
        "urgency": "info",
        "causes": ["Uszkodzona wtyczka czujnika IAT", "Uszkodzony termistor w czujniku"],
        "actions": ["Sprawdź złącze czujnika temperatury dolotu"],
    },
    "P0115": {
        "title": "Czujnik temperatury płynu chłodzącego (ECT) - usterka obwodu",
        "description": "Czujnik temperatury silnika podaje nieprawidłowy sygnał do ECU.",
        "urgency": "warning",
        "causes": [
            "Uszkodzony podwójny czujnik ECT (np. G62 w VAG)",
            "Przerwa lub zwarcie w wiązce czujnika",
            "Zacięty termostat w pozycji otwartej",
        ],
        "actions": ["Porównaj odczyt temperatury w aplikacji ze wskazaniem na zegarach"],
    },
    "P0120": {
        "title": "Czujnik położenia przepustnicy (TPS) - usterka obwodu",
        "description": "Potencjometr przepustnicy podaje niestabilny sygnał kąta otwarcia.",
        "urgency": "warning",
        "causes": ["Zabrudzona nagarem gardziel przepustnicy", "Zużyty potencjometr przepustnicy"],
        "actions": ["Wyczyść przepustnicę z nagaru i przeprowadź adaptację (Basic Settings)"],
    },
    # ---------------- Mieszanka paliwowo-powietrzna i sondy lambda ----------------
    "P0171": {
        "title": "Mieszanka zbyt uboga (Bank 1)",
        "description": "Układ paliwowy podaje zbyt ubogą mieszankę na pierwszym rzędzie cylindrów.",
        "urgency": "warning",
        "causes": [
            "Nieszczelność dolotu / podciśnienia (zasysanie 'lewego powietrza')",
            "Zabrudzony lub uszkodzony przepływomierz masowy (MAF)",
            "Niskie ciśnienie paliwa lub zapchany filtr paliwa",
            "Nieszczelność wydechu przed pierwszą sondą lambda",
        ],
        "actions": [
            "Sprawdź szczelność rur dolotowych i wężyków odmy",
            "Odczytaj wskazania MAF na biegu jałowym",
            "Sprawdź długoterminową korektę paliwa LTFT",
        ],
    },
    "P0172": {
        "title": "Mieszanka zbyt bogata (Bank 1)",
        "description": "Układ paliwowy podaje zbyt dużą dawkę paliwa względem ilości powietrza.",
        "urgency": "warning",
        "causes": [
            "Nieszczelny / lejący wtryskiwacz paliwa",
            "Mocno zabrudzony filtr powietrza",
            "Uszkodzona sonda lambda podająca zawyżone napięcie",
            "Za wysokie ciśnienie na listwie paliwowej (zacięty regulator)",
        ],
        "actions": [
            "Sprawdź stan filtra powietrza",
            "Zweryfikuj korekty wtrysku paliwa oraz ciśnienie na szynie",
        ],
    },
    "P0130": {
        "title": "Sonda lambda (Bank 1, Czujnik 1) - usterka obwodu",
        "description": "Brak prawidłowego sygnału napięciowego z przedniej sondy regulacyjnej.",
        "urgency": "warning",
        "causes": ["Zużycie sondy lambda", "Uszkodzona wiązka elektryczna przy wydechu"],
        "actions": ["Sprawdź stan przewodów sondy pod kątem przetarcia o elementy wydechu"],
    },
    "P0133": {
        "title": "Sonda lambda (Bank 1, Czujnik 1) - powolna reakcja",
        "description": "Sonda regulacyjna zbyt wolno reaguje na zmiany składu spalin.",
        "urgency": "info",
        "causes": ["Starzenie się ogniwa pomiarowego sondy", "Zatrucie ołowiem lub olejem"],
        "actions": ["Obserwuj wykres oscylacji napięcia sondy (0.1V - 0.9V)"],
    },
    "P0135": {
        "title": "Sonda lambda (Bank 1, Czujnik 1) - usterka grzałki",
        "description": "Przerwa w obwodzie podgrzewacza sondy lambda.",
        "urgency": "warning",
        "causes": ["Przepalona grzałka sondy lambda", "Przepalony bezpiecznik grzałki"],
        "actions": ["Zmierz rezystancję grzałki sondy omomierzem (zwykle 3-15 Ohm)"],
    },
    # ---------------- Turbodoładowanie ----------------
    "P0234": {
        "title": "Układ doładowania turbosprężarki - przeładowanie (Overboost)",
        "description": "Ciśnienie doładowania przekroczyło dopuszczalny limit zadany przez ECU.",
        "urgency": "warning",
        "causes": [
            "Zapieczone kierownice zmiennej geometrii turbiny (VTG) w pozycji max",
            "Uszkodzony zawór sterowania doładowaniem N75",
            "Zacięty siłownik podciśnieniowy (gruszka) turbiny",
        ],
        "actions": [
            "Sprawdź płynność ruchu sztangi turbiny przy użyciu strzykawki/pompki próżniowej",
            "Wykonaj test elementu wykonawczego zaworu N75 w aplikacji",
        ],
    },
    "P0299": {
        "title": "Układ doładowania turbosprężarki - niedoładowanie (Underboost)",
        "description": "Rzeczywiste ciśnienie doładowania jest znacznie niższe od zadanego.",
        "urgency": "warning",
        "causes": [
            "Nieszczelność w układzie dolotowym pod ciśnieniem (pęknięta rura, nieszczelny intercooler)",
            "Przetarty wężyk podciśnienia do zaworu N75 lub gruszki turbiny",
            "Uszkodzony zawór upustowy DV (np. pęknięta membrana w 1.8T/2.0 TFSI)",
            "Zużycie mechaniczne wirnika lub klapki wastegate turbosprężarki",
        ],
        "actions": [
            "Osłuchaj syczenie pod maską podczas przyspieszania",
            "Skontroluj stan gumowych kolanek intercoolera pod kątem pęknięć",
            "Sprawdź szczelność wężyków podciśnienia",
        ],
    },
    # ---------------- Wypadanie zapłonów (Misfire) ----------------
    "P0300": {
        "title": "Wielokrotne / losowe wypadanie zapłonów",
        "description": "Wykryto wypadanie zapłonów w więcej niż jednym cylindrze.",
        "urgency": "warning",
        "causes": [
            "Zużyte lub zabrudzone świece zapłonowe",
            "Uszkodzona cewka lub przewody zapłonowe",
            "Nieszczelność w układzie dolotowym (lewe powietrze)",
            "Niskie ciśnienie paliwa lub zanieczyszczone wtryskiwacze",
        ],
        "actions": [
            "Sprawdź stan świec zapłonowych",
            "Zweryfikuj cewki zapłonowe",
            "Sprawdź korekty paliwowe (STFT/LTFT)",
        ],
    },
    "P0301": {
        "title": "Wypadanie zapłonu - cylinder 1",
        "description": "Wykryto brak zapłonu w cylindrze 1.",
        "urgency": "warning",
        "causes": ["Świeca zapłonowa cylindra 1", "Cewka cylindra 1", "Wtryskiwacz cylindra 1"],
        "actions": ["Zamień cewkę cylindra 1 z innym cylindrem, by sprawdzić czy błąd wędruje"],
    },
    "P0302": {
        "title": "Wypadanie zapłonu - cylinder 2",
        "description": "Wykryto brak zapłonu w cylindrze 2.",
        "urgency": "warning",
        "causes": ["Świeca zapłonowa cylindra 2", "Cewka cylindra 2", "Wtryskiwacz cylindra 2"],
        "actions": ["Zamień cewkę cylindra 2 z innym cylindrem"],
    },
    "P0303": {
        "title": "Wypadanie zapłonu - cylinder 3",
        "description": "Wykryto brak zapłonu w cylindrze 3.",
        "urgency": "warning",
        "causes": ["Świeca zapłonowa cylindra 3", "Cewka cylindra 3", "Wtryskiwacz cylindra 3"],
        "actions": ["Zamień cewkę cylindra 3 z innym cylindrem"],
    },
    "P0304": {
        "title": "Wypadanie zapłonu - cylinder 4",
        "description": "Wykryto brak zapłonu w cylindrze 4.",
        "urgency": "warning",
        "causes": ["Świeca zapłonowa cylindra 4", "Cewka cylindra 4", "Wtryskiwacz cylindra 4"],
        "actions": ["Zamień cewkę cylindra 4 z innym cylindrem"],
    },
    # ---------------- Układy emisji (Katalizator, EVAP, EGR, DPF) ----------------
    "P0401": {
        "title": "Układ recyrkulacji spalin (EGR) - niewystarczający przepływ",
        "description": "Ilość spalin zawracana przez zawór EGR jest mniejsza niż wymagana przez sterownik.",
        "urgency": "info",
        "causes": [
            "Zarośnięty nagarem zawór EGR lub rurka łącząca z kolektorem",
            "Niesprawny siłownik podciśnieniowy zaworu EGR",
        ],
        "actions": ["Wyczyść zawór EGR i kanały dolotowe z osadów sadzy"],
    },
    "P0420": {
        "title": "Niska sprawność katalizatora (Bank 1)",
        "description": "Wydajność konwersji katalizatora spadła poniżej progu normy.",
        "urgency": "info",
        "causes": [
            "Naturalne zużycie katalizatora",
            "Uszkodzenie drugiej sondy lambda (diagnostycznej)",
            "Nieszczelność wydechu w okolicy katalizatora",
        ],
        "actions": [
            "Sprawdź wykres napięcia drugiej sondy lambda",
            "Sprawdź szczelność układu wydechowego",
        ],
    },
    "P0441": {
        "title": "Układ pochłaniania oparów paliwa (EVAP) - nieprawidłowy przepływ",
        "description": "Sterownik nie wykrył prawidłowego przedmuchu par paliwa ze zbiornika z węglem aktywnym.",
        "urgency": "info",
        "causes": [
            "Zacięty lub uszkodzony zawór odpowietrzania zbiornika N80",
            "Zablokowany przewód podciśnienia EVAP",
        ],
        "actions": [
            "Uruchom test wyjść dla zaworu N80 w zakładce Nastawniki i posłuchaj cykania",
            "Sprawdź drożność przewodu między zaworem N80 a kolektorem",
        ],
    },
    "P0455": {
        "title": "Układ pochłaniania oparów paliwa (EVAP) - duża nieszczelność",
        "description": "Wykryto znaczną utratę ciśnienia w układzie oparów paliwa.",
        "urgency": "info",
        "causes": [
            "Niedokręcony lub uszkodzony korek wlewu paliwa",
            "Pęknięty przewód oparów paliwa ze zbiornika",
        ],
        "actions": ["Upewnij się, że korek wlewu paliwa jest prawidłowo dokręcony"],
    },
    "P2002": {
        "title": "Filtr cząstek stałych (DPF) - wydajność poniżej progu",
        "description": "Skuteczność wychwytywania sadzy przez filtr DPF jest obniżona.",
        "urgency": "warning",
        "causes": [
            "Pęknięty wkład ceramiczny filtra DPF",
            "Przekłamujący czujnik różnicy ciśnień Delta-P (G450)",
        ],
        "actions": ["Sprawdź odczyt czujnika różnicy ciśnień na wyłączonym i włączonym silniku"],
    },
    "P2452": {
        "title": "Czujnik różnicy ciśnień DPF (G450) - usterka obwodu",
        "description": "Nieprawidłowy sygnał elektryczny z czujnika ciśnienia DPF.",
        "urgency": "warning",
        "causes": [
            "Uszkodzenie czujnika ciśnienia różnicowego G450 (częsta usterka VAG)",
            "Stopione lub pęknięte gumowe rurki prowadzące od filtra do czujnika",
        ],
        "actions": ["Sprawdź stan elastycznych rurek dochodzących do czujnika G450 na grodzi silnika"],
    },
    # ---------------- Czujniki prędkości i magistrala ----------------
    "P0500": {
        "title": "Czujnik prędkości pojazdu (VSS) - awaria",
        "description": "Brak sygnału z czujnika prędkości pojazdu.",
        "urgency": "warning",
        "causes": ["Uszkodzony czujnik prędkości VSS", "Uszkodzona wiązka / wtyczka"],
        "actions": ["Sprawdź stan złącza czujnika prędkości na skrzyni biegów"],
    },
    "P0600": {
        "title": "Błąd magistrali szeregowej sterownika (CAN/Serial)",
        "description": "Brak prawidłowej komunikacji na magistrali pokładowej.",
        "urgency": "critical",
        "causes": ["Zwarcie lub przerwa w liniach magistrali CAN", "Awaria modułu ECU/ABS/Licznik"],
        "actions": ["Sprawdź napięcia magistrali CAN", "Zdiagnozuj stan zasilania modułów"],
    },
}

DTC_KNOWLEDGE_BASE = STANDARD_DTC_DATABASE


class RuleBasedDiagnosticAI(DiagnosticAI):
    """Deterministyczny silnik diagnostyczny oparty na regułach bezpieczeństwa i bazie DTC.

    Gwarantuje działanie offline, brak halucynacji i absolutny priorytet bezpieczeństwa pojazdu.
    """

    def __init__(
        self,
        dtc_database: Optional[dict[str, dict[str, Any]]] = None,
        knowledge_base: Optional[Any] = None,
    ):
        self.db = dtc_database if dtc_database is not None else STANDARD_DTC_DATABASE
        self.knowledge_base = knowledge_base

    def analyze(self, vehicle_context: dict[str, Any]) -> DiagnosisReport:
        dtc_list: list[str] = vehicle_context.get("dtc_codes", [])
        raw_code = vehicle_context.get("dtc_code")
        if raw_code and raw_code not in dtc_list:
            dtc_list = [raw_code] + dtc_list

        findings: list[DTCFinding] = []
        safety_warnings: list[str] = []
        safe_to_drive = True

        # 1. Analiza kodów DTC
        for code in dtc_list:
            norm_code = code.upper().strip()
            finding = self._evaluate_dtc(norm_code, vehicle_context)
            findings.append(finding)

        # 2. Triage telemetryczny (reguły fizyczne i krytyczne)
        coolant = (
            vehicle_context.get("coolant_temp_c")
            or vehicle_context.get("coolant_c")
            or vehicle_context.get("coolant_temp")
        )
        if coolant is not None:
            if coolant >= 115:
                safety_warnings.append(
                    f"KRYTYCZNE: Temperatura płynu chłodzącego ({coolant}°C) przekracza próg bezpieczeństwa (115°C). "
                    "Ryzyko przegrzania i pęknięcia głowicy!"
                )
                safe_to_drive = False
            elif coolant >= 105:
                safety_warnings.append(
                    f"OSTRZEŻENIE: Podwyższona temperatura cieczy ({coolant}°C). Obserwuj wskazania i wentylatory."
                )

        oil_temp = vehicle_context.get("oil_temp_c") or vehicle_context.get("oil_temp")
        if oil_temp is not None and oil_temp >= 130:
            safety_warnings.append(
                f"KRYTYCZNE: Temperatura oleju silnikowego ({oil_temp}°C) grozi zerwaniem filmu olejowego!"
            )
            safe_to_drive = False

        rpm = vehicle_context.get("rpm", 0)
        has_misfire = any(f.code.startswith("P030") for f in findings)
        if has_misfire and rpm > 3000:
            safety_warnings.append(
                "KRYTYCZNE: Wypadanie zapłonów przy wysokich obrotach grozi zniszczeniem katalizatora paliwem."
            )
            safe_to_drive = False

        battery_v = vehicle_context.get("voltage") or vehicle_context.get("battery_voltage")
        if battery_v is not None:
            if battery_v < 10.5:
                safety_warnings.append(f"KRYTYCZNE: Napięcie akumulatora/ECU ({battery_v}V) jest krytycznie niskie!")
                safe_to_drive = False
            elif battery_v < 11.8:
                safety_warnings.append(f"OSTRZEŻENIE: Niskie napięcie instalacji ({battery_v}V) podczas pracy.")

        # 3. Ustalenie całościowego poziomu pilności
        overall_urgency = "info"
        if not safe_to_drive or any(f.urgency == "critical" for f in findings):
            overall_urgency = "critical"
            safe_to_drive = False
        elif safety_warnings or any(f.urgency == "warning" for f in findings):
            overall_urgency = "warning"

        # 4. Krok następny i rekomendacje (hands-free dla kierowcy w trasie)
        next_steps = [
            "Parametry zamrożone (freeze-frame) zostały automatycznie zarchiwizowane w bazie",
            "Nie kasuj DTC w trakcie jazdy",
        ]
        if not safe_to_drive:
            next_steps.insert(0, "Zatrzymaj pojazd w bezpiecznym miejscu i wyłącz silnik")
            next_steps.append("Skonsultuj się z wykwalifikowanym serwisem samochodowym")
        else:
            next_steps.append("Zaplanuj diagnostykę warsztatową")

        summary = self._generate_summary(findings, overall_urgency, safe_to_drive)

        return DiagnosisReport(
            dtc_findings=findings,
            overall_urgency=overall_urgency,
            safe_to_drive=safe_to_drive,
            summary=summary,
            safety_warnings=safety_warnings,
            next_steps=next_steps,
            metadata={"engine": "RuleBasedDiagnosticAI", "findings_count": len(findings)},
        )

    def _evaluate_dtc(self, code: str, context: dict[str, Any]) -> DTCFinding:
        entry = self.db.get(code)
        if entry:
            actions = list(entry.get("actions", []))
            try:
                from services.diagnostic_knowledge_base import DiagnosticProcedureRegistry

                proc = DiagnosticProcedureRegistry.find_by_dtc(code)
                if proc:
                    for st in proc.steps:
                        actions.append(f"Krok {st.step_number} ({st.title}): {st.description}")
            except Exception:
                pass

            return DTCFinding(
                code=code,
                title=entry["title"],
                description=entry["description"],
                urgency=entry["urgency"],
                possible_causes=list(entry.get("causes", [])),
                recommended_actions=actions,
                freeze_frame_notes=f"Zweryfikuj warunki wystąpienia dla {code}",
            )

        # Sprawdzenie bazy wiedzy / procedur dla nieznanego w STANDARD_DTC kodu
        try:
            from services.diagnostic_knowledge_base import DiagnosticKnowledgeBase

            kb = self.knowledge_base or DiagnosticKnowledgeBase()
            res = kb.lookup_dtc(code, vehicle_context=context, allow_web_search=False)
            actions = ["Zapisz parametry pracy silnika i sprawdź biuletyny TSB"]
            if res.diagnostic_procedure:
                for st in res.diagnostic_procedure.steps:
                    actions.append(f"Krok {st.step_number} ({st.title}): {st.description}")
            return DTCFinding(
                code=code,
                title=res.title,
                description=res.description,
                urgency="info",
                possible_causes=res.possible_causes,
                recommended_actions=actions,
                freeze_frame_notes=res.confirmation_prompt or "Odczytaj pełną ramkę zamrożoną",
            )
        except Exception:
            pass

        # Fallback dla nieznanego kodu DTC
        category = "Układ napędowy (Powertrain)" if code.startswith("P") else "Sterownik pojazdu"
        return DTCFinding(
            code=code,
            title=f"Kod diagnostyczny {code}",
            description=f"Standardowy kod z grupy: {category}. Wymaga weryfikacji w dokumentacji serwisowej.",
            urgency="info",
            possible_causes=["Wymagana dokumentacja serwisowa konkretnego modelu pojazdu"],
            recommended_actions=["Zapisz parametry pracy silnika i sprawdź biuletyny TSB"],
            freeze_frame_notes="Odczytaj pełną ramkę zamrożoną",
        )

    def _generate_summary(self, findings: list[DTCFinding], urgency: str, safe: bool) -> str:
        if not findings:
            if not safe:
                return "Brak zarejestrowanych DTC, ale parametry telemetryczne wskazują stan krytyczny!"
            return "Brak aktywnych błędów DTC. Układ pracuje prawidłowo."

        codes = {f.code for f in findings}

        # 1. Specjalna korelacja dla pary P0171 + P0101 (lub P0102)
        if "P0171" in codes and any(c in codes for c in ["P0101", "P0100", "P0102"]):
            return (
                "Korelacja usterek (P0171 + P0101): Mieszanka zbyt uboga powiązana z błędem przepływomierza MAF. "
                "Wskazuje na nieszczelność w dolocie za przepływomierzem (zasysanie lewego powietrza przez pękniętą rurę lub odmę) "
                "bądź mocne zabrudzenie sensora MAF. Jazda dozwolona z umiarkowanym obciążeniem."
            )

        # 2. Korelacja dla wypadania zapłonu + mieszanki (P0300 + P0171)
        if "P0300" in codes and "P0171" in codes:
            return (
                "Korelacja usterek: Wypadanie zapłonów (P0300) wywołane skrajnie ubogą mieszanką (P0171). "
                "Prawdopodobna duża nieszczelność w układzie dolotowym lub spadek ciśnienia paliwa."
            )

        # 3. Korelacja niedoładowania (P0299) z dolotem
        if "P0299" in codes and any(c in codes for c in ["P0101", "P0171"]):
            return (
                "Korelacja usterek: Niedoładowanie turbiny (P0299) z błędem napełnienia cylindrów. "
                "Skontroluj szczelność węży intercoolera oraz zawór N75/DV."
            )

        codes_str = ", ".join(f.code for f in findings)
        if urgency == "critical":
            return f"Wykryto krytyczny stan pojazdu (kody: {codes_str}). Dalsza jazda stwarza ryzyko awarii!"
        if urgency == "warning":
            return f"Wykryto usterki wymagające uwagi (kody: {codes_str}). Zalecana spokojna jazda i kontrola."
        return f"Zarejestrowano kody informacyjne ({codes_str}). Brak bezpośredniego zagrożenia."


class LocalDiagnosticAI(DiagnosticAI):
    """Adapter dla lokalnego modelu AI (np. LLM w GGUF), z deterministycznym fallbackiem."""

    def __init__(
        self,
        fallback_engine: Optional[DiagnosticAI] = None,
        model_runner: Optional[Callable[[str], str]] = None,
        llm_engine: Optional[Any] = None,
    ):
        self.fallback = fallback_engine or RuleBasedDiagnosticAI()
        self.llm_engine = llm_engine
        self.model_runner = model_runner
        if self.llm_engine and not self.model_runner:
            self.model_runner = lambda prompt: self.llm_engine.ask(prompt)

    def analyze(self, vehicle_context: dict[str, Any]) -> DiagnosisReport:
        # Zawsze najpierw przeprowadzamy ocenę deterministyczną
        baseline_report = self.fallback.analyze(vehicle_context)

        # Jeśli brak runnera lub błąd modelu lokalnego, bezpiecznie zwracamy baseline
        if not self.model_runner:
            return baseline_report

        try:
            prompt = (
                f"Przeanalizuj diagnostykę pojazdu: kody={vehicle_context.get('dtc_codes')}, "
                f"telemetria={vehicle_context}. Podaj krótkie objaśnienie."
            )
            llm_text = self.model_runner(prompt)
            if llm_text:
                baseline_report.summary = f"[Lokalny Asystent AI] {llm_text.strip()}"
                baseline_report.metadata["llm_processed"] = True
        except Exception:
            # W przypadku awarii inference zachowujemy niezawodny raport regułowy
            baseline_report.metadata["llm_error"] = True

        return baseline_report
