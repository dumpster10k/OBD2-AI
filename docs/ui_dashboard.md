# Interfejs Mobilny i Pulpit Telemetrii (Kivy UI)

Dokumentacja architektury interfejsu użytkownika, kontrolera stanu oraz protokołów bezpieczeństwa w aplikacji **AI Car Doctor**.

---

## 1. Architektura UI

Interfejs rozdziela logikę biznesową od warstwy renderowania widżetów:

```text
               ┌───────────────────────────┐
               │    DashboardController    │  (Logika biznesowa & stan)
               │ - refresh_telemetry()     │  (core/obd_client.py, services/ai_engine.py)
               │ - scan_dtc_and_diagnose() │
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
│  - Panel raportu AI       │ │  - Środowiska CI / testy  │
│  - Asystent głosowy       │ │  - Działa bez Kivy        │
│  - Dwuetapowe kasowanie   │ └───────────────────────────┘
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

## 3. Panel raportu diagnostycznego AI

Raport generowany po kliknięciu `🔍 Skanuj błędy OBD i diagnozuj AI`:
- **Wskaźnik zdatności do jazdy** (`safe_to_drive`): `TAK` / `NIE (Zatrzymaj pojazd!)`.
- **Wskaźnik pilności** (`overall_urgency`): `INFO`, `WARNING`, `CRITICAL`.
- **Zalecenia warsztatowe**: Usystematyzowana lista pierwszych kroków naprawczych.
- **Klauzula pomocnicza**: Każdy raport zawiera obowiązkowe zastrzeżenie:
  > *Uwaga: Diagnoza ma charakter pomocniczy i wymaga weryfikacji warsztatowej.*

---

## 4. Dwuetapowa procedura kasowania DTC

Zgodnie z wymogami bezpieczeństwa pojazdu (pkt 7 `AGENTS.md`) kasowanie kodów usterek podlega ścisłemu protokołowi:

1. **Weryfikacja postoju**:
   - Sprawdzenie prędkości pojazdu (`speed == 0`).
   - W przypadku wykrycia ruchu (`speed > 0`) żądanie jest natychmiast odrzucane z komunikatem ostrzegawczym.
2. **Krok 1 (Inicjacja)**:
   - Kliknięcie `Skasuj kody błędów DTC` przełącza stan na `dtc_clear_pending = True`.
   - Przycisk zmienia etykietę na `⚠️ POTWIERDŹ KASOWANIE NA POSTOJU`.
3. **Krok 2 (Potwierdzenie i archiwizacja)**:
   - Ponowne kliknięcie weryfikuje warunek postoju.
   - Kody DTC wraz z bieżącą telemetrią są utrwalane w logu audytowym sesji (`session_log`).
   - Wysłanie komendy `CLEAR_DTC` do sterownika ECU.
   - Odświeżenie widoku i wyczyszczenie aktywnego raportu.

---

## 5. Obsługa asystenta głosowego

Przycisk `🎙️ Asystent głosowy (Zapytaj AI)` uruchamia integrację z `VoiceDiagnosticAssistant`:
- Obsługa mowy kierowcy w trybie głośnomówiącym.
- Ochrona przed kasowaniem błędów głosem (asystent odmawia i instruuje o wymogu potwierdzenia manualnego na postoju).
- Synteza odpowiedzi przez lokalny model TTS (Piper).
