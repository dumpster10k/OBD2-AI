from __future__ import annotations

from services.ecu_interpreter import (
    decode_dtc_bytes,
    decode_dtc_frame,
    decode_pid_response,
    format_log_summary,
    parse_raw_ecu_log,
)


def test_decode_dtc_bytes():
    # 0x03, 0x00 -> P0300
    assert decode_dtc_bytes(0x03, 0x00) == "P0300"
    # 0x01, 0x71 -> P0171
    assert decode_dtc_bytes(0x01, 0x71) == "P0171"
    # 0x41, 0x23 -> C0123 (bits 7-6 = 01 -> C)
    assert decode_dtc_bytes(0x41, 0x23) == "C0123"
    # 0x82, 0x10 -> B0210 (bits 7-6 = 10 -> B)
    assert decode_dtc_bytes(0x82, 0x10) == "B0210"
    # 0xC1, 0x55 -> U0155 (bits 7-6 = 11 -> U)
    assert decode_dtc_bytes(0xC1, 0x55) == "U0155"


def test_decode_dtc_frame():
    # Odpowiedź Mode 03 z 2 błędami: P0300 i P0171
    frame_hex = "43 02 03 00 01 71"
    dtcs = decode_dtc_frame(frame_hex)
    assert dtcs == ["P0300", "P0171"]

    # Brak błędów: 43 00
    assert decode_dtc_frame("43 00") == []

    # Odpowiedź z paddingiem 00 00 na końcu
    assert decode_dtc_frame("43 01 01 71 00 00") == ["P0171"]

    # Błędna ramka
    assert decode_dtc_frame("") == []
    assert decode_dtc_frame("NO DATA") == []


def test_decode_pid_response_standard():
    # Tryb 01 PID 0C (RPM: (A*256 + B)/4) -> 1A F8 = (26*256 + 248)/4 = 1726.0
    res_rpm = decode_pid_response("01", "0C", "41 0C 1A F8")
    assert res_rpm.is_success is True
    assert res_rpm.parameter_name == "RPM"
    assert res_rpm.value == 1726.0
    assert res_rpm.unit == "RPM"

    # Tryb 01 PID 0D (Speed: A) -> 32 = 50 km/h
    res_speed = decode_pid_response("01", "0D", "41 0D 32")
    assert res_speed.is_success is True
    assert res_speed.parameter_name == "SPEED"
    assert res_speed.value == 50.0
    assert res_speed.unit == "km/h"

    # Tryb 01 PID 05 (Coolant: A - 40) -> 7B (123) - 40 = 83°C
    res_temp = decode_pid_response("01", "05", "41 05 7B")
    assert res_temp.is_success is True
    assert res_temp.parameter_name == "COOLANT_TEMP"
    assert res_temp.value == 83.0
    assert res_temp.unit == "°C"


def test_decode_pid_response_negative():
    # Negative Response Code: 7F 01 11 (Service not supported)
    res_nrc = decode_pid_response("01", "99", "7F 01 11")
    assert res_nrc.is_success is False
    assert "Service Not Supported" in res_nrc.error_message


def test_parse_raw_ecu_log():
    raw_log = """
    > ATZ
    ELM327 v1.5
    > ATE0
    OK
    > 010C
    41 0C 1A F8
    > 010D
    41 0D 32
    > 03
    43 01 03 00
    > 0199
    7F 01 11
    > 0105
    NO DATA
    """
    entries = parse_raw_ecu_log(raw_log)
    assert len(entries) >= 6

    # Sprawdzenie zdekodowanych elementów
    rpm_entry = next(e for e in entries if e.command == "010C")
    assert rpm_entry.response_raw == "41 0C 1A F8"
    assert rpm_entry.interpreted_value == 1726.0

    dtc_entry = next(e for e in entries if e.command == "03")
    assert "P0300" in dtc_entry.dtc_codes

    no_data_entry = next(e for e in entries if e.command == "0105")
    assert no_data_entry.status == "NO_DATA"

    summary = format_log_summary(entries)
    assert "Podsumowanie komunikacji ECU" in summary
    assert "P0300" in summary
