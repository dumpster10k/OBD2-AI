# AI Car Doctor

Lekka aplikacja mobilna do diagnostyki samochodu przez adapter Bluetooth OBD-II. Projekt wykorzystuje Python, `python-obd` oraz warstwę AI do objaśniania kodów DTC i analizy danych telemetrycznych.

> Projekt jest w fazie rozwoju. Diagnoza AI ma charakter pomocniczy i nie zastępuje mechanika ani dokumentacji serwisowej.

## Funkcje

- odczyt standardowych kodów błędów OBD-II/DTC,
- bezpieczne czyszczenie kodów DTC po potwierdzeniu użytkownika,
- analiza kodów błędów z kontekstem telemetrycznym,
- klasyfikacja pilności problemu,
- obsługa definicji niestandardowych czujników/PID-ów,
- walidacja zakresu wartości czujników,
- przygotowanie pod mobilny interfejs Kivy,
- automatyczne testy i CI z kontrolą coverage.

## Architektura

```text
OBD-II Bluetooth / ELM327
          │
          ▼
   core/obd_client.py       komunikacja z ECU i DTC
          │
          ├── services/ai_engine.py       analiza i rekomendacje AI
          ├── services/sensor_manager.py  niestandardowe czujniki/PID-y
          └── ui/main.py                   interfejs Kivy
```

## Struktura projektu

```text
.
├── core/
│   └── obd_client.py
├── docs/
│   └── diagnostic_ai.md
├── services/
│   ├── ai_engine.py
│   ├── diagnostic_ai.py
│   └── sensor_manager.py
├── ui/
│   └── main.py
├── tests/
│   ├── test_obd.py
│   ├── test_ai.py
│   ├── test_diagnostic_ai.py
│   └── test_sensor_manager.py
├── .github/workflows/ci.yml
├── AGENTS.md
├── CONTRIBUTING.md
└── requirements.txt
```

## Wymagania

- Python 3.12 lub nowszy,
- adapter OBD-II zgodny z ELM327,
- Bluetooth lub inne połączenie obsługiwane przez środowisko,
- Kivy — wymagane tylko do uruchomienia interfejsu mobilnego.

## Instalacja

```bash
git clone https://github.com/dumpster10k/OBD2-AI-.git
cd OBD2-AI-
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
# .venv\\Scripts\\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Testy

Testy nie wymagają podłączonego samochodu ani fizycznego adaptera — komunikacja OBD jest izolowana przez fake connection:

```bash
PYTHONPATH=. python -m pytest -q
```

Coverage:

```bash
PYTHONPATH=. python -m pytest \
  --cov=core --cov=services \
  --cov-report=term-missing \
  --cov-fail-under=80
```

## Uruchomienie interfejsu

Po zainstalowaniu Kivy i sparowaniu adaptera:

```bash
python ui/main.py
```

## Bezpieczeństwo i ograniczenia

- Nie kasuj DTC podczas jazdy. Operację wykonuj na postoju i po zapisaniu kodów oraz danych diagnostycznych.
- Kasowanie błędów może wyzerować readiness monitors i nie usuwa przyczyny usterki.
- Sugestia AI nie jest pewną diagnozą. W przypadku czerwonych kontrolek, przegrzania, niskiego ciśnienia oleju lub nierównej pracy silnika zatrzymaj pojazd i skontaktuj się z serwisem.
- Nie zapisuj kluczy API, danych osobowych ani danych pojazdu w repozytorium.
- Niestandardowe PID-y muszą być zweryfikowane względem konkretnego modelu ECU; nie wysyłaj nieznanych komend sterujących.

## Workflow pracy

- `master` — stabilna gałąź produkcyjna,
- `development` — bieżąca integracja,
- `feature/*`, `fix/*`, `test/*` — prace zadaniowe.

Zmiany powinny trafiać przez Pull Request. Szczegółowe zasady znajdują się w [`AGENTS.md`](AGENTS.md) i [`CONTRIBUTING.md`](CONTRIBUTING.md).

CI uruchamia:

- testy `pytest`,
- coverage z minimalnym progiem 80%,
- build artefaktu źródłowego.

## Licencja

Licencja nie została jeszcze wybrana. Przed publicznym wydaniem dodaj odpowiedni plik `LICENSE`.
