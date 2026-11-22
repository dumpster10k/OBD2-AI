# Interfejs Mobilny i Pulpit Telemetrii (Kivy UI)

Dokumentacja architektury interfejsu użytkownika, kontrolera stanu, modułu wykresów i symulatora awarii w aplikacji **AI Car Doctor**.

---

## 1. Architektura UI

Interfejs rozdziela logikę biznesową od warstwy renderowania widżetów:

```text
               ┌───────────────────────────┐
               │    DashboardController    │  (Logika biznesowa & stan)
               │ - refresh_telemetry()     │  (core/obd_client.py, services/ai_engine.py)
               │ - scan_dtc_and_diagnose() │  - bufor historii próbkowania
               │ - enable_simulation()     │  - silnik scenariuszy awarii
               │ - request_clear_dtc()     │
               │ - confirm_clear_dtc()     │
               │ - handle_voice_input()    │
               └─────────────┬─────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
┌───────────────────────────┐ ┌───────────────────────────┐
│        CarDoctorUI        │ │        WidgetStub         │
│  - Karty telemetrii       │ │  - Bezpieczny fallback    │
│  - Wykresy trendów        │ │  - Środowiska CI / testy  │
│  - Symulator usterek      │ │  - Działa bez Kivy        │
│  - Panel raportu AI       │ └───────────────────────────┘
│  - Asystent głosowy       │
│  - Dwuetapowe kasowanie   │
└───────────────────────────┘
```

### Izolacja środowiskowa (Headless / CI-ready)
W przypadku braku biblioteki Kivy w środowisku uruchomieniowym (np. serwery CI, kontenery Docker) moduł `ui/main.py` automatycznie inicjalizuje atrapy `WidgetStub`. Umożliwia to 100% pokrycie testami logiki kontrolera bez konieczności uruchamiania serwera graficznego X11/Wayland.

---

## 2. Pulpit telemetrii na żywo

Pulpit pobiera znormalizowane metryki z magistrali OBD-II przez `OBDClient.get_telemetry()`:

| Parametr | Jednostka | Komenda OBD-II | Wartość domyślna / Fallback |
|---|---|---|---|
| **Obroty silnika** (`rpm`) | RPM | `obd.commands.RPM` | `0` |
| **Prędkość pojazdu** (`speed`) | km/h | `obd.commands.SPEED` | `0` |
| **Temperatura cieczy** (`coolant_temp`) | °C | `obd.commands.COOLANT_TEMP` | `0` |
| **Napięcie akumulatora** (`voltage`) | V | `obd.commands.ELM_VOLTAGE` | `12.6` (przy braku odczytu) |

Błędy odczytu pojedynczych PID-ów są izolowane — awaria sensora napięcia nie blokuje odczytu obrotów ani prędkości.

---

## 3. Wykresy przebiegu parametrów (`TelemetryChart`)

Moduł wizualizacji trendów czasowych umożliwia bieżącą analizę dynamiki parametrów silnika:
- **Bufor próbkowania**: automatyczny bufor kroczący (do 50 ostatnich próbek) dla parametrów `rpm`, `speed`, `coolant_temp` oraz `voltage`.
- **Wielokanałowy przełącznik**: szybkie zakładki `[ RPM ]`, `[ KM/H ]`, `[ TEMP ]`, `[ VOLT ]`.
- **Pasek statystyk**: dynamiczny podgląd wartości bieżącej, minimalnej i maksymalnej w oknie czasowym.
- **Dynamiczne kolory linii**:
  - Obroty i prędkość: Electric Cyan (`#06B6D4`),
  - Temperatura płynu: zielony (`< 105°C`), bursztynowy (`105-114°C`), ostrzegawczy czerwony (`>= 115°C`),
  - Napięcie: zielony (`>= 11.8V`), bursztynowy (`< 11.8V`).

---

## 4. Symulator usterek i scenariusze demonstracyjne (Demo Mode)

Aplikacja pozwala na pełne testowanie i demonstrację diagnostyki AI bez konieczności podłączania fizycznego samochodu:

| Identyfikator | Nazwa scenariusza | Kody DTC | Telemetria początkowa |
|---|---|---|---|
| `clean` | **Normalna praca (OK)** | brak | 850 RPM, 0 km/h, 89 °C, 14.2 V |
| `misfire` | **Wypadanie zapłonów** | `P0300`, `P0301` | 2800 RPM, 65 km/h, 93 °C, 13.9 V |
| `overheat` | **Przegrzanie silnika** | `P0217` (Krytyczny) | 2200 RPM, 40 km/h, 119 °C, 13.4 V |
| `lean_mix` | **Uboga mieszanka / MAF** | `P0171`, `P0101` | 1950 RPM, 55 km/h, 88 °C, 14.0 V |
| `low_voltage` | **Niskie napięcie akumulatora** | `P0562` | 0 RPM, 0 km/h, 65 °C, 11.1 V |

Kliknięcie przycisku scenariusza natychmiast ładuje wirtualny stan pojazdu, aktualizuje pulpit telemetrii oraz uruchamia analizę AI.

---

## 5. Panel raportu diagnostycznego AI

Raport generowany po kliknięciu `🔍 Skanuj błędy OBD i diagnozuj AI`:
- **Wskaźnik zdatności do jazdy** (`safe_to_drive`): `TAK` / `NIE (Zatrzymaj pojazd!)`.
- **Wskaźnik pilności** (`overall_urgency`): `INFO`, `WARNING`, `CRITICAL`.
- **Zalecenia warsztatowe**: Usystematyzowana lista pierwszych kroków naprawczych.
- **Klauzula pomocnicza**: Każdy raport zawiera obowiązkowe zastrzeżenie:
  > *Uwaga: Diagnoza ma charakter pomocniczy i wymaga weryfikacji warsztatowej.*

---

## 6. Dwuetapowa procedura kasowania DTC

Zgodnie z wymogami bezpieczeństwa pojazdu (pkt 7 `AGENTS.md`) kasowanie kodów usterek podlega ścisłemu protokołowi:

1. **Weryfikacja postoju**:
   - Sprawdzenie prędkości pojazdu (`speed == 0`).
   - W przypadku wykrycia ruchu (`speed > 0`) żądanie jest natychmiast odrzucane z komunikatem ostrzegawczym.
2. **Krok 1 (Inicjacja)**:
   - Kliknięcie `Skasuj kody błędów DTC` przełącza stan na `dtc_clear_pending = True`.
   - Przycisk zmienia etykietę na `⚠️ POTWIERDŹ KASOWANIE NA POSTOJU` i kolor na ostrzegawczą czerwień.
3. **Krok 2 (Potwierdzenie i archiwizacja)**:
   - Ponowne kliknięcie weryfikuje warunek postoju.
   - Kody DTC wraz z bieżącą telemetrią są utrwalane w logu audytowym sesji (`session_log`).
   - Wysłanie komendy `CLEAR_DTC` do ECU (lub wyczyszczenie wirtualnych kodów w symulatorze).
   - Odświeżenie widoku i zresetowanie aktywnego raportu.

---

## 7. Obsługa asystenta głosowego

Przycisk `🎙️ Asystent głosowy (Zapytaj AI)` uruchamia integrację z `VoiceDiagnosticAssistant`:
- Obsługa mowy kierowcy w trybie głośnomówiącym.
- Ochrona przed kasowaniem błędów głosem (asystent odmawia i instruuje o wymogu potwierdzenia manualnego na postoju).
- Synteza odpowiedzi przez lokalny model TTS (Piper).
