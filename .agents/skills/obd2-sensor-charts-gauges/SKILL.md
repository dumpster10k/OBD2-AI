---
name: obd2-sensor-charts-gauges
description: Projektowanie i implementacja wizualizacji parametrów OBD-II, wskaźniki zegarowe (circular gauges / dials), wykresy przebiegu (trend charts), obliczanie średnich, wartości min/max oraz interpretacja zakresów optymalnych, ostrzegawczych i krytycznych. Użyj, gdy użytkownik lub agent chce dodać wykres, zegar tarczowy, zweryfikować optymalny zakres sensora lub przeanalizować średnie wartości telemetrii.
---

# Wizualizacja danych OBD-II: Wskaźniki zegarowe, wykresy i analiza optymalnych zakresów

Instrukcja dla agentów AI dotycząca implementowania wskaźników tarczowych (zegarowych), wykresów trendu czasowego oraz ewaluacji optymalnych i granicznych parametrów pracy silnika przy użyciu modułu `services/telemetry_metrics.py` oraz biblioteki Kivy.

---

## 1. Wybór formy prezentacji danych

| Typ wizualizacji | Kiedy stosować | Zalety | Przykładowe parametry |
|---|---|---|---|
| **Wskaźnik zegarowy (Circular Gauge / Dial)** | Szybki odczyt stanu bieżącego jednym rzutem oka | Kierowca natychmiast widzi położenie wskazówki w strefie zielonej/żółtej/czerwonej | Obroty (RPM), prędkość (km/h), ciśnienie doładowania (Boost) |
| **Wykres trendu czasowego (Trend Chart)** | Analiza dynamiki i zmian w czasie | Ujawnia narastanie problemu (np. powolny wzrost temperatury pod obciążeniem) | Temperatura cieczy (ECT), napięcie akumulatora (V), temperatura oleju |
| **Karta liczbowa z min/max i średnią** | Precyzyjna inspekcja statystyczna | Pokazuje skrajne wartości bez konieczności ciągłej obserwacji | Spadki napięcia przy rozruchu, maksymalne obroty, średnia prędkość |

---

## 2. Baza parametrów optymalnych (`MetricThresholds`)

W module `services/telemetry_metrics.py` zdefiniowano ujednoliconą bazę progów roboczych silnika:

| Parametr (`metric_id`) | Zakres optymalny (Zielony) | Zakres ostrzegawczy (Bursztynowy) | Próg krytyczny (Czerwony) |
|---|---|---|---|
| **`coolant_temp`** | `85.0°C – 98.0°C` | `99.0°C – 114.0°C` | `≥ 115.0°C` (Ryzyko przegrzania / uszkodzenia UPG) |
| **`voltage`** | `13.6 V – 14.6 V` | `11.8 V – 13.5 V` lub `14.7 V – 15.4 V` | `< 10.5 V` (Brak zasilania) lub `≥ 15.5 V` (Przeładowanie) |
| **`rpm`** | `750 – 3200 RPM` | `5500 – 6499 RPM` | `≥ 6500 RPM` (Redline / odcięcie paliwa) |
| **`oil_temp`** | `85.0°C – 105.0°C` | `106.0°C – 129.0°C` | `≥ 130.0°C` (Degradacja filmu olejowego) |
| **`boost_pressure`** | `0.0 – 1.6 bar` | `1.7 – 2.1 bar` | `≥ 2.2 bar` (Przeładowanie turbiny / Overboost) |

### Ocena statusu parametru w kodzie:
```python
from services.telemetry_metrics import evaluate_metric_status

status = evaluate_metric_status("coolant_temp", 102.5)
# Zwraca: 'warning'
```

---

## 3. Matematyka wskaźnika zegarowego (Circular Gauge)

Standardowa tarcza wskaźnika w motoryzacji operuje na kącie **270°**:
- Kąt początkowy: `-135°` (godzina ~7:30 — wartość minimalna),
- Kąt środkowy: `0°` (godzina 12:00 — 50% skali),
- Kąt końcowy: `+135°` (godzina ~4:30 — wartość maksymalna).

### A. Obliczanie kąta wskazówki:
```python
from services.telemetry_metrics import value_to_gauge_angle

angle = value_to_gauge_angle(value=2500, min_val=0, max_val=8000)
# Zwraca: -50.6°
```

### B. Obliczanie współrzędnych końca wskazówki:
Dla środka tarczy `(cx, cy)` i promienia wskazówki `r_needle`:
```python
import math

rad = math.radians(90.0 - angle)  # Konwersja kąta nawigacyjnego na trygonometryczny
needle_x = cx + (r_needle * math.cos(rad))
needle_y = cy + (r_needle * math.sin(rad))
```

### C. Kolorowanie łuku skali (Zone Arcs w Kivy Canvas):
- **Strefa zielona (Optimal)**: od kąta wartości `optimal_min` do `optimal_max`.
- **Strefa żółta (Warning)**: od `warning_low`/`warning_high`.
- **Strefa czerwona (Critical)**: powyżej progu krytycznego do końca skali.

---

## 4. Wykres liniowy trendu (Linear Trend Chart)

Wykres trendu (np. `TelemetryChart` w `ui/main.py`) opiera się na buforze kroczącym próbek:

```python
from services.telemetry_metrics import calculate_series_stats

# Pobranie ostatnich 50 próbek parametru
samples = [88.0, 89.0, 91.0, 94.0, 92.0]
stats = calculate_series_stats(samples)

print(f"Bieżąca: {stats['current']} | Średnia: {stats['avg']} | Min: {stats['min']} | Max: {stats['max']}")
```

### Zasady skalowania osi pionowej (Y):
1. Wyznacz `val_min = min(samples)` i `val_max = max(samples)`.
2. Dodaj margines 10% (padding), aby linia nie dotykała krawędzi karty.
3. Jeśli `val_max == val_min`, ustaw sztuczny zakres `[val_min - 1, val_max + 1]`.
4. Wylicz współrzędną Y każdego punktu:
   `y = plot_y + ((sample - val_min) / (val_max - val_min)) * plot_h`

---

## 5. Implementacja Kivy i kompatybilność z CI (Headless)

Przy tworzeniu widżetów rysujących canvas w Kivy pamiętaj o izolacji środowiskowej:

```python
from ui.main import KIVY_AVAILABLE, WidgetStub

if KIVY_AVAILABLE:
    from kivy.uix.widget import Widget
    from kivy.graphics import Color, Line, Ellipse
else:
    Widget = WidgetStub

class DialGaugeWidget(Widget):
    def update_value(self, val: float):
        if not KIVY_AVAILABLE:
            return  # W środowisku testowym CI unikaj odwołań do canvas
        # Logika redraw canvas
```

---

## 6. Checklist dodawania nowego wskaźnika lub wykresu

- [ ] Zarejestruj progi w `STANDARD_METRIC_THRESHOLDS` (lub upewnij się, że parametr istnieje).
- [ ] Zapewnij bufor historii próbkowania w `DashboardController.telemetry_history`.
- [ ] Zweryfikuj, że wykres/zegar nie crashuje w środowisku CI bez Kivy (`WidgetStub`).
- [ ] Dodaj test jednostkowy weryfikujący obliczenia statystyk i kątów (`tests/test_telemetry_metrics.py`).
