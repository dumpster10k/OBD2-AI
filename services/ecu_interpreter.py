from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

NRC_DESCRIPTIONS: dict[int, str] = {
    0x10: "General Reject",
    0x11: "Service Not Supported",
    0x12: "SubFunction Not Supported",
    0x13: "Incorrect Message Length Or Invalid Format",
    0x21: "Busy Repeat Request",
    0x22: "Conditions Not Correct",
    0x31: "Request Out Of Range",
    0x33: "Security Access Denied",
    0x78: "Response Pending",
}

STANDARD_PIDS_INFO: dict[str, dict[str, Any]] = {
    "04": {"name": "ENGINE_LOAD", "unit": "%", "fn": lambda b: round(b[0] / 2.55, 1)},
    "05": {"name": "COOLANT_TEMP", "unit": "°C", "fn": lambda b: float(b[0] - 40)},
    "0B": {"name": "MAP", "unit": "kPa", "fn": lambda b: float(b[0])},
    "0C": {"name": "RPM", "unit": "RPM", "fn": lambda b: round(((b[0] * 256) + b[1]) / 4.0, 1)},
    "0D": {"name": "SPEED", "unit": "km/h", "fn": lambda b: float(b[0])},
    "0F": {"name": "INTAKE_TEMP", "unit": "°C", "fn": lambda b: float(b[0] - 40)},
    "11": {"name": "THROTTLE_POS", "unit": "%", "fn": lambda b: round(b[0] / 2.55, 1)},
    "1F": {"name": "RUN_TIME", "unit": "s", "fn": lambda b: float((b[0] * 256) + b[1])},
    "42": {"name": "ECU_VOLTAGE", "unit": "V", "fn": lambda b: round(((b[0] * 256) + b[1]) / 1000.0, 2)},
}


@dataclass
class ECUResponseFrame:
    command: str
    response_raw: str
    status: str  # "OK", "NO_DATA", "ERROR", "NRC"
    is_success: bool = True
    parameter_name: Optional[str] = None
    value: Optional[float | str] = None
    unit: Optional[str] = None
    interpreted_value: Optional[Any] = None
    dtc_codes: list[str] = field(default_factory=list)
    error_message: Optional[str] = None


def decode_dtc_bytes(b1: int, b2: int) -> str:
    """Dekoduje 2-bajtowy kod usterki OBD-II zgodnie ze standardem SAE J2012 / ISO 15031-6."""
    first_char_map = {0: "P", 1: "C", 2: "B", 3: "U"}
    prefix_type = (b1 >> 6) & 0x03
    first_char = first_char_map[prefix_type]

    digit2 = (b1 >> 4) & 0x03
    digit3 = b1 & 0x0F
    digit4 = (b2 >> 4) & 0x0F
    digit5 = b2 & 0x0F

    return f"{first_char}{digit2}{digit3:X}{digit4:X}{digit5:X}"


def decode_dtc_frame(frame_hex: str) -> list[str]:
    """Dekoduje odpowiedź Mode 03 / Mode 07 na listę kodów DTC.

    Przykład: '43 02 03 00 01 71' -> ['P0300', 'P0171']
    """
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", frame_hex.upper())
    if len(cleaned) < 4:
        return []

    # Odpowiedź pozytywna na Mode 03/07/0A zaczyna się od 43/47/4A
    service_id = cleaned[:2]
    if service_id not in ["43", "47", "4A"]:
        return []

    payload_hex = cleaned[2:]
    # Część adapterów podaje liczbę kodów w kolejnym bajcie (np. '02')
    # a część przechodzi bezpośrednio do par bajtów
    bytes_list = [int(payload_hex[i : i + 2], 16) for i in range(0, len(payload_hex), 2)]
    if not bytes_list:
        return []

    # Jeśli pierwszy bajt to liczba kodów (np. 02) i zgadza się z długością:
    reported_count = bytes_list[0]
    dtc_raw_bytes = bytes_list[1:] if len(bytes_list) >= 1 + (reported_count * 2) and reported_count > 0 else bytes_list

    codes = []
    for i in range(0, len(dtc_raw_bytes) - 1, 2):
        b1 = dtc_raw_bytes[i]
        b2 = dtc_raw_bytes[i + 1]
        if b1 == 0 and b2 == 0:
            continue
        code = decode_dtc_bytes(b1, b2)
        if code not in codes:
            codes.append(code)

    return codes


def decode_pid_response(request_mode: str, request_pid: str, response_hex: str) -> ECUResponseFrame:
    """Dekoduje odpowiedź telemetrii OBD-II dla zadanego trybu i PID."""
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", response_hex.upper())
    req_cmd = f"{request_mode.upper()}{request_pid.upper()}"

    if "NO DATA" in response_hex.upper() or "NODATA" in response_hex.upper() or not cleaned:
        return ECUResponseFrame(
            command=req_cmd,
            response_raw=response_hex.strip(),
            status="NO_DATA",
            is_success=False,
            error_message="Brak danych od ECU (NO DATA)",
        )

    # Sprawdzenie Negative Response Code (NRC: 7F [Mode] [NRC_Code])
    if cleaned.startswith("7F"):
        nrc_code = int(cleaned[4:6], 16) if len(cleaned) >= 6 else 0x10
        desc = NRC_DESCRIPTIONS.get(nrc_code, f"Unknown NRC (0x{nrc_code:02X})")
        return ECUResponseFrame(
            command=req_cmd,
            response_raw=response_hex.strip(),
            status="NRC",
            is_success=False,
            error_message=f"Błąd ECU NRC 0x{nrc_code:02X}: {desc}",
        )

    # Odpowiedź Mode 01 ma Service ID 41
    if request_mode.upper() == "01" and cleaned.startswith("41"):
        pid_hex = cleaned[2:4]
        data_hex = cleaned[4:]
        data_bytes = [int(data_hex[i : i + 2], 16) for i in range(0, len(data_hex), 2)]

        info = STANDARD_PIDS_INFO.get(pid_hex)
        if info and data_bytes:
            try:
                calculated = info["fn"](data_bytes)
                return ECUResponseFrame(
                    command=req_cmd,
                    response_raw=response_hex.strip(),
                    status="OK",
                    is_success=True,
                    parameter_name=info["name"],
                    value=calculated,
                    interpreted_value=calculated,
                    unit=info["unit"],
                )
            except Exception as e:
                return ECUResponseFrame(
                    command=req_cmd,
                    response_raw=response_hex.strip(),
                    status="ERROR",
                    is_success=False,
                    error_message=f"Błąd obliczania PID: {e}",
                )

    return ECUResponseFrame(
        command=req_cmd,
        response_raw=response_hex.strip(),
        status="OK",
        is_success=True,
        interpreted_value=cleaned,
    )


def parse_raw_ecu_log(log_text: str) -> list[ECUResponseFrame]:
    """Przetwarza surowy zrzut sesji komunikacji ELM327 / OBD-II na ustrukturyzowane ramki."""
    entries: list[ECUResponseFrame] = []
    lines = [item.strip() for item in log_text.strip().splitlines() if item.strip()]

    current_cmd: Optional[str] = None
    current_responses: list[str] = []

    def flush_entry():
        nonlocal current_cmd, current_responses
        if not current_cmd:
            return
        combined_resp = " ".join(current_responses).strip()

        if current_cmd.startswith("AT"):
            entries.append(
                ECUResponseFrame(
                    command=current_cmd,
                    response_raw=combined_resp,
                    status="OK" if "OK" in combined_resp or "ELM" in combined_resp else "INFO",
                    is_success=True,
                    interpreted_value=combined_resp,
                )
            )
        elif current_cmd in ["03", "07", "0A"]:
            dtcs = decode_dtc_frame(combined_resp)
            entries.append(
                ECUResponseFrame(
                    command=current_cmd,
                    response_raw=combined_resp,
                    status="NO_DATA" if "NO DATA" in combined_resp else "OK",
                    is_success="NO DATA" not in combined_resp,
                    parameter_name="DTC_LIST",
                    interpreted_value=dtcs,
                    dtc_codes=dtcs,
                )
            )
        elif len(current_cmd) == 4 and current_cmd[:2] == "01":
            mode = current_cmd[:2]
            pid = current_cmd[2:4]
            frame = decode_pid_response(mode, pid, combined_resp)
            entries.append(frame)
        else:
            entries.append(
                ECUResponseFrame(
                    command=current_cmd,
                    response_raw=combined_resp,
                    status="OK",
                    is_success=True,
                    interpreted_value=combined_resp,
                )
            )
        current_cmd = None
        current_responses = []

    for line in lines:
        if line.startswith(">"):
            flush_entry()
            current_cmd = line.lstrip("> ").strip()
        else:
            current_responses.append(line)

    flush_entry()
    return entries


def format_log_summary(entries: list[ECUResponseFrame]) -> str:
    """Formatuje czytelne podsumowanie zinterpretowanych logów ECU."""
    lines = ["=== Podsumowanie komunikacji ECU ==="]
    dtc_found: list[str] = []

    for e in entries:
        if e.dtc_codes:
            for c in e.dtc_codes:
                if c not in dtc_found:
                    dtc_found.append(c)

        if e.parameter_name and e.value is not None:
            lines.append(f"• {e.parameter_name}: {e.value} {e.unit or ''}")
        elif e.status == "NO_DATA":
            lines.append(f"• {e.command}: Brak odpowiedzi (NO DATA)")
        elif not e.is_success and e.error_message:
            lines.append(f"• {e.command}: {e.error_message}")

    if dtc_found:
        lines.append(f"Wykryte kody usterek (DTC): {', '.join(dtc_found)}")
    else:
        lines.append("Kody usterek: Brak zarejestrowanych błędów.")

    return "\n".join(lines)
