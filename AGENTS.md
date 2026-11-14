# Zasady dla agentów

## 1. Branching

- `master` stanowi stabilną gałąź wydawniczą (release).
- `development` stanowi gałąź integracyjną.
- Każde zadanie realizuj na dedykowanej gałęzi utworzonej z aktualnego stanu `development`.
- Stosuj konwencję nazewnictwa: `feature/<nazwa>`, `fix/<nazwa>`, `test/<nazwa>` lub `docs/<nazwa>`.
- Wszelkie commity umieszczaj wyłącznie na dedykowanej gałęzi zadaniowej.

## 2. Praca przed commitem

1. Pobierz aktualny kod: `git fetch origin`.
2. Zaktualizuj gałąź bazową względem `origin/development`.
3. Uruchom lokalną bramkę weryfikacyjną:
   `PYTHONPATH=. python -m pytest --cov=core --cov=services --cov-report=term-missing --cov-fail-under=80`.
4. Zweryfikuj format i jakość zmienionych plików.
5. Do repozytorium dołączaj wyłącznie pliki źródłowe; sekrety, tokeny, środowiska lokalne i artefakty builda izoluj w `.gitignore`.

## 3. Commity

Stosuj standard Conventional Commits:

- `feat:` nowa funkcjonalność
- `fix:` poprawka błędu
- `test:` testy
- `refactor:` refaktoryzacja zachowująca istniejące zachowanie
- `docs:` dokumentacja
- `ci:` konfiguracja CI/CD
- `chore:` zadania techniczne i utrzymaniowe

Zasady tworzenia commitów:

- Jeden commit reprezentuje dokładnie jedną logiczną zmianę.
- Tytuł pisz w trybie rozkazującym, o długości do 72 znaków.
- Tytuł commita musi jednoznacznie określać cel i zakres modyfikacji.
- Zmiany w kodzie commituj łącznie z testami, które je weryfikują.

## 4. Pull Request

Wszystkie zmiany integruj przez Pull Request:

- `feature/*`, `fix/*`, `test/*`, `docs/*` kieruj do gałęzi `development`.
- PR do gałęzi `master` otwieraj wyłącznie jako release z `development`.

Zawartość wymaganego opisu PR:

- opis problemu i zastosowanego rozwiązania,
- zakres zmian (zgodny z checklistą PR template),
- wykaz wykonanych testów oraz uzyskany wynik coverage,
- wpływ i potencjalne ryzyka dla modułów OBD, AI oraz UI,
- procedura testu manualnego w przypadku zmian sprzętowych lub UI.

Warunkiem zatwierdzenia i scalenia PR jest zielony status wszystkich checków CI oraz rozwiązanie wszystkich uwag z review.

## 5. Testy i bramka coverage

- Testy jednostkowe realizuj w pełnej izolacji od sprzętu fizycznego, z użyciem mocków i fake connections.
- Każdy moduł pokrywaj testami ścieżki pozytywnej oraz obsługi błędów i stanów brzegowych.
- Utrzymuj pokrycie kodu testami na minimalnym poziomie 80% dla modułów `core` i `services`.
- Dla kodu UI oraz integracji sprzętowej przygotuj procedurę testów integracyjnych/manualnych.

## 6. Status checks w CI

Wymagane automatyczne checki weryfikacyjne:

- `test` — instalacja zależności i pomyślne wykonanie całego zestawu pytest,
- `coverage` — potwierdzenie osiągnięcia progu minimum 80% pokrycia,
- `build` — poprawne wygenerowanie pakietu źródłowego.

W przypadku braku automatycznego uruchomienia CI ponów workflow lub zgłoś problem przed uznaniem zadania za zakończone.

## 7. Bezpieczeństwo pojazdu i danych

- Kasowanie błędów DTC wykonuj wyłącznie po manualnym potwierdzeniu przez użytkownika na postoju i uprzednim utrwaleniu kodów w logu sesji.
- Wszystkie analizy AI oznaczaj jako hipotezy pomocnicze wymagające weryfikacji warsztatowej.
- W logach, telemetrii i zgłoszeniach chroń prywatność: maskuj numery VIN, dane personalne oraz klucze dostępowe.
- Niestandardowe parametry PID poddawaj ścisłej walidacji pod kątem typu odpowiedzi, dozwolonego zakresu wartości i trybu ECU.
