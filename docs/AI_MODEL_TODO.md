# TODO: lokalny model AI na urządzeniu

## Decyzja architektoniczna

Aplikacja działa w trybie **offline-first**, bez płatnego hostingu chmurowego, z modelem AI uruchamianym lokalnie na telefonie lub laptopie.

Dane pojazdu nie są wysyłane do chmury, a repozytorium nie zawiera kluczy API. Opcjonalne połączenie internetowe może służyć wyłącznie do ręcznej aktualizacji bazy definicji DTC lub PID-ów za zgodą użytkownika.

## Strategia lokalna

Wdrożenie opiera się na warstwie deterministycznej uzupełnionej o model mowy i językowy:

1. parser kodów DTC,
2. lokalna baza definicji i opisów,
3. deterministyczny triage bezpieczeństwa (`RuleBasedDiagnosticAI`),
4. lekki lokalny LLM do objaśniania usterki i dialogu z użytkownikiem,
5. asystent głosowy kierowcy (STT/TTS hands-free).

Lokalny LLM nie podejmuje decyzji o kasowaniu DTC ani nie wysyła komend zapisu/kodowania do ECU.

## Rekomendowane modele

Modele oceniane pod kątem efektywności mobilnej:

1. **SmolLM2-360M-Instruct** (GGUF Q4_K_M) — ultra-lekki (~230 MB), uruchamiany na każdym smartfonie.
2. **Qwen2.5-0.5B-Instruct** (GGUF Q4_K_M) — zbalansowany model mobilny (~350 MB).
3. **Qwen2.5-1.5B-Instruct** (GGUF Q4_K_M) — wysoka dokładność techniczna i język polski (~980 MB).
4. **Whisper Tiny (ONNX)** — szybkie rozpoznawanie mowy (~75 MB).
5. **Piper TTS (ONNX)** — natychmiastowa synteza mowy w języku polskim (~28 MB).

## Format i środowisko uruchomieniowe

- Format modeli: **GGUF** (Q4_K_M) oraz **ONNX**.
- Środowisko: `llama-cpp-python` / `llama.cpp` oraz `piper-tts` / `onnxruntime`.
- Architektura: adapter `LocalLLMEngine` oraz `SpeechService` izolowane za interfejsami, nieblokujące wątku UI.

## Pamięć i profile urządzeń

| Profil | Model | Zastosowanie |
|---|---|---|
| **Android Lite** | 135M–360M, Q4 | Podstawowe wyjaśnienia DTC na starszych telefonach |
| **Android Standard** | 0.5B–1.5B, Q4 | Analiza kontekstu telemetrii i dialog techniczny |
| **Desktop / Laptop** | 1.5B–3B, Q4 | Pełne raporty diagnostyczne i asystent |
| **Fallback** | brak LLM | Silnik regułowy `RuleBasedDiagnosticAI` (zawsze dostępny) |

## Wymagania akceptacyjne

- [x] Podstawowa analiza i triage działają całkowicie offline (`RuleBasedDiagnosticAI`).
- [x] Fallback regułowy działa niezawodnie w przypadku braku zainstalowanego LLM.
- [x] Zaimplementowano interfejs `LocalLLMEngine` z obsługą runnera GGUF i mocków testowych.
- [x] Zintegrowano moduły mowy offline (`SpeechService`, STT Whisper/Vosk, TTS Piper).
- [x] Wdrożono asystenta głosowego `VoiceDiagnosticAssistant` z blokadą kasowania błędów głosem.
- [x] Każda odpowiedź modelu zawiera obligatoryjną klauzulę o pomocniczym charakterze diagnozy.
- [x] Model nie generuje komend zapisu/kodowania ECU.
- [x] Deterministyczne reguły fizyczne (temperatura, ładowanie) nadrzędnie wyznaczają stan krytyczny.
- [x] Zintegrowano pulpit mobilny Kivy z obsługą asystenta głosowego i telemetrii.
- [ ] Test benchmarkowy na zestawie 100 rzeczywistych zamrożonych ramek DTC.
- [ ] Pomiary czasu inferencji, zużycia RAM i baterii na urządzeniu ARM64.
- [ ] Paczkowanie wag modeli jako opcjonalnego zasobu pobieranego na żądanie.

## Zrealizowana architektura

```text
RuleBasedDiagnosticAI    # silnik regułowy (zawsze dostępny, gwarancja braku halucynacji)
LocalDiagnosticAI        # adapter lokalnego modelu AI
LocalLLMEngine           # obsługa kompaktowych modeli GGUF (SmolLM2-360M, Qwen2.5-0.5B/1.5B)
SpeechService            # obsługa mowy STT (Whisper/Vosk) oraz TTS (Piper)
VoiceDiagnosticAssistant # bezdotykowy asystent kierowcy
DashboardController      # kontroler integrujący telemetrię, raporty AI i asystenta z UI
```
