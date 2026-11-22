---
name: obd2-actuator-output-tests
description: Testowanie elementów wykonawczych (Output Tests / Basic Settings / Nastawy podstawowe), np. zawory N80 (EVAP), N75 (wastegate/doładowanie), silniczki klap nagrzewnicy/klimatyzacji Climatronic (V70, V68, V71, V85 w Audi A4 B6 / VAG), przekaźnik pompy paliwa J17, wentylatory chłodnicy. Obsługa protokołów VAG KWP1281/KWP2000 (Funkcja 03 Stellgliedtest, Funkcja 04 Grundeinstellung), UDS 0x2F (InputOutputControlByIdentifier) oraz standardowego OBD-II Mode 08. Rygorystyczne procedury bezpieczeństwa (blokady obrotów, prędkości, watchdog czasowy, awaryjne zatrzymanie).
---

# Testowanie elementów wykonawczych i nastawy podstawowe (Actuator Output Tests & Basic Settings)

Przewodnik dla agentów AI dotyczący implementacji, diagnozowania i wykonywania testów podzespołów wykonawczych (Output Tests / Stellgliedtest) oraz procedur nastaw podstawowych (Basic Settings / Grundeinstellung) w stylu oprogramowania Ross-Tech VCDS / VAS, ze szczególnym uwzględnieniem platformy VAG (np. Audi A4 B6 / B7, Passat B5, Golf 4/5) oraz uniwersalnych standardów OBD-II (Mode 08) i UDS (Service 0x2F).

---

## 1. Architektura i protokoły sterowania podzespołami

| Standard / Protokół | Funkcja diagnostyczna | Zastosowanie | Sposób działania |
|---|---|---|---|
| **VAG KWP1281 / KWP2000** | **Funkcja 03 (Stellgliedtest)** | Sterowniki silnika (01), Climatronic (08), liczniki (17), ABS (03) | ECU sekwencyjnie lub selektywnie wysterowuje cewki, przekaźniki i silniczki krokiem testowym. |
| **VAG KWP1281 / KWP2000** | **Funkcja 04 (Grundeinstellung)** | Kalibracja i adaptacja krańcowych położeń (np. klap nawiewu, przepustnicy) | Sterownik bada skrajne napięcia potencjometrów zwrotnych i zapisuje wartości w pamięci EEPROM. |
| **UDS (ISO 14229)** | **Service 0x2F (`InputOutputControlByIdentifier`)** | Nowsze pojazdy VAG (od platformy Golf 6 / Audi A4 B8) oraz CAN | Precyzyjne sterowanie wartością zadaną (duty cycle %, stan ON/OFF, freeze). |
| **Standard OBD-II** | **Mode 08 (On-Board System Test)** | Każdy pojazd zgodny z normą EOBD / OBD-II | Wymuszenie testu szczelności oparów EVAP (PID `01`) lub odcięcia wtryskiwaczy. |

---

## 2. Kluczowe podzespoły wykonawcze (Studium przypadku: Audi A4 B6)

### A. Sterownik silnika (`01 - Engine`, ECU ME7.5 / EDC15 / EDC16)
1. **Zawór N80 (EVAP Purge Valve)**:
   - *Rola*: Elektrozawór odpowietrzania zbiornika paliwa (usuwanie par benzyny przez filtr z węglem aktywnym).
   - *Objaw uszkodzenia*: Trudny rozruch po tankowaniu do pełna, syczenie z wlewu paliwa, błędy `P0441` (Incorrect Purge Flow), cykanie lub brak cykania.
   - *Procedura testowa*: Wysterowanie cewki impulsami 10 Hz przez 15–20 s. Operator powinien usłyszeć wyraźne, głośne rytmiczne klikanie w komorze silnika w okolicy obudowy filtra powietrza.
2. **Zawór N75 (Wastegate / VNT Boost Solenoid)**:
   - *Rola*: Sterowanie podciśnieniem gruszki turbosprężarki (zawór wastegate w 1.8T lub zmienna geometria VNT w 1.9 TDI).
   - *Objaw uszkodzenia*: Notlauf (przeładowanie / niedoładowanie, błąd `P0299` lub `P0234`).
   - *Procedura testowa*: Cykliczne przełączanie zaworu (0% -> 100% duty cycle co 3 sekundy). Operator obserwuje płynny skok sztangi turbiny o długości ok. 10–12 mm.
3. **Przekaźnik pompy paliwa J17 / Pompa paliwa**:
   - *Procedura*: Wymuszenie pracy pompy na 15 sekund przy zgaszonym silniku. Pozwala zweryfikować ciśnienie w szynie oraz ciągłość obwodu elektrycznego bez kręcenia rozrusznikiem.
4. **Wentylatory chłodnicy V7 / V177**:
   - *Procedura*: Załączenie 1. biegu (wolny) i 2. biegu (szybki) celem wykrycia przepalonych opornic lub uszkodzonego modułu sterownika wentylatorów.

### B. Sterownik klimatyzacji (`08 - Auto HVAC / Climatronic` 8E0 820 043)
Typowa usterka w Audi A4 B6 objawia się terkoczącymi silniczkami za konsolą środkową i schowkiem oraz nierównomiernym nawiewem ciepłego/zimnego powietrza:
1. **Silniczki klap i potencjometry zwrotne**:
   - **V70**: Silnik klapy centralnej (potencjometr **G92**).
   - **V68**: Silnik klapy regulacji temperatury lewa/główna (potencjometr **G112**).
   - **V71**: Silnik klapy spiętrzania / obiegu zamkniętego (potencjometr **G113**).
   - **V85**: Silnik klapy nawiewu na nogi / odmrażania (potencjometr **G114**).
   - **V107**: Silnik klapy odmrażacza szyby przedniej.
2. **Test podzespołów (Funkcja 03)**:
   - Sterownik po kolei uruchamia nawiew z pełną mocą, kompresor (zawór regulacyjny N280 lub sprzęgło N25) oraz każdy silniczek klapy od skrajności do skrajności.
3. **Nastawy podstawowe / Adaptacja klap (Funkcja 04, Kanał 001)**:
   - Sterownik wykonuje pełny cykl kalibracyjny: wszystkie silniczki poruszają się w skrajne pozycje (min i max).
   - Sterownik odczytuje wartości rezystancji z potencjometrów (zakres surowy ~0–255 lub 0–5 V).
   - Prawidłowy koniec procedury: wszystkie 4 pola wartości schodzą do **0** (kalibracja zakończona sukcesem).

### C. Zestaw wskaźników (`17 - Instruments / Kombiinstrument`)
- **Procedura testowa licznika**:
  - Test wskazówek: płynne przejście na 100% skali, a następnie powrót i zatrzymanie dokładnie na środku (3000 RPM, 100 km/h, 90°C, 1/2 zbiornika paliwa).
  - Test wyświetlacza FIS: pełne zapalenie wszystkich pikseli / segmentów.
  - Test brzęczyka (gong / buzzer ostrzegawczy).

---

## 3. Rygorystyczny protokół bezpieczeństwa (Pre-flight Safety Checks)

Wykonywanie testów elementów wykonawczych w poruszającym się pojeździe lub przy uruchomionym silniku stwarza **poważne ryzyko wypadku, pożaru lub uszkodzenia mechanicznego**!

### A. Wymagane warunki początkowe (Hard Safety Interlocks)
Każdy test musi przejść procedurę `ActuatorSafetyPreflight`:
1. **Prędkość pojazdu**: `vehicle_speed == 0.0 km/h` (bezwzględny postój).
2. **Obroty silnika**: `engine_rpm == 0` (Ignition ON, Engine OFF — zgaszony silnik z włączonym zapłonem).
   - *Wyjątek*: Specyficzne testy dynamiczne (np. adaptacja przepustnicy na ciepłym biegu jałowym), gdzie wymagana jest zaciągnięta dźwignia hamulca ręcznego i `vehicle_speed == 0.0`.
3. **Napięcie akumulatora**: `battery_voltage >= 12.0 V`.
   - Zabezpieczenie przed spadkiem zasilania podczas wysterowywania cewek i wentylatorów, co mogłoby zawiesić ECU.
4. **Brak krytycznych błędów czujników położenia** (dla procedury nastaw podstawowych).

### B. Zabezpieczenia w trakcie trwania testu (Runtime Guards)
1. **Watchdog Timeout**:
   - Maksymalny czas trwania pojedynczego testu (np. 15–30 sekund).
   - Po upływie czasu system **automatycznie** wysyła ramkę resetującą sterowanie (np. UDS `0x2F ... 0x00` - Return Control To ECU).
   - Zapobiega to przegrzaniu i stopieniu cewki (np. elektrozaworu N80/N75) w przypadku utraty połączenia Bluetooth/USB.
2. **Przycisk natychmiastowego przerwania (Emergency Abort)**:
   - Dostępny na pierwszym planie UI w trakcie całego testu.
   - Wysłanie ramki zatrzymującej w < 50 ms od kliknięcia.
3. **Natychmiastowe przerwanie w razie detekcji obrotów lub ruchu**:
   - Jeśli w trakcie testu `engine_rpm > 200` lub `vehicle_speed > 0`, test jest natychmiastowo przerywany.

---

## 4. Przykładowa implementacja silnika testów (`services/actuator_testing.py`)

### A. Model danych testu podzespołu:
```python
from dataclasses import dataclass
from typing import Optional, Callable


@dataclass
class ActuatorTestDefinition:
    test_id: str  # Unikalne ID, np. "vag_n80_purge_valve"
    name: str  # Czytelna nazwa: "Zawór N80 (EVAP)"
    target_ecu: str  # "01", "08", "17" lub "7E0"
    protocol: str  # "KWP1281", "KWP2000", "UDS_2F", "OBD_MODE_08"
    command_payload: str  # Hex polecenia diagnostycznego (np. "2F11220301")
    reset_payload: str  # Hex przywrócenia kontroli ECU (np. "2F112200")
    duration_sec: float  # Czas trwania testu (np. 15.0 s)
    description: str  # Opis komponentu
    operator_instruction: str  # Wskazówka: "Posłuchaj klikania przy filtrze powietrza"
    requires_engine_off: bool = True  # Warunek rpm == 0
    min_voltage: float = 12.0  # Minimalne napięcie akumulatora
```

### B. Weryfikacja warunków bezpieczeństwa (Pre-flight):
```python
class ActuatorSafetyPreflight:
    @staticmethod
    def verify(telemetry: dict, test: ActuatorTestDefinition) -> tuple[bool, str]:
        speed = telemetry.get("speed", 0.0)
        rpm = telemetry.get("rpm", 0)
        voltage = telemetry.get("voltage", 12.4)

        if speed > 0.0:
            return False, f"Pojazd jest w ruchu ({speed} km/h). Test dozwolony wyłącznie na postoju!"

        if test.requires_engine_off and rpm > 50:
            return False, f"Silnik pracuje ({rpm} RPM). Wymagany zgaszony silnik z włączonym zapłonem!"

        if voltage < test.min_voltage:
            return False, f"Zbyt niskie napięcie akumulatora ({voltage:.1f} V < {test.min_voltage} V)!"

        return True, "Warunki bezpieczeństwa spełnione."
```

### C. Zakończenie i raportowanie:
Po wykonaniu testu operator otrzymuje prompt ewaluacyjny:
- *Czy słyszałeś wyraźne klikanie zaworu N80?* [TAK / NIE]
- *Czy sztanga gruszki N75 poruszała się płynnie w całym zakresie?* [TAK / NIE]
- *Czy dmuchawa wkręciła się na maksymalne obroty?* [TAK / NIE]
Wynik testu wraz ze statusem telemetrii (napięcie, data, VIN) zapisywany jest w logu sesji (`TelemetryLogger`).

---

## 5. Wytyczne dla testów jednostkowych (Izolacja sprzętowa)

Zgodnie z regułą **AGENTS.md pkt 5**, wszystkie testy muszą być w 100% odizolowane od fizycznego interfejsu diagnostycznego:
- Stosuj mocki klasy `OBDClient` i `FakeConnection`.
- Testuj:
  1. Odrzucenie wykonania testu przy `vehicle_speed > 0` lub `rpm > 0`.
  2. Pomyślne przejście pre-flight checks przy poprawnych warunkach.
  3. Działanie watchdog timeoutu i wysłanie ramki resetującej `reset_payload`.
  4. Funkcję Emergency Abort.
  5. Parsowanie i interpretację odpowiedzi sterownika (pozytywne potwierdzenie `0x6F` / `0x7F` negative response).
