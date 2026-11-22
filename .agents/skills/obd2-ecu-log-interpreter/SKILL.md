---
name: obd2-ecu-log-interpreter
description: Interpretacja surowych logów i ramek diagnostycznych z ECU / adaptera ELM327. Użyj, gdy użytkownik przekazuje zrzut komunikacji OBD-II, surowe ramki hex (np. 41 0C 1A F8, 43 02 03 00), kody błędów DTC, ramki zamrożone (Freeze Frames) lub pyta, co oznacza odpowiedź sterownika.
---

# Interpretacja logów i ramek diagnostycznych ECU (ELM327 / OBD-II)

Instrukcja dla agentów AI dotycząca analizowania, dekodowania i interpretowania surowych zrzutów komunikacji z magistrali pojazdu przy użyciu modułu `services/ecu_interpreter.py`.

---

## 1. Architektura ramki OBD-II / ELM327

Odpowiedź ze sterownika na zapytanie OBD-II składa się z Service ID, PID i bajtów danych:

```text
[Żądanie testera]       01 0C          (Mode 01, PID 0C - Obroty silnika)
[Odpowiedź ECU]        41 0C 1A F8    (41 = Mode 01 OK, PID 0C, Dane = 1A F8)
```

### Relacja kodów Service ID (SID):
| Żądanie | Odpowiedź pozytywna | Typ operacji |
|---|---|---|
| `01` | `41` | Bieżące parametry telemetrii silnika |
| `02` | `42` | Zamrożona ramka błędu (Freeze Frame) |
| `03` | `43` | Aktywne kody usterek (DTCs) |
| `04` | `44` | Kasowanie kodów DTC (Clear Diagnostic Info) |
| `07` | `47` | Oczekujące kody usterek (Pending DTCs) |
| `0A` | `4A` | Trwałe kody usterek (Permanent DTCs) |
| `22` | `62` | Rozszerzone parametry UDS (Manufacturer PIDs) |

---

## 2. Dekodowanie kodów błędów DTC (Mode 03 / 07 / 0A)

Ramka odpowiedzi na komendę `03` zawiera pary bajtów kodujące usterki:
Przykład: `43 02 03 00 01 71`

### Algorytm dekodowania 2 bajtów na kod DTC (SAE J2012):
1. **Pierwszy znak (litera)** — bity 7-6 pierwszego bajtu:
   - `00` -> **P** (Powertrain — układ napędowy / silnik / skrzynia)
   - `01` -> **C** (Chassis — podwozie / ABS / ESP)
   - `10` -> **B** (Body — karoseria / klimatyzacja / poduszki SRS)
   - `11` -> **U** (Network — sieć CAN / komunikacja między modułami)
2. **Druga cyfra** — bity 5-4 pierwszego bajtu:
   - `0` (zgodny ze standardem ISO/SAE) lub `1-3` (specyficzny dla producenta).
3. **Kolejne 3 cyfry**:
   - Bity 3-0 pierwszego bajtu oraz cały drugi bajt w formacie szesnastkowym (Hex).

### Przykład:
- Bajty `0x03` (`0000 0011`) i `0x00`:
  - Bity 7-6 = `00` -> `P`
  - Bity 5-4 = `00` -> `0`
  - Bity 3-0 = `0011` -> `3`
  - Drugi bajt = `0x00` -> `00`
  - Wynik: **`P0300`** (Wypadanie zapłonów).

---

## 3. Negatywne kody odpowiedzi (NRC - Negative Response Codes)

Gdy sterownik odrzuca komendę, zwraca ramkę zaczynającą się od `7F`:
Format: `7F [Żądany_Mode] [Kod_NRC]`

| Kod NRC | Nazwa standardowa | Znaczenie w praktyce |
|---|---|---|
| `7F 01 11` | `Service Not Supported` | Sterownik nie obsługuje danego trybu. |
| `7F 01 12` | `SubFunction Not Supported` | Nieobsługiwany podtryb lub PID. |
| `7F 22 22` | `Conditions Not Correct` | Warunki nie zostały spełnione (np. silnik nie pracuje lub zbyt wysoka prędkość). |
| `7F 22 31` | `Request Out Of Range` | Żądany PID Mode 22 nie istnieje w tym sterowniku. |
| `7F 27 33` | `Security Access Denied` | Brak autoryzacji bezpieczeństwa (wymagany Seed & Key). |

---

## 4. Narzędzia Pythona w projekcie (`services/ecu_interpreter.py`)

Do automatycznej analizy logów używaj gotowych funkcji:

```python
from services.ecu_interpreter import (
    decode_dtc_frame,
    decode_pid_response,
    parse_raw_ecu_log,
    format_log_summary,
)

# 1. Dekodowanie pojedynczej ramki DTC
codes = decode_dtc_frame("43 02 03 00 01 71")
# Zwraca: ['P0300', 'P0171']

# 2. Dekodowanie odpowiedzi PID
frame = decode_pid_response("01", "0C", "41 0C 1A F8")
# Zwraca: ECUResponseFrame(parameter_name='RPM', value=1726.0, unit='RPM', is_success=True)

# 3. Parsowanie całego zrzutu sesji ELM327
raw_log = """
> 010C
41 0C 1A F8
> 0105
41 05 7B
> 03
43 01 03 00
"""
entries = parse_raw_ecu_log(raw_log)
print(format_log_summary(entries))
# Wyświetla:
# • RPM: 1726.0 RPM
# • COOLANT_TEMP: 83.0 °C
# Wykryte kody usterek (DTC): P0300
```

---

## 5. Typowe błędy adaptera ELM327 i diagnoza problemu

- **`NO DATA`**: Sterownik nie odpowiedział w wyznaczonym czasie (timeout) lub żądany PID nie jest obsługiwany w tym modelu.
- **`UNABLE TO CONNECT` / `BUS INIT: ... ERROR`**: Nieprawidłowy protokół magistrali lub wyłączony zapłon pojazdu (brak zasilania linii K lub CAN).
- **`BUS BUSY`**: Przeciążenie szyny CAN lub kolizja ramek (wymagana komenda `AT AT1` lub zwiększenie timeoutu `AT ST`).
- **`CAN ERROR`**: Fizyczne uszkodzenie wiązki OBD, zła prędkość transmisji (np. 250 kbps zamiast 500 kbps) lub brak terminatora 120 Ohm.
