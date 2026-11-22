# Wbudowane modele AI (Offline-First)

Moduł AI w **AI Car Doctor** działa w trybie **offline-first**, zapewniając pełną prywatność danych diagnostycznych pojazdu (brak wysyłania ramek telemetrycznych, numeru VIN czy lokalizacji do chmury).

Architektura opiera się na dwóch uzupełniających się filarach:
1. **Lokalny model główny (LLM)** — wyjaśnianie usterki, generowanie zaleceń i dialog techniczny.
2. **Lokalne modele mowy (Speech AI - STT & TTS)** — bezpieczna obsługa bezdotykowa w trakcie jazdy (hands-free).

---

## 1. Główny model diagnostyczny (Lekki LLM)

Do objaśniania usterki i dialogu technicznego przygotowano dedykowane adaptery (`services/llm_engine.py`) wspierające format **GGUF** (np. przez `llama.cpp` / `llama-cpp-python`):

| Model | Rozmiar wag | Pamięć RAM | Kwantyzacja | Zastosowanie |
|---|---|---|---|---|
| **SmolLM2 360M Instruct** | ~230 MB | ~512 MB | Q4_K_M | Starsze / budżetowe smartfony z małą ilością pamięci. |
| **Qwen2.5 0.5B Instruct** | ~350 MB | ~700 MB | Q4_K_M | Domyślny ultra-lekki model mobilny o wysokiej kulturze technicznej. |
| **Qwen2.5 1.5B Instruct** | ~980 MB | ~1.8 GB | Q4_K_M | Standardowe telefony i laptopy; znakomite objaśnienia w języku polskim. |

### Kluczowe zasady bezpieczeństwa LLM:
* Wszystkie odpowiedzi modelu opatrzone są klauzulą: `Uwaga: Diagnoza ma charakter pomocniczy i wymaga weryfikacji warsztatowej.`
* Model nie podejmuje decyzji o krytyczności — triage krytyczny (np. temperatura cieczy chłodzącej > 115°C, napięcie < 10.5V) zawsze realizuje deterministyczny silnik `RuleBasedDiagnosticAI`.
* Model ma zablokowaną możliwość sugerowania samodzielnego kasowania błędów w czasie jazdy.

---

## 2. Modele mowy (Speech AI)

Interfejs mowy (`services/speech_service.py`) pozwala na bezdotykową obsługę asystenta kierowcy:

### A. Rozpoznawanie mowy (Speech-to-Text — STT)
* **Whisper Tiny (ONNX)** — waga ~75 MB, RAM ~200 MB, wielojęzyczny z obsługą PL.
* **Vosk Small PL** — waga ~45 MB, RAM ~120 MB, zoptymalizowany pod polską mowę na systemach wbudowanych / Android.

### B. Synteza mowy (Text-to-Speech — TTS)
* **Piper TTS Polish (Darkman / Gosia Medium)** — waga ~28 MB, RAM ~80 MB w formacie ONNX. Szybka synteza w czasie rzeczywistym bezpośrednio na CPU urządzenia.

---

## 3. Asystent głosowy kierowcy (`VoiceDiagnosticAssistant`)

Przepływ przetwarzania zapytania:

```text
[Głos kierowcy / Mikrofon] 
       │
       ▼
 [STT: Whisper / Vosk / AudioRecorder]
       │
       ▼
[Klasyfikacja intencji (VoiceIntent) i ochrona bezpieczeństwa]
       ├── "Skasuj błędy" ──────────► ODMOWA GŁOSOWA (wymóg manualnego potwierdzenia na postoju!)
       ├── "Czy mogę jechać?" ──────► Analiza zdatności do jazdy (DiagnosticAI)
       ├── "Jaka temperatura?" ─────► Odczyt telemetrii ECT (°C) i ocena ryzyka przegrzania
       ├── "Napięcie / bateria" ────► Odczyt napięcia instalacji (V) i diagnoza ładowania
       ├── "Prędkość i RPM" ────────► Odczyt prędkości (km/h) i obrotów silnika
       ├── "Jakie mam błędy?" ──────► Raport zarejestrowanych kodów DTC
       ├── "Wyjaśnij błąd P0300" ───► Interpretacja kodu DTC z bazy STANDARD_DTC_DATABASE
       ├── "Pomoc / komendy" ───────► Podsumowanie dostępnych poleceń bezdotykowych
       ├── "Co z autem?" ───────────► Całościowy raport stanu technicznego pojazdu
       └── Zapytanie techniczne ────► LocalLLMEngine (z kontekstem pojazdu i telemetrii)
       │
       ▼
 [TTS: Piper TTS ONNX] ──► [Komunikat głosowy WAV / Odtwarzanie audio]
```

### Obsługiwane polecenia głosowe
| Intencja | Przykładowe frazy | Źródło danych / Reakcja |
|---|---|---|
| `CLEAR_DTC` | "Skasuj błędy", "Wyczyść błędy", "Kasuj" | **Odmowa**. Zgodnie z punktem 7 `AGENTS.md` kasowanie wymaga zatrzymania pojazdu i potwierdzenia manualnego. |
| `SAFE_TO_DRIVE` | "Czy mogę jechać dalej?", "Czy bezpiecznie dojadę?" | Analiza telemetrii i kodów DTC (`DiagnosticAI.analyze()`). |
| `COOLANT_TEMP` | "Jaka jest temperatura płynu?", "Czy silnik się grzeje?" | Odczyt PID ECT z oceną progową (<105°C norma, 105-114°C podwyższona, >=115°C krytyczna). |
| `VOLTAGE` | "Jakie jest napięcie akumulatora?", "Stan baterii" | Odczyt napięcia instalacji (<11.8V niskie, 11.8-15.0V norma, >15.0V przeładowanie). |
| `SPEED_RPM` | "Z jaką prędkością jadę?", "Jakie mam obroty?" | Zestawienie prędkości (km/h) i prędkości obrotowej silnika (RPM). |
| `DTC_STATUS` | "Jakie mam błędy?", "Czy są jakieś usterki?" | Odczyt aktywnych kodów błędów ze sterownika ECU. |
| `DTC_EXPLAIN` | "Wyjaśnij błąd P0300", "Co oznacza kod P0171?" | Szybkie wyjaśnienie usterki, przyczyn i zaleceń z bazy wiedzy. |
| `HELP` | "Pomoc", "Co potrafisz?", "Jakie są komendy?" | Przegląd dostępnych poleceń asystenta mowy. |
| `VEHICLE_HEALTH` | "Co z autem?", "Jaki jest stan pojazdu?" | Całościowe podsumowanie diagnostyczne. |
| `GENERAL_LLM` | Dowolne inne pytania motoryzacyjne | Przetwarzanie przez lokalny LLM z wstrzykniętym kontekstem pojazdu. |

