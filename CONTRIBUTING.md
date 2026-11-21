# Contributing

Zasady wytwarzania kodu, konwencje commitów oraz architekturę opisuje dokument [`AGENTS.md`](AGENTS.md).

## Procedura kontrybucji

1. Utwórz gałąź roboczą (`feature/*`, `fix/*`, `docs/*`) z aktualnego stanu `development`.
2. Zaimplementuj zmiany wraz z testami jednostkowymi.
3. Wykonaj lokalną weryfikację jakości:
   ```bash
   PYTHONPATH=. python -m pytest --cov=core --cov=services --cov-report=term-missing --cov-fail-under=80
   ```
4. Otwórz Pull Request do gałęzi `development`, wypełniając szablon zgłoszenia.
