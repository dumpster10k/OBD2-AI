# AI Car Doctor

Lekka aplikacja mobilna i desktopowa do diagnostyki samochodu przez adapter Bluetooth OBD-II. Projekt wykorzystuje Python, `python-obd` oraz warstwę AI do objaśniania kodów DTC i analizy danych telemetrycznych.

## Funkcje

- odczyt standardowych kodów błędów OBD-II/DTC,
- bezpieczne czyszczenie kodów DTC po potwierdzeniu użytkownika,
- analiza kodów błędów z kontekstem telemetrycznym,
- obsługa niestandardowych czujników/PID-ów,
- eksport sesji diagnostycznych do CSV, Excel (`.xlsx`) i PDF,
- automatyczne testy i CI z kontrolą coverage.

## Eksport danych

`ExportService` przyjmuje listę rekordów telemetrycznych, np.:

```python
from services.export_service import ExportService

rows = [{"timestamp": "2026-01-01T12:00:00Z", "rpm": 850, "coolant_c": 90}]
service = ExportService()
service.export_csv(rows, "reports/session.csv")
service.export_excel(rows, "reports/session.xlsx")
service.export_pdf(rows, "reports/session.pdf")
```

Eksport PDF jest raportem czytelnym dla człowieka, CSV nadaje się do dalszej analizy, a XLSX do pracy w Excelu lub LibreOffice.

## Instalacja

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Testy

Testy nie wymagają samochodu ani adaptera:

```bash
PYTHONPATH=. python -m pytest -q
PYTHONPATH=. python -m pytest --cov=core --cov=services --cov-report=term-missing --cov-fail-under=80
```

## Workflow

- `master` — stabilna wersja produkcyjna,
- `development` — integracja,
- `feature/*` — pojedyncze funkcje.

Zmiany wprowadzamy przez Pull Request. Szczegółowe zasady znajdują się w `AGENTS.md` i `CONTRIBUTING.md`.
