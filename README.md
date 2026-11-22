# AI Car Doctor

Lekka aplikacja mobilna do diagnostyki samochodu przez adapter Bluetooth OBD-II. Projekt wykorzystuje Python, `python-obd` oraz lokalne modele AI do objaśniania kodów DTC, analizy telemetrii i bezdotykowego dialogu z kierowcą.

> Diagnoza AI ma charakter pomocniczy i nie zastępuje mechanika ani dokumentacji serwisowej.

---

## Funkcje

- **Odczyt i analiza DTC**: automatyczna identyfikacja kodów usterek z bazy OBD-II.
- **Pulpit telemetrii na żywo**: podgląd RPM, prędkości, temperatury płynu chłodzącego i napięcia akumulatora.
- **Triage bezpieczeństwa**: ocena zdatności do jazdy (`safe_to_drive`) oraz poziomu pilności (`overall_urgency`).
- **Lokalne modele AI (offline-first)**: wsparcie dla kompaktowych modeli LLM (GGUF) bez wysyłania danych do chmury.
- **Asystent głosowy kierowcy**: obsługa bezdotykowa mowy (STT Whisper/Vosk, TTS Piper).
- **Bezpieczne dwuetapowe kasowanie DTC**: blokada kasowania w trakcie jazdy (`speed > 0`), manualne potwierdzenie na postoju i audyt w logu sesji.
- **Niestandardowe czujniki**: menedżer niestandardowych parametrów PID z walidacją zakresu.
- **Gotowość do testów i CI**: architektura `WidgetStub` umożliwiająca testowanie interfejsu bez serwera graficznego.

---

## Architektura

```text
OBD-II Bluetooth / ELM327
          │
          ▼
   core/obd_client.py       komunikacja z ECU, odczyt DTC i telemetria
          │
          ├── services/diagnostic_ai.py   deterministyczny triage i reguły
          ├── services/ai_engine.py       fasada diagnostyczna
          ├── services/llm_engine.py      lokalny model LLM (offline GGUF)
          ├── services/speech_service.py  mowa offline (STT Whisper, TTS Piper)
          ├── services/sensor_manager.py  niestandardowe PID-y
          └── ui/main.py                  kontroler i mobilny pulpit Kivy
```

---

## Dokumentacja szczegółowa

Wyczerpujące specyfikacje modułów znajdują się w katalogu [`docs/`](docs/):

- [`docs/diagnostic_ai.md`](docs/diagnostic_ai.md) — reguły triage'u, poziomy pilności, bezpieczeństwo i fallbacki.
- [`docs/ai_models.md`](docs/ai_models.md) — wbudowane modele LLM (GGUF) oraz modele mowy (STT/TTS).
- [`docs/ui_dashboard.md`](docs/ui_dashboard.md) — architektura pulpitu Kivy, kontroler telemetrii i procedura kasowania DTC.
- [`docs/AI_MODEL_TODO.md`](docs/AI_MODEL_TODO.md) — plan i status wdrożenia modeli na urządzeniach fizycznych.

---

## Struktura projektu

```text
.
├── core/
│   └── obd_client.py           # klient OBD-II i pobieranie telemetrii
├── docs/
│   ├── ai_models.md            # specyfikacja modeli LLM i mowy
│   ├── AI_MODEL_TODO.md        # checklist wdrożeniowy AI
│   ├── diagnostic_ai.md        # reguły diagnostyczne i triage
│   └── ui_dashboard.md         # architektura interfejsu Kivy
├── services/
│   ├── ai_engine.py            # orkiestracja diagnostyki AI
│   ├── diagnostic_ai.py        # silnik regułowy i adapter LLM
│   ├── llm_engine.py           # obsługa modeli GGUF
│   ├── sensor_manager.py       # niestandardowe PID-y i formuły
│   └── speech_service.py       # obsługa STT i TTS
├── ui/
│   └── main.py                 # DashboardController i CarDoctorUI
├── tests/
│   ├── test_ai.py
│   ├── test_diagnostic_ai.py
│   ├── test_llm_engine.py
│   ├── test_obd.py
│   ├── test_sensor_manager.py
│   ├── test_speech_service.py
│   └── test_ui.py
├── .github/workflows/ci.yml
├── AGENTS.md                   # zasady pracy agentów i konwencje
├── CONTRIBUTING.md
└── requirements.txt
```

---

## Wymagania

- Python 3.12 lub nowszy,
- Adapter OBD-II zgodny z ELM327 (Bluetooth / USB / Wi-Fi),
- Kivy 2.3+ (wymagane wyłącznie do wyświetlania interfejsu graficznego; logika działa w trybie headless).

---

## Instalacja

```bash
git clone https://github.com/dumpster10k/OBD2-AI.git
cd OBD2-AI
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

## Testy i weryfikacja

Testy nie wymagają podłączonego pojazdu ani adaptera OBD (pełna izolacja przez mocki):

```bash
# Uruchomienie zestawu testów
PYTHONPATH=. python -m pytest -q

# Weryfikacja bramki coverage (min. 80%)
PYTHONPATH=. python -m pytest \
  --cov=core --cov=services --cov=ui \
  --cov-report=term-missing \
  --cov-fail-under=80
```

---

## Uruchomienie aplikacji

```bash
python ui/main.py
```

---

## Bezpieczeństwo i zasady

- **Kasowanie DTC**: dozwolone wyłącznie na postoju pojazdu (`speed == 0`) po manualnym potwierdzeniu kierowcy i utrwaleniu kodów w logu sesji.
- **Charakter analizy**: wszelkie diagnozy stanowią hipotezy pomocnicze wymagające weryfikacji warsztatowej.
- **Prywatność**: telemetria, kody błędów i numery VIN nie są przesyłane do chmury.

---

## Workflow pracy

Wszystkie prace developerskie realizowane są na dedykowanych gałęziach według zasad w [`AGENTS.md`](AGENTS.md):
- `master` — stabilna gałąź wydawnicza,
- `development` — gałąź integracyjna,
- `feature/*`, `fix/*`, `docs/*` — gałęzie zadaniowe integrowane przez Pull Request.
