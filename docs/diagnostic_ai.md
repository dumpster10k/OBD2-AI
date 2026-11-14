# Silnik Diagnostyczny AI (Offline-First)

## Wprowadzenie

Moduł `services.diagnostic_ai` odpowiada za interpretację kodów usterek OBD-II (DTC) oraz bieżącą telemetrię pojazdu. Głównym założeniem modułu jest **działanie offline-first**, bez konieczności połączenia z chmurą, z priorytetem bezpieczeństwa użytkownika i mechaniki pojazdu.

## Zasady bezpieczeństwa

1. **Brak automatycznego kasowania DTC**: Silnik diagnostyczny nigdy nie inicjuje procedury czyszczenia pamięci ECU (`CLEAR_DTC`). Kasowanie kodów może odbyć się wyłącznie po manualnym potwierdzeniu przez kierowcę na postoju.
2. **Deterministyczny triage**: Triage bezpieczeństwa opiera się na twardych regułach fizycznych (temperatury płynów, napięcie ładowania, wypadanie zapłonów pod obciążeniem).
3. **Status hipotezy**: Wszelkie diagnozy i sugerowane przyczyny są oznaczane jako hipotezy pomocnicze, wymagające weryfikacji przez mechanika przed przystąpieniem do naprawy.

## Architektura modułu

```text
               ┌───────────────────────┐
               │     DiagnosticAI      │ (Interfejs bazowy)
               │ analyze(context)->Rep │
               └───────────▲───────────┘
                           │
             ┌─────────────┴─────────────┐
             │                           │
┌───────────────────────────┐ ┌───────────────────────────┐
│   RuleBasedDiagnosticAI   │ │     LocalDiagnosticAI     │
│  - Standardowa baza DTC   │ │  - Adapter lokalnego LLM  │
│  - Triage telemetryczny   │ │  - Automatyczny fallback  │
│  - Gwarancja braku haluc. │ │    do RuleBasedDiagnostic │
└───────────────────────────┘ └───────────────────────────┘
```

## Poziomy pilności (Urgency)

| Poziom | Stan | Kryteria | Zalecenie dla kierowcy |
|---|---|---|---|
| `critical` | Krytyczny | Ciecz chłodząca >= 115°C, olej >= 130°C, misfire przy RPM > 3000, napięcie < 10.5V, błędy magistrali (np. P0600) | **Natychmiast zatrzymaj pojazd w bezpiecznym miejscu i wyłącz silnik.** Jazda grozi zniszczeniem silnika lub katalizatora. |
| `warning` | Ostrzeżenie | Kody DTC układu zapłonowego/zasilania (P0300, P0171, ECT), ciecz >= 105°C, napięcie < 11.8V | Bezpieczna jazda z ograniczoną prędkością do warsztatu; unikaj wysokich obrotów. |
| `info` | Informacyjny | Kody o niskiej pilności (np. P0420 - sprawność katalizatora), kody nieznane | Rutynowa kontrola przy najbliższym przeglądzie. |

## Przykład użycia

### 1. Użycie RuleBasedDiagnosticAI

```python
from services.diagnostic_ai import RuleBasedDiagnosticAI

engine = RuleBasedDiagnosticAI()

context = {
    "dtc_codes": ["P0300", "P0171"],
    "rpm": 2200,
    "coolant_temp_c": 92.0,
    "voltage": 13.8,
}

report = engine.analyze(context)

print(f"Pilność: {report.overall_urgency}")
print(f"Można jechać: {report.safe_to_drive}")
print(f"Podsumowanie: {report.summary}")
for warning in report.safety_warnings:
    print(f"- Uwaga: {warning}")
for step in report.next_steps:
    print(f"- Krok: {step}")
```

### 2. Użycie przez AIEngine

Klasa `services.ai_engine.AIEngine` integruje silnik `RuleBasedDiagnosticAI`:

```python
from services.ai_engine import AIEngine

ai = AIEngine()
report = ai.analyze_context({
    "dtc_codes": ["P0301"],
    "rpm": 3500,  # Wysokie obroty + misfire -> pilność krytyczna!
})

assert report.safe_to_drive is False
assert report.overall_urgency == "critical"
```

### 3. Użycie z lokalnym modelem AI (GGUF / Ollama)

```python
from services.diagnostic_ai import LocalDiagnosticAI

def my_local_llm_runner(prompt: str) -> str:
    # Wywołanie lokalnego modelu inference (np. llama.cpp)
    return "Zalecana zamiana cewek cylindra 1 i 2 w celu potwierdzenia usterki."

local_ai = LocalDiagnosticAI(model_runner=my_local_llm_runner)
report = local_ai.analyze({"dtc_codes": ["P0301"]})
```
