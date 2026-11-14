# Zasady dla agentów

## 1. Branching

- `master` jest gałęzią stabilną i release'ową.
- `development` jest gałęzią integracyjną.
- Każde zadanie realizuj na osobnej gałęzi utworzonej z aktualnego `development`.
- Nazewnictwo: `feature/<nazwa>`, `fix/<nazwa>`, `test/<nazwa>` lub `docs/<nazwa>`.
- Nie commituj bezpośrednio do `master` ani `development`.

## 2. Praca przed commitem

1. Pobierz aktualny kod: `git fetch origin`.
2. Zaktualizuj gałąź bazową.
3. Uruchom testy lokalnie:
   `PYTHONPATH=. python -m pytest -q --cov=. --cov-report=term-missing`.
4. Sprawdź format i jakość zmienionych plików.
5. Nie dodawaj sekretów, tokenów, plików `.env`, cache ani artefaktów builda.

## 3. Commity

Stosuj Conventional Commits:

- `feat:` nowa funkcjonalność
- `fix:` poprawka błędu
- `test:` testy
- `refactor:` refaktoryzacja bez zmiany zachowania
- `docs:` dokumentacja
- `ci:` konfiguracja CI/CD
- `chore:` prace techniczne

Zasady:

- Jeden commit powinien reprezentować jedną logiczną zmianę.
- Tytuł w trybie rozkazującym, maksymalnie 72 znaki.
- Nie używaj commitów typu `update`, `changes`, `misc` bez konkretnego opisu.
- Commituj test razem z funkcjonalnością, której dotyczy.

## 4. Pull Request

Każda zmiana trafia przez PR:

- feature/fix/test/docs -> `development`
- `development` -> `master` wyłącznie jako PR release'owy

PR musi zawierać:

- opis problemu i rozwiązania,
- zakres zmian,
- listę wykonanych testów,
- wynik coverage i informację o zmianie coverage,
- ryzyka oraz wpływ na OBD/AI/UI,
- instrukcję ręcznego testu, jeśli zmiana dotyczy sprzętu lub UI.

PR nie może być mergowany, gdy wymagany check CI jest czerwony, testy nie przechodzą albo występują nierozwiązane uwagi review.

## 5. Testy i coverage

- Testy jednostkowe nie mogą wymagać fizycznego adaptera OBD.
- Połączenie z OBD testuj przez mocki/fake connection.
- Każdy nowy moduł powinien mieć testy ścieżki poprawnej i błędnej.
- Kod produkcyjny nie może obniżać coverage bez uzasadnienia w PR.
- Minimalny cel coverage: 80% dla kodu Python objętego testami.
- Coverage nie jest wymówką do testowania kodu UI lub integracji sprzętowej wyłącznie jednostkowo; takie przypadki opisz jako testy ręczne/integracyjne.

## 6. CI status checks

Wymagane checki PR:

- `test` — instalacja zależności i pełny pytest,
- `coverage` — raport coverage i weryfikacja minimum 80%,
- `build` — utworzenie artefaktu źródłowego.

Mergowanie jest dozwolone wyłącznie po przejściu wszystkich wymaganych checków. Jeśli CI nie uruchomiło się, agent nie oznacza PR jako gotowego — należy ponowić workflow lub zgłosić problem.

## 7. Bezpieczeństwo aplikacji

- Kasowanie DTC wymaga jawnego potwierdzenia użytkownika i zapisu kodów przed operacją.
- AI może sugerować diagnozę, ale nie może przedstawiać jej jako pewnej bez potwierdzenia.
- Nie wysyłaj danych pojazdu ani kluczy API do logów.
- Dynamiczne PID-y muszą przejść walidację odpowiedzi, zakresu i dozwolonego trybu ECU.
