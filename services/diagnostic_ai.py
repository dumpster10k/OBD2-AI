from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


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
    "P0115": {
        "title": "Usterka obwodu temperatury płynu chłodzącego (ECT)",
        "description": "Czujnik ECT podaje nieprawidłowy sygnał do ECU.",
        "urgency": "warning",
        "causes": ["Uszkodzony czujnik ECT", "Przerwa lub zwarcie w wiązce czujnika", "Termostat"],
        "actions": ["Porównaj odczyt ECT z rzeczywistą temperaturą silnika"],
    },
    "P0171": {
        "title": "Mieszanka zbyt uboga (Bank 1)",
        "description": "Układ paliwowy podaje zbyt ubogą mieszankę na pierwszym rzędzie cylindrów.",
        "urgency": "warning",
        "causes": [
            "Nieszczelność dolotu / podciśnienia",
            "Zabrudzony lub uszkodzony przepływomierz masowy (MAF)",
            "Niskie ciśnienie pompy paliwa",
            "Nieszczelność wydechu przed sondą lambda",
        ],
        "actions": [
            "Sprawdź szczelność dolotu generatorem dymu",
            "Odczytaj wskazania MAF na biegu jałowym",
        ],
    },
    "P0172": {
        "title": "Mieszanka zbyt bogata (Bank 1)",
        "description": "Układ paliwowy podaje zbyt bogatą mieszankę na pierwszym rzędzie cylindrów.",
        "urgency": "warning",
        "causes": ["Cieknący wtryskiwacz", "Zabrudzony filtr powietrza", "Uszkodzona sonda lambda"],
        "actions": ["Sprawdź filtr powietrza i ciśnienie paliwa"],
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


class RuleBasedDiagnosticAI(DiagnosticAI):
    """Deterministyczny silnik diagnostyczny oparty na regułach bezpieczeństwa i bazie DTC.
    
    Gwarantuje działanie offline, brak halucynacji i absolutny priorytet bezpieczeństwa pojazdu.
    """

    def __init__(self, dtc_database: Optional[dict[str, dict[str, Any]]] = None):
        self.db = dtc_database if dtc_database is not None else STANDARD_DTC_DATABASE

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
        coolant = vehicle_context.get("coolant_temp_c") or vehicle_context.get("coolant_c")
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

        oil_temp = vehicle_context.get("oil_temp_c")
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
                safety_warnings.append(
                    f"KRYTYCZNE: Napięcie akumulatora/ECU ({battery_v}V) jest krytycznie niskie!"
                )
                safe_to_drive = False
            elif battery_v < 11.8:
                safety_warnings.append(
                    f"OSTRZEŻENIE: Niskie napięcie instalacji ({battery_v}V) podczas pracy."
                )

        # 3. Ustalenie całościowego poziomu pilności
        overall_urgency = "info"
        if not safe_to_drive or any(f.urgency == "critical" for f in findings):
            overall_urgency = "critical"
            safe_to_drive = False
        elif safety_warnings or any(f.urgency == "warning" for f in findings):
            overall_urgency = "warning"

        # 4. Krok następny i rekomendacje
        next_steps = [
            "Zapisz ramkę zamrożoną (freeze-frame) przed skasowaniem kodów",
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
            return DTCFinding(
                code=code,
                title=entry["title"],
                description=entry["description"],
                urgency=entry["urgency"],
                possible_causes=list(entry.get("causes", [])),
                recommended_actions=list(entry.get("actions", [])),
                freeze_frame_notes=f"Zweryfikuj warunki wystąpienia dla {code}",
            )

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

        codes_str = ", ".join(f.code for f in findings)
        if urgency == "critical":
            return f"Wykryto krytyczny stan pojazdu (kody: {codes_str}). Dalsza jazda stwarza ryzyko awarii!"
        if urgency == "warning":
            return f"Wykryto usterki wymagające uwagi (kody: {codes_str}). Zalecana kontrola."
        return f"Zarejestrowano kody informacyjne ({codes_str}). Brak bezpośredniego zagrożenia."


class LocalDiagnosticAI(DiagnosticAI):
    """Adapter dla lokalnego modelu AI (np. LLM w GGUF), z deterministycznym fallbackiem."""

    def __init__(
        self,
        fallback_engine: Optional[DiagnosticAI] = None,
        model_runner: Optional[Callable[[str], str]] = None,
    ):
        self.fallback = fallback_engine or RuleBasedDiagnosticAI()
        self.model_runner = model_runner

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
