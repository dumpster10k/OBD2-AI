---
name: obd2-sensor-authoring
description: Dodawanie i definiowanie nowych czujników OBD-II oraz niestandardowych parametrów PID w SensorManager. Użyj, gdy użytkownik lub agent chce dodać nowy sensor (np. temperatura oleju, ciśnienie doładowania, EGT, DPF, temperatura skrzyni biegów), zdefiniować formułę dekodowania bajtów (A, B, C, D) lub zweryfikować zakresy fizyczne.
---

# Dodawanie nowych czujników OBD-II (Sensor Authoring)

Instrukcja dla agentów AI dotycząca definiowania i integrowania nowych sensorów w module `services/sensor_manager.py` oraz `core/obd_client.py`.

---

## 1. Struktura definicji sensora (`SensorDefinition`)

Każdy sensor w systemie opisany jest klasą `SensorDefinition`:

```python
from services.sensor_manager import SensorDefinition, SensorManager

sensor = SensorDefinition(
    name="Engine Oil Temp",           # Unikalna, czytelna nazwa parametru
    mode="22",                        # Tryb OBD-II ("01" = standard, "22" = rozszerzony/UDS)
    pid="1126",                       # Identyfikator parametru (Hex bez 0x)
    formula="(A*256 + B)/10",         # Formuła matematyczna dekodowania bajtów
    unit="°C",                        # Jednostka fizyczna
    min_value=-40.0,                  # Minimalna dopuszczalna wartość (walidacja)
    max_value=160.0,                  # Maksymalna dopuszczalna wartość (walidacja)
    description="Temperatura oleju silnikowego",
    ecu_target="7E0",                 # Opcjonalny docelowy adres modułu (domyślnie 7E0 silnik)
)
```

---

## 2. Tryby OBD-II (Modes / Services)

Wybierz odpowiedni tryb w zależności od typu pojazdu i czujnika:

| Tryb | Zastosowanie | Długość PID | Przykłady |
|---|---|---|---|
| **Mode 01** | Standardowe parametry SAE J1979 (działają w każdym aucie OBD-II) | 1 bajt (2 znaki hex) | `0C` (RPM), `0D` (Speed), `05` (Coolant), `04` (Load), `0B` (MAP) |
| **Mode 22** | Rozszerzone parametry producenta (UDS / ISO 14229) | 2 bajty (4 znaki hex) | `1126` (Oil Temp VAG), `1155` (Boost), `1E50` (ATF Temp), `2010` (DPF Soot) |
| **Mode 02** | Parametry zamrożone (Freeze Frame PIDs) | 1 bajt | Parametry silnika zapisane w chwili zarejestrowania błędu DTC |

---

## 3. Składnia formuł dekodowania bajtów

Formuły w `SensorManager` są bezpiecznie parsowane przez AST (brak ryzykownego `eval`). Obsługiwane zmienne i operatory:

- **Zmienne**: `A` (bajt 1), `B` (bajt 2), `C` (bajt 3), `D` (bajt 4).
- **Operatory**: `+`, `-`, `*`, `/`, `**` oraz nawiasy `()`.

### Typowe wzorce formuł:
1. **Pojedynczy bajt ze skalowaniem liniowym**:
   - `A` — prędkość w km/h, ciśnienie MAP w kPa.
   - `A - 40` — temperatury (np. płyn chłodzący, powietrze dolotowe) w °C.
   - `A / 2.55` — procenty 0-100% (np. obciążenie silnika, otwarcie przepustnicy, poziom paliwa).
2. **Dwa bajty ze skalowaniem 16-bitowym**:
   - `(A*256 + B) / 4` — obroty silnika (RPM).
   - `(A*256 + B) / 10` — temperatura oleju / spalin z precyzją do 0.1°C.
   - `(A*256 + B) * 0.01` — ciśnienie doładowania w barach lub masa sadzy w gramach.
   - `(A*256 + B) / 1000` — napięcie modułu w woltach (V).

---

## 4. Procedura dodania nowego czujnika przez agenta

Gdy użytkownik prosi o dodanie nowego sensora (np. ciśnienie paliwa CR):

1. **Zidentyfikuj tryb, PID i formułę**:
   - Sprawdź specyfikację OBD-II lub bazę producenta (np. Mode 01 PID 23: Fuel Rail Pressure, formuła `(A*256 + B)*10`, jednostka `kPa`, zakres `0` do `655350`).
2. **Zarejestruj sensor w `SensorManager`**:
   ```python
   manager = SensorManager.with_defaults()
   manager.add_sensor(
       SensorDefinition(
           name="Fuel Rail Pressure",
           mode="01",
           pid="23",
           formula="(A*256 + B)*10",
           unit="kPa",
           min_value=0,
           max_value=655350,
           description="Ciśnienie paliwa na szynie Common Rail",
       )
   )
   ```
3. **Przetestuj obliczenia i walidację zakresów**:
   ```python
   # Przykład: bajty [0x01, 0xF4] -> (1*256 + 244)*10 = 5000 kPa = 50 bar
   calculated = manager.evaluate_raw("Fuel Rail Pressure", [0x01, 0xF4])
   assert calculated == 5000.0
   assert manager.validate_value("Fuel Rail Pressure", calculated) is True
   ```
4. **Napisz test jednostkowy** w `tests/test_sensor_manager.py` weryfikujący dodany sensor.

---

## 5. Reguły bezpieczeństwa (AGENTS.md pkt 7)

- **Ścisła walidacja typu i zakresu**: Zawsze definiuj `min_value` i `max_value`, aby wykluczyć uszkodzone ramki lub błędy transmisji szyny CAN.
- **Niestandardowe parametry PID**: Przed dodaniem sensora upewnij się, że tryb (`mode`) nie jest trybem diagnostycznym modyfikującym pamięć ECU (np. brak komend zapisu Mode 2E/3D w warstwie odczytu telemetrii).
