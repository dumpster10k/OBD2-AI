# TODO: wybór modelu AI i hostingu

## Decyzja wstępna

Dla MVP wybieramy **hosting zewnętrzny przez API**, a nie model uruchamiany bezpośrednio na telefonie.

Powód: aplikacja musi najpierw dobrze agregować dane OBD, kody DTC, freeze-frame i historię sesji. Zewnętrzne API daje lepszą jakość odpowiedzi, prostsze aktualizacje modelu i mniejsze wymagania sprzętowe telefonu.

Model AI ma być asystentem diagnostycznym, a nie systemem sterującym ECU. Nie może samodzielnie wykonywać komend kasowania ani komend zapisu do sterowników.

## Shortlista modeli z Hugging Face

Przed wyborem produkcyjnym sprawdzić aktualne licencje, wersje i dostępność:

1. **Qwen2.5-1.5B-Instruct** — kandydat do lokalnego MVP; mały, dobry do klasyfikacji i krótkich objaśnień.
2. **SmolLM2-1.7B-Instruct** — lekki model lokalny do trybu offline i prostych odpowiedzi.
3. **Phi-3.5-mini-instruct** — większy model do lepszych odpowiedzi kontekstowych; wymaga więcej pamięci.
4. **Qwen2.5-3B/7B-Instruct** — wariant serwerowy lub dla mocniejszych urządzeń; lepszy do długich analiz.
5. **Gemma 3 1B/4B Instruct** — kandydat do porównania jakości i kosztu, po sprawdzeniu licencji oraz obsługi języka polskiego.

To są kandydaci do benchmarku, nie automatyczna rekomendacja wdrożenia. Model musi być oceniony na rzeczywistych kodach DTC i danych telemetrycznych.

## Plan hostingu

### Etap 1 — API zewnętrzne

- do modelu wysyłamy tylko znormalizowany kontekst diagnostyczny,
- klucza API nie przechowujemy w aplikacji mobilnej,
- aplikacja komunikuje się z własnym backendem/proxy,
- backend stosuje limity, logowanie bez danych wrażliwych i wersjonowanie promptu,
- przy braku sieci aplikacja nadal pokazuje surowe dane DTC i reguły bezpieczeństwa.

### Etap 2 — model lokalny/offline

- kwantyzowany model 1B–3B w formacie GGUF lub rozwiązaniu wspieranym przez Android,
- inference przez llama.cpp/MLC/LiteRT — wybór po benchmarku na docelowych telefonach,
- lokalny model obsługuje krótkie objaśnienia, klasyfikację i fallback offline,
- brak wysyłania danych auta do sieci w trybie prywatnym.

### Etap 3 — hybryda

- reguły bezpieczeństwa i podstawowa klasyfikacja lokalnie,
- cięższa analiza przez API tylko po zgodzie użytkownika,
- możliwość wyłączenia chmury w ustawieniach.

## Wymagania akceptacyjne

- [ ] Benchmark minimum 100 przypadków DTC.
- [ ] Testy języka polskiego i angielskiego.
- [ ] Ocena: poprawność kodu, ostrożność zaleceń, halucynacje, czas odpowiedzi i koszt.
- [ ] Model nie przedstawia hipotezy jako pewnej diagnozy.
- [ ] Model nie zaleca jazdy przy potencjalnie krytycznych objawach.
- [ ] Model nie generuje bezpośrednio komend zapisu/kodowania ECU.
- [ ] Fallback działa bez internetu.
- [ ] Klucz API znajduje się wyłącznie na backendzie.
- [ ] Sprawdzona licencja modelu i warunki komercyjnego użycia.

## Proponowany interfejs

```python
class DiagnosticAI:
    def analyze(self, vehicle_context: dict) -> dict:
        """Zwraca ustrukturyzowaną hipotezę, pilność i kolejne kroki."""
        raise NotImplementedError
```

Implementacje:

```text
ExternalDiagnosticAI  # backend/API
LocalDiagnosticAI     # model na urządzeniu
RuleBasedFallback     # działanie bez sieci
```

## Następny krok

Przygotować benchmark i adapter `DiagnosticAI`, a następnie porównać Qwen2.5-1.5B, SmolLM2-1.7B oraz Phi-3.5-mini na tych samych danych. Decyzję produkcyjną podjąć dopiero po pomiarach jakości i czasu odpowiedzi.
