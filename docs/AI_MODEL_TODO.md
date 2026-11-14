# TODO: lokalny model AI na urządzeniu

## Decyzja architektoniczna

Docelowo aplikacja działa **offline-first**, bez płatnego hostingu, z modelem AI uruchamianym lokalnie na telefonie lub laptopie.

Nie przechowujemy kluczy API w aplikacji i nie wysyłamy danych pojazdu do chmury. Internet może być używany opcjonalnie wyłącznie do aktualizacji modeli, bazy DTC lub definicji PID-ów po zgodzie użytkownika.

## Strategia lokalna

Najpierw implementujemy diagnostykę deterministyczną:

1. parser DTC,
2. lokalna baza kodów i opisów,
3. reguły bezpieczeństwa,
4. analiza freeze-frame,
5. dopiero potem lokalny LLM do wyjaśniania i rozmowy z użytkownikiem.

LLM nie podejmuje decyzji o kasowaniu DTC ani nie wysyła komend zapisu do ECU.

## Kandydaci do benchmarku

Modele należy pobrać i ocenić zgodnie z aktualną licencją Hugging Face:

1. **Qwen2.5-1.5B-Instruct** — główny kandydat dla Androida; dobry kompromis rozmiaru i jakości.
2. **SmolLM2-1.7B-Instruct** — alternatywa dla słabszych telefonów.
3. **Gemma 3 1B** — mały kandydat do porównania jakości i języka polskiego.
4. **Phi-3.5-mini-instruct** — opcja dla laptopów i mocniejszych telefonów; prawdopodobnie zbyt ciężka jako domyślna wersja Android.
5. **Qwen2.5-3B-Instruct** — opcja desktopowa lub dla urządzeń z większą pamięcią.

To shortlist, a nie ostateczna decyzja. Przed użyciem trzeba sprawdzić licencję, wymagania i jakość języka polskiego.

## Format i uruchamianie

Preferowany format modelu:

```text
GGUF + kwantyzacja Q4_K_M lub podobna
```

Kierunek implementacji:

- Android: natywny runtime wspierający Android/ARM64, np. llama.cpp lub MLC-LLM,
- Windows/Linux: llama.cpp, llama-cpp-python lub podobny runtime,
- Python/Kivy: adapter `LocalDiagnosticAI`, który komunikuje się z runtime bez blokowania UI.

Nie zakładamy, że `llama-cpp-python` będzie łatwo kompilować się bezpośrednio w każdym APK. Runtime powinien być izolowany za interfejsem, aby można go było zmienić bez przebudowy logiki diagnostycznej.

## Pamięć i tryby urządzeń

| Tryb | Model | Zastosowanie |
|---|---|---|
| Android Lite | 1B–1.5B, Q4 | krótkie objaśnienia DTC, pytania użytkownika |
| Android Standard | 1.5B–3B, Q4 | analiza kontekstu i prosty dialog |
| Laptop | 3B–7B, Q4/Q5 | dłuższe raporty i analiza historii |
| Fallback | brak LLM | reguły, baza DTC i szablony odpowiedzi |

Model nie musi analizować surowego strumienia w każdej próbce. Telemetria powinna być agregowana lokalnie do cech, np. średnia, minimum, maksimum, trend i zdarzenia.

## Prywatność

- dane OBD pozostają na urządzeniu,
- historia diagnostyki jest lokalna w SQLite,
- logi nie zawierają VIN ani pełnych danych pojazdu bez zgody,
- aktualizacja modelu jest ręczna lub podpisana,
- aplikacja działa bez internetu,
- użytkownik może usunąć model i całą historię.

## Wymagania akceptacyjne

- [ ] Aplikacja wykonuje podstawową analizę bez internetu.
- [ ] Fallback reguł działa bez zainstalowanego LLM.
- [ ] Test benchmarkowy zawiera minimum 100 przypadków DTC.
- [ ] Model nie przedstawia hipotezy jako pewnej diagnozy.
- [ ] Model nie generuje komend zapisu/kodowania ECU.
- [ ] Triage krytycznych przypadków wykonują reguły, nie sam LLM.
- [ ] Zmierzono czas odpowiedzi, RAM, temperaturę i baterię.
- [ ] APK działa na minimum dwóch urządzeniach ARM64.
- [ ] Sprawdzono licencję i możliwość dystrybucji modelu.
- [ ] Model jest dystrybuowany osobno lub jako opcjonalny pakiet, aby nie powiększać podstawowego APK.

## Następny krok

Zaimplementować interfejs:

```python
class DiagnosticAI:
    def analyze(self, vehicle_context: dict) -> dict:
        raise NotImplementedError
```

oraz trzy implementacje:

```text
RuleBasedDiagnosticAI  # zawsze dostępny, bez modelu
LocalDiagnosticAI      # model na urządzeniu
HybridDiagnosticAI     # opcjonalnie później, bez wymaganego hostingu
```

Pierwszy cel: działający `RuleBasedDiagnosticAI` i benchmark lokalny, a dopiero potem integracja Qwen2.5-1.5B lub SmolLM2.
