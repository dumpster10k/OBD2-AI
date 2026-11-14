# Contributing

Szczegółowe zasady dla agentów i deweloperów znajdują się w [`AGENTS.md`](AGENTS.md).

## Minimalny proces

```bash
git fetch origin
git checkout development
git pull --ff-only origin development
git checkout -b feature/my-change
python -m pip install -r requirements.txt
PYTHONPATH=. python -m pytest -q --cov=. --cov-report=term-missing
git add .
git commit -m "feat: opis zmiany"
git push -u origin feature/my-change
```

Następnie otwórz PR do `development` i poczekaj na wymagane status checks.
