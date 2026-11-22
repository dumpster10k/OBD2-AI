"""Moduł profilowania i automatycznej identyfikacji pojazdu na podstawie VIN i ECU ID.

Obejmuje:
- Dekoder numeru VIN (WMI, rocznik modelowy, kod platformy/nadwozia).
- Identyfikator sterownika silnika ECU (Bosch EDC15/16/17, ME7.5, MED17, Simos, PCR2.1).
- Profile silnikowe:
  * 1.6 MPI 8V (BSE/BGU/ALZ)
  * 1.6 FSI (BAG/BLF)
  * 1.6 TDI CR (CAYC/CLHA)
  * 1.0 TSI / 1.2 TSI / 1.4 TSI EA211 & EA111
  * 1.8T 20V (AWT/BFB/BEX)
  * 1.9 TDI PD (AVF/AWX/ARL/ASZ)
  * 2.0 TDI PD oraz CR
- Automatyczne dobieranie zestawu aktywnych czujników, zegarów oraz testów podzespołów.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class VehicleProfile:
    """Kompletny profil techniczny zidentyfikowanego pojazdu."""

    vin: str = ""
    vendor: str = "Standard"  # np. "VAG", "BMW", "Mercedes", "Standard"
    brand: str = "Uniwersalny"  # np. "Audi", "Volkswagen", "Skoda", "Seat"
    model: str = "Pojazd OBD-II"  # np. "A4", "Golf", "Octavia", "Leon", "Passat"
    generation: str = ""  # np. "B6", "B7", "IV", "V", "VI", "VII"
    model_year: Optional[int] = None
    engine_code: str = ""  # np. "BSE", "CAYC", "AVF", "AWT", "CAXA", "CBZA"
    engine_name: str = "Standard OBD-II Engine"
    fuel_type: str = "petrol"  # "petrol", "diesel"
    has_turbo: bool = False
    has_dpf: bool = False
    ecu_family: str = "Generic_OBD"  # "EDC15", "EDC16", "EDC17", "ME7.5", "MED17", "Simos", "PCR2.1"
    recommended_protocol: str = "SAE_J1979"  # "KWP1281", "KWP2000", "UDS_2F", "SAE_J1979"
    active_sensor_names: list[str] = field(default_factory=list)
    dashboard_gauge_keys: list[str] = field(default_factory=list)
    applicable_actuator_tests: list[str] = field(default_factory=list)
    summary_description: str = ""


class VINDecoder:
    """Dekoduje numer nadwozia VIN (Mode 09 PID 02) zgodnie ze standardem ISO 3779 / SAE J272."""

    # World Manufacturer Identifier (WMI)
    WMI_MAP: dict[str, tuple[str, str]] = {
        "WAU": ("VAG", "Audi"),
        "WA1": ("VAG", "Audi"),
        "TRU": ("VAG", "Audi"),
        "WVW": ("VAG", "Volkswagen"),
        "WVG": ("VAG", "Volkswagen"),
        "WV1": ("VAG", "Volkswagen"),
        "WV2": ("VAG", "Volkswagen"),
        "TMB": ("VAG", "Skoda"),
        "TMP": ("VAG", "Skoda"),
        "VSS": ("VAG", "Seat"),
        "WBA": ("BMW", "BMW"),
        "WBS": ("BMW", "BMW M"),
        "WDB": ("Mercedes", "Mercedes-Benz"),
        "WDC": ("Mercedes", "Mercedes-Benz"),
        "WDD": ("Mercedes", "Mercedes-Benz"),
        "VF3": ("PSA", "Peugeot"),
        "VF7": ("PSA", "Citroën"),
        "VF1": ("Renault", "Renault"),
        "UU1": ("Renault", "Dacia"),
        "WF0": ("Ford", "Ford"),
        "W0L": ("Opel", "Opel"),
        "JT1": ("Toyota", "Toyota"),
        "JT2": ("Toyota", "Toyota"),
        "JTD": ("Toyota", "Toyota"),
        "JTE": ("Toyota", "Toyota"),
        "SB1": ("Toyota", "Toyota"),
        "WBY": ("BMW", "BMW i"),
        "WDF": ("Mercedes", "Mercedes-Benz"),
    }

    # 10. znak VIN określa rok modelowy
    YEAR_CODES: dict[str, int] = {
        "Y": 2000,
        "1": 2001,
        "2": 2002,
        "3": 2003,
        "4": 2004,
        "5": 2005,
        "6": 2006,
        "7": 2007,
        "8": 2008,
        "9": 2009,
        "A": 2010,
        "B": 2011,
        "C": 2012,
        "D": 2013,
        "E": 2014,
        "F": 2015,
        "G": 2016,
        "H": 2017,
        "J": 2018,
        "K": 2019,
        "L": 2020,
        "M": 2021,
        "N": 2022,
        "P": 2023,
        "R": 2024,
        "S": 2025,
        "T": 2026,
    }

    # Kody platform i modeli VAG zawarte w znakach 7-8 VIN
    VAG_PLATFORM_MAP: dict[str, tuple[str, str]] = {
        "8E": ("A4", "B6/B7"),
        "8H": ("A4 Cabrio", "B6/B7"),
        "8K": ("A4", "B8"),
        "8W": ("A4", "B9"),
        "8L": ("A3", "I"),
        "8P": ("A3", "II"),
        "8V": ("A3", "III"),
        "4B": ("A6", "C5"),
        "4F": ("A6", "C6"),
        "4G": ("A6", "C7"),
        "1J": ("Golf / Bora", "IV"),
        "1K": ("Golf / Jetta", "V"),
        "5K": ("Golf", "VI"),
        "5G": ("Golf", "VII"),
        "3B": ("Passat", "B5"),
        "3C": ("Passat", "B6/B7"),
        "3G": ("Passat", "B8"),
        "1Z": ("Octavia", "II"),
        "5E": ("Octavia", "III"),
        "1M": ("Leon / Toledo", "I"),
        "1P": ("Leon", "II"),
        "5F": ("Leon", "III"),
        "6L": ("Ibiza", "III"),
        "6J": ("Ibiza", "IV"),
        "7M": ("Sharan", "I"),
        "7N": ("Sharan", "II"),
        "7H": ("Transporter", "T5"),
    }

    @classmethod
    def decode(cls, vin: str) -> dict[str, Any]:
        """Ekstrahuje producenta, markę, rocznik i model z numeru VIN."""
        cleaned = re.sub(r"[^A-HJ-NPR-Z0-9]", "", vin.upper().strip())
        if len(cleaned) < 10:
            return {"valid": False, "vin": cleaned}

        wmi = cleaned[:3]
        vendor_info = cls.WMI_MAP.get(wmi, ("Inny", "Nieznana marka"))

        year_char = cleaned[9]
        model_year = cls.YEAR_CODES.get(year_char)

        # Wykrycie modelu VAG
        model_name = "Model standardowy"
        generation = ""
        if vendor_info[0] == "VAG" and len(cleaned) >= 8:
            # W VAG kod nadwozia zazwyczaj znajduje się na pozycjach 7-8
            chassis_code = cleaned[6:8]
            if chassis_code in cls.VAG_PLATFORM_MAP:
                model_name, generation = cls.VAG_PLATFORM_MAP[chassis_code]

        return {
            "valid": len(cleaned) == 17,
            "vin": cleaned,
            "vendor": vendor_info[0],
            "brand": vendor_info[1],
            "model": model_name,
            "generation": generation,
            "model_year": model_year,
        }


class ECUIdentifier:
    """Identyfikuje rodzinę sterownika, silnik i osprzęt na podstawie numeru części lub oznaczenia ECU."""

    @classmethod
    def identify(cls, ecu_raw_str: str) -> dict[str, Any]:
        raw_norm = ecu_raw_str.upper().replace(" ", "").replace("-", "")

        # 1. VAG 1.9 TDI PD (Bosch EDC15P / EDC15P+)
        # Przykłady: 038906019FP, 038906019BJ, 038906019KD
        if re.search(r"038906019[A-Z0-9]*", raw_norm) or "EDC15" in raw_norm:
            return {
                "vendor": "VAG",
                "engine_code": "1.9 TDI PD",
                "engine_name": "1.9 TDI PD (Pumpe Düse - AVF/AWX/ARL/ASZ/BKC)",
                "fuel_type": "diesel",
                "has_turbo": True,
                "has_dpf": False,
                "ecu_family": "EDC15P",
                "recommended_protocol": "KWP1281",
            }

        # 2. VAG 1.9 TDI / 2.0 TDI PD (Bosch EDC16U1 / EDC16U34)
        # Przykłady: 03G906016, 03G906021
        if (
            (
                "EDC16" in raw_norm
                and not any(
                    k in raw_norm
                    for k in [
                        "3.0",
                        "CP",
                        "HDI",
                        "TDCI",
                        "DV6",
                        "DW10",
                        "DDE",
                        "CDI",
                        "K9K",
                        "C34",
                    ]
                )
            )
            or "03G906016" in raw_norm
            or "03G906021" in raw_norm
        ):
            has_dpf = "BLS" in raw_norm or "BMM" in raw_norm or "DPF" in raw_norm
            return {
                "vendor": "VAG",
                "engine_code": "1.9/2.0 TDI PD (EDC16)",
                "engine_name": "1.9 / 2.0 TDI PD (BKD/BXE/BLS/BMM)",
                "fuel_type": "diesel",
                "has_turbo": True,
                "has_dpf": has_dpf,
                "ecu_family": "EDC16",
                "recommended_protocol": "KWP2000",
            }

        # 3. VAG 1.6 TDI Common Rail (Siemens / Continental Simos PCR2.1)
        # Przykłady: 03L906023, PCR2.1, CAYC (105KM), CAYB (90KM), CLHA
        if "PCR2.1" in raw_norm or "03L906023" in raw_norm or "CAYC" in raw_norm or "CLHA" in raw_norm:
            return {
                "vendor": "VAG",
                "engine_code": "1.6 TDI CR",
                "engine_name": "1.6 TDI Common Rail (CAYC/CAYB/CLHA)",
                "fuel_type": "diesel",
                "has_turbo": True,
                "has_dpf": True,
                "ecu_family": "PCR2.1",
                "recommended_protocol": "UDS_2F",
            }

        # 4. VAG 2.0 TDI Common Rail (Bosch EDC17)
        # Przykłady: 03L906018, 03L906022, EDC17CP14, EDC17C46
        if (
            (
                "EDC17" in raw_norm
                and not any(
                    k in raw_norm
                    for k in [
                        "3.0",
                        "CP44",
                        "CP45",
                        "BMW",
                        "DDE",
                        "N47",
                        "B47",
                        "N57",
                        "HDI",
                        "TDCI",
                        "DV6",
                        "DW10",
                        "C10",
                        "C84",
                        "C50",
                        "C41",
                        "C06",
                    ]
                )
            )
            or "03L906018" in raw_norm
            or "03L906022" in raw_norm
        ):
            return {
                "vendor": "VAG",
                "engine_code": "2.0 TDI CR",
                "engine_name": "2.0 TDI Common Rail (CBAB/CBBB/CJCA/CUNA)",
                "fuel_type": "diesel",
                "has_turbo": True,
                "has_dpf": True,
                "ecu_family": "EDC17",
                "recommended_protocol": "UDS_2F",
            }

        # 5. VAG 1.6 MPI 8V (Siemens Simos 3 / 7)
        # Kultowy silnik wolnossący w A4 B6 (ALZ), Golf 4/5/6, Octavia (BSE, BGU, BSF, AKL)
        if "SIMOS" in raw_norm and ("1.6" in raw_norm or "BSE" in raw_norm) or "06A906033" in raw_norm:
            return {
                "vendor": "VAG",
                "engine_code": "1.6 MPI 8V",
                "engine_name": "1.6 MPI 8V (BSE/BGU/ALZ/BSF - Wolnossący)",
                "fuel_type": "petrol",
                "has_turbo": False,
                "has_dpf": False,
                "ecu_family": "Simos3",
                "recommended_protocol": "KWP1281",
            }

        # 6. VAG 1.6 FSI 16V (Bosch MED9.5.10)
        # Przykłady: 03C906056 (BAG, BLF)
        if "03C906056" in raw_norm or ("MED9" in raw_norm and "1.6" in raw_norm) or "BLF" in raw_norm:
            return {
                "vendor": "VAG",
                "engine_code": "1.6 FSI",
                "engine_name": "1.6 FSI 16V (BAG/BLF - Bezpośredni wtrysk)",
                "fuel_type": "petrol",
                "has_turbo": False,
                "has_dpf": False,
                "ecu_family": "MED9.5",
                "recommended_protocol": "KWP2000",
            }

        # 7. VAG 1.8T 20V (Bosch ME7.5)
        # Przykłady: 06A906032, 06B906018, ME7.5 (AWT, BFB, BEX, BAM, AGU)
        if re.search(r"06[AB]906032[A-Z0-9]*", raw_norm) or "ME7.5" in raw_norm or "1.8T" in raw_norm:
            return {
                "vendor": "VAG",
                "engine_code": "1.8T 20V",
                "engine_name": "1.8T 20V Turbo (AWT/BFB/BEX/BAM/AUQ)",
                "fuel_type": "petrol",
                "has_turbo": True,
                "has_dpf": False,
                "ecu_family": "ME7.5",
                "recommended_protocol": "KWP1281",
            }

        # 8. VAG 1.2 TSI EA111 (Siemens Simos 10 / 10.12)
        # Przykłady: 03F906070 (CBZA 86KM, CBZB 105KM)
        if "03F906070" in raw_norm or "CBZA" in raw_norm or "CBZB" in raw_norm:
            return {
                "vendor": "VAG",
                "engine_code": "1.2 TSI EA111",
                "engine_name": "1.2 TSI 8V Turbo (CBZA/CBZB - łańcuch)",
                "fuel_type": "petrol",
                "has_turbo": True,
                "has_dpf": False,
                "ecu_family": "Simos10",
                "recommended_protocol": "UDS_2F",
            }

        # 9. VAG 1.4 TSI EA111 (Bosch MED17.5.5 / MED17.5.20)
        # Przykłady: 03C906016, 03C906022 (CAXA 122KM, CAVA Twincharger 150/160KM)
        if (
            "03C906016" in raw_norm
            or "03C906022" in raw_norm
            or "CAXA" in raw_norm
            or ("MED17" in raw_norm and "1.4" in raw_norm)
        ):
            return {
                "vendor": "VAG",
                "engine_code": "1.4 TSI EA111",
                "engine_name": "1.4 TSI Turbo (CAXA/CAVA - łańcuch)",
                "fuel_type": "petrol",
                "has_turbo": True,
                "has_dpf": False,
                "ecu_family": "MED17.5",
                "recommended_protocol": "UDS_2F",
            }

        # 10. VAG 1.0 TSI / 1.2 TSI / 1.4 TSI EA211 (Bosch MED17.5.21 / Simos 18 / 21)
        # Nowsze małe silniki na pasku rozrządu z nastawnikiem V465 (Golf 7, Octavia 3, Leon 3)
        if "EA211" in raw_norm or "CHPA" in raw_norm or "CZCA" in raw_norm or "CJZA" in raw_norm or "CHZB" in raw_norm:
            return {
                "vendor": "VAG",
                "engine_code": "1.0/1.2/1.4 TSI EA211",
                "engine_name": "1.0 / 1.2 / 1.4 TSI EA211 (Pasek rozrządu + V465 wastegate)",
                "fuel_type": "petrol",
                "has_turbo": True,
                "has_dpf": False,
                "ecu_family": "MED17.5.21",
                "recommended_protocol": "UDS_2F",
            }

        # 11. VAG 2.0 TFSI EA113 (Bosch MED9.1)
        # Golf 5 GTI, Leon Cupra, Audi S3 8P, Audi A4 B7 (AXX, BWA, BWE, BUL, CDL, BHZ, BYD)
        if (
            "MED9.1" in raw_norm
            or "1K0907115" in raw_norm
            or "8P0907115" in raw_norm
            or "8E0907115" in raw_norm
            or any(c in raw_norm for c in ["BWA", "AXX", "BWE", "BUL", "CDL", "BHZ", "BYD"])
        ):
            return {
                "vendor": "VAG",
                "engine_code": "2.0 TFSI EA113",
                "engine_name": "2.0 TFSI EA113 (Pasek + pasek/łańcuszek wałków, HPFP szklanka)",
                "fuel_type": "petrol",
                "has_turbo": True,
                "has_dpf": False,
                "ecu_family": "MED9.1",
                "recommended_protocol": "KWP2000",
            }

        # 12. VAG 2.0 TSI / TFSI EA888 Gen 1/2/3 (Bosch MED17.5 / Continental Simos 18)
        # Golf 6/7 GTI/R, Octavia RS, Leon Cupra 5F, Audi A4 B8 (CAEB, CCZA, CHHA, CHHB, CJXC, CJXG, DKTB)
        if (
            "06J906026" in raw_norm
            or "06J906027" in raw_norm
            or "5G0906259" in raw_norm
            or "8K2907115" in raw_norm
            or "SIMOS18" in raw_norm
            or any(c in raw_norm for c in ["CAEB", "CCZA", "CHHA", "CHHB", "CJXC", "CJXG", "DKTB", "EA888"])
        ):
            return {
                "vendor": "VAG",
                "engine_code": "2.0 TSI EA888",
                "engine_name": "2.0 TSI / TFSI EA888 (Łańcuch rozrządu, MPI+FSI w Gen3)",
                "fuel_type": "petrol",
                "has_turbo": True,
                "has_dpf": False,
                "ecu_family": "Simos18" if "SIMOS" in raw_norm or "5G0906259" in raw_norm else "MED17.5",
                "recommended_protocol": "UDS_2F",
            }

        # 13. VAG 3.0 TDI V6 Common Rail (Bosch EDC16CP34 / EDC17CP14 / EDC17CP44 / MD1)
        # Audi A4/A6/A8/Q7, Touareg (ASB, BKN, BMK, CAPA, CCWA, CDUC, CKVB, CRTC)
        if (
            "4F0907401" in raw_norm
            or "4F0910401" in raw_norm
            or "8K0907401" in raw_norm
            or "4G0907401" in raw_norm
            or "EDC16CP34" in raw_norm
            or "EDC17CP44" in raw_norm
            or any(c in raw_norm for c in ["3.0TDI", "CAPA", "CCWA", "CDUC", "ASB", "BKN", "BMK", "CRTC"])
        ):
            return {
                "vendor": "VAG",
                "engine_code": "3.0 TDI V6 CR",
                "engine_name": "3.0 V6 TDI Common Rail (204-272 KM, piezo / klapy wirowe)",
                "fuel_type": "diesel",
                "has_turbo": True,
                "has_dpf": True,
                "ecu_family": "EDC17CP44" if "4G0" in raw_norm or "CDUC" in raw_norm else "EDC16CP34",
                "recommended_protocol": "UDS_2F" if "4G0" in raw_norm or "8K0" in raw_norm else "KWP2000",
            }

        # 14. VAG VR6 3.2 / 3.6 FSI (Bosch ME7.1.1 / MED9.1)
        # Golf R32, Passat B6/CC 3.6, Audi TT 3.2, Touareg VR6 (BDB, BMJ, BUB, BWS, AXZ)
        if (
            "022906032" in raw_norm
            or "03H906032" in raw_norm
            or any(c in raw_norm for c in ["VR6", "R32", "BUB", "BWS", "BMJ", "BDB", "AXZ"])
        ):
            return {
                "vendor": "VAG",
                "engine_code": "VR6 3.2/3.6",
                "engine_name": "VR6 3.2 / 3.6 FSI 24V (Kanały 208/209 fazy rozrządu)",
                "fuel_type": "petrol",
                "has_turbo": False,
                "has_dpf": False,
                "ecu_family": "ME7.1.1",
                "recommended_protocol": "KWP1281",
            }

        # 15. VAG 4.2 V8 MPI / FSI (Bosch ME7.1.1 / MED9.1.1)
        # Audi S4 B6/B7 (BBK), Audi S5 4.2 (CAUA), Audi A8 4.2 (BFM, BVJ)
        if (
            "8E0907559" in raw_norm
            or "4E0910560" in raw_norm
            or "079907560" in raw_norm
            or any(c in raw_norm for c in ["4.2V8", "BBK", "CAUA", "BFM", "BVJ", "BAS"])
        ):
            return {
                "vendor": "VAG",
                "engine_code": "4.2 V8",
                "engine_name": "4.2 V8 40V / FSI 32V (Dwa przepływomierze Bank 1/2)",
                "fuel_type": "petrol",
                "has_turbo": False,
                "has_dpf": False,
                "ecu_family": "ME7.1.1",
                "recommended_protocol": "KWP2000",
            }

        # --- BMW ---
        # 16. BMW M57 3.0d (Bosch DDE5 / DDE6)
        if (
            "DDE5" in raw_norm
            or "DDE6" in raw_norm
            or "M57" in raw_norm
            or ("BMW" in raw_norm and "3.0D" in raw_norm and "N57" not in raw_norm)
        ):
            return {
                "vendor": "BMW",
                "engine_code": "M57 3.0d",
                "engine_name": "BMW M57 3.0d R6 (Common Rail DDE5/DDE6 M57D30)",
                "fuel_type": "diesel",
                "has_turbo": True,
                "has_dpf": True,
                "ecu_family": "DDE6",
                "recommended_protocol": "ISO_14229_UDS",
            }

        # 17. BMW N47 / B47 2.0d (Bosch DDE7 / EDC17C06 / EDC17C41 / EDC17C50)
        if (
            "DDE7" in raw_norm
            or "N47" in raw_norm
            or "B47" in raw_norm
            or ("BMW" in raw_norm and "2.0D" in raw_norm)
            or any(c in raw_norm for c in ["EDC17C06", "EDC17C41", "EDC17C50"])
        ):
            return {
                "vendor": "BMW",
                "engine_code": "N47/B47 2.0d",
                "engine_name": "BMW N47/B47 2.0d (Rozrząd tył silnika, DPF, DDE7/EDC17)",
                "fuel_type": "diesel",
                "has_turbo": True,
                "has_dpf": True,
                "ecu_family": "DDE7",
                "recommended_protocol": "ISO_14229_UDS",
            }

        # 18. BMW N57 3.0d (Bosch EDC17CP45)
        if (
            "N57" in raw_norm
            or ("EDC17CP45" in raw_norm)
            or ("BMW" in raw_norm and "3.0D" in raw_norm and "CP45" in raw_norm)
        ):
            return {
                "vendor": "BMW",
                "engine_code": "N57 3.0d",
                "engine_name": "BMW N57 3.0d R6 (EDC17CP45 piezo CR)",
                "fuel_type": "diesel",
                "has_turbo": True,
                "has_dpf": True,
                "ecu_family": "EDC17CP45",
                "recommended_protocol": "ISO_14229_UDS",
            }

        # 19. BMW M54 2.2/2.5/3.0 (Siemens MS43 / MS45)
        if (
            "MS43" in raw_norm
            or "MS45" in raw_norm
            or "M54" in raw_norm
            or ("BMW" in raw_norm and ("325I" in raw_norm or "330I" in raw_norm or "530I" in raw_norm))
        ):
            return {
                "vendor": "BMW",
                "engine_code": "M54 R6",
                "engine_name": "BMW M54 2.2/2.5/3.0 R6 (Podwójny Vanos, DISA, MS43/MS45)",
                "fuel_type": "petrol",
                "has_turbo": False,
                "has_dpf": False,
                "ecu_family": "MS43",
                "recommended_protocol": "KWP2000",
            }

        # 20. BMW N52 / N55 / B48 / B58 Valvetronic (Siemens MSV70/MSV80 / Bosch MEVD17)
        if (
            "MEVD17" in raw_norm
            or "MSV70" in raw_norm
            or "MSV80" in raw_norm
            or any(c in raw_norm for c in ["N52", "N55", "B48", "B58", "VALVETRONIC"])
        ):
            return {
                "vendor": "BMW",
                "engine_code": "N52/N55/B48/B58",
                "engine_name": "BMW R4/R6 Valvetronic (Vanos + Valvetronic mimośród, MEVD17)",
                "fuel_type": "petrol",
                "has_turbo": True,
                "has_dpf": False,
                "ecu_family": "MEVD17",
                "recommended_protocol": "ISO_14229_UDS",
            }

        # --- PSA & FORD ---
        # 21. PSA / Ford 1.6 HDi / TDCi (Bosch EDC16C34 / EDC17C10)
        if (
            "EDC16C34" in raw_norm
            or "EDC17C10" in raw_norm
            or "DV6" in raw_norm
            or (
                ("PSA" in raw_norm or "FORD" in raw_norm)
                and "1.6" in raw_norm
                and ("HDI" in raw_norm or "TDCI" in raw_norm)
            )
        ):
            return {
                "vendor": "PSA",
                "engine_code": "1.6 HDi/TDCi",
                "engine_name": "1.6 HDi / TDCi DV6 (FAP mokry z Eolys, EDC16C34/EDC17)",
                "fuel_type": "diesel",
                "has_turbo": True,
                "has_dpf": True,
                "ecu_family": "EDC16C34",
                "recommended_protocol": "ISO_14229_UDS",
            }

        # 22. PSA / Ford 2.0 HDi / TDCi (Siemens SID803 / Delphi DCM3.5)
        if (
            "SID803" in raw_norm
            or "DCM3.5" in raw_norm
            or "DCM6.2" in raw_norm
            or "DW10" in raw_norm
            or (
                ("PSA" in raw_norm or "FORD" in raw_norm)
                and "2.0" in raw_norm
                and ("HDI" in raw_norm or "TDCI" in raw_norm)
            )
        ):
            return {
                "vendor": "PSA",
                "engine_code": "2.0 HDi/TDCi",
                "engine_name": "2.0 HDi / TDCi DW10 (Common Rail Siemens/Delphi/Bosch)",
                "fuel_type": "diesel",
                "has_turbo": True,
                "has_dpf": True,
                "ecu_family": "SID803",
                "recommended_protocol": "ISO_14229_UDS",
            }

        # 23. Ford 1.0 EcoBoost (Bosch MED17.0.7 / Continental EMS2211)
        if "ECOBOOST" in raw_norm or ("FORD" in raw_norm and "1.0" in raw_norm) or "EMS2211" in raw_norm:
            return {
                "vendor": "Ford",
                "engine_code": "1.0 EcoBoost",
                "engine_name": "Ford 1.0 EcoBoost 3-cyl (Pasek w oleju wet-belt, turbo, MED17)",
                "fuel_type": "petrol",
                "has_turbo": True,
                "has_dpf": False,
                "ecu_family": "MED17",
                "recommended_protocol": "ISO_14229_UDS",
            }

        # 24. PSA 1.2 PureTech (Valeo V46 / Bosch MED17.4.4)
        if (
            "PURETECH" in raw_norm
            or "EB2" in raw_norm
            or (("PSA" in raw_norm or "PEUGEOT" in raw_norm or "CITROEN" in raw_norm) and "1.2" in raw_norm)
        ):
            return {
                "vendor": "PSA",
                "engine_code": "1.2 PureTech",
                "engine_name": "PSA 1.2 PureTech EB2 (Pasek w kąpieli olejowej, smok olejowy)",
                "fuel_type": "petrol",
                "has_turbo": True,
                "has_dpf": False,
                "ecu_family": "MED17.4",
                "recommended_protocol": "ISO_14229_UDS",
            }

        # --- MERCEDES-BENZ ---
        # 25. Mercedes OM646 2.2 CDI (Bosch EDC16C2 / EDC16CP31)
        if (
            "OM646" in raw_norm
            or "EDC16C2" in raw_norm
            or "EDC16CP31" in raw_norm
            or ("MERCEDES" in raw_norm and "2.2" in raw_norm and "CDI" in raw_norm)
        ):
            return {
                "vendor": "Mercedes",
                "engine_code": "OM646 2.2 CDI",
                "engine_name": "Mercedes OM646 2.2 CDI R4 (EDC16, żeliwny blok)",
                "fuel_type": "diesel",
                "has_turbo": True,
                "has_dpf": True,
                "ecu_family": "EDC16CP31",
                "recommended_protocol": "ISO_14229_UDS",
            }

        # 26. Mercedes OM651 2.1 CDI (Delphi CRD2 / CRD3)
        if (
            "OM651" in raw_norm
            or "CRD2" in raw_norm
            or "CRD3" in raw_norm
            or ("MERCEDES" in raw_norm and "2.1" in raw_norm and "CDI" in raw_norm)
        ):
            return {
                "vendor": "Mercedes",
                "engine_code": "OM651 2.1 CDI",
                "engine_name": "Mercedes OM651 2.1 CDI (Wtrysk Delphi piezo/solenoid, rozrząd tył)",
                "fuel_type": "diesel",
                "has_turbo": True,
                "has_dpf": True,
                "ecu_family": "CRD3",
                "recommended_protocol": "ISO_14229_UDS",
            }

        # 27. Mercedes M271 1.8 Kompressor / CGI (Siemens SIM4 / Bosch MED17.7)
        if "M271" in raw_norm or "SIM4" in raw_norm or ("KOMPRESSOR" in raw_norm and "1.8" in raw_norm):
            return {
                "vendor": "Mercedes",
                "engine_code": "M271 1.8",
                "engine_name": "Mercedes M271 1.8 Kompressor/CGI (Wariatory faz rozrządu, łańcuch)",
                "fuel_type": "petrol",
                "has_turbo": True,
                "has_dpf": False,
                "ecu_family": "SIM4",
                "recommended_protocol": "ISO_14229_UDS",
            }

        # --- RENAULT & DACIA ---
        # 28. Renault 1.5 dCi K9K (Delphi DDCR / DCM1.2 / Bosch EDC17C84)
        if (
            "K9K" in raw_norm
            or ("1.5" in raw_norm and "DCI" in raw_norm)
            or any(c in raw_norm for c in ["DDCR", "DCM1.2", "EDC17C84"])
        ):
            return {
                "vendor": "Renault",
                "engine_code": "1.5 dCi K9K",
                "engine_name": "Renault 1.5 dCi K9K (Common Rail Delphi/Bosch, panewki, EGR)",
                "fuel_type": "diesel",
                "has_turbo": True,
                "has_dpf": True,
                "ecu_family": "DCM1.2",
                "recommended_protocol": "ISO_14229_UDS",
            }

        # 29. Renault 1.2 / 1.3 TCe (Continental EMS3125 / Bosch MED17)
        if "EMS3125" in raw_norm or "TCE" in raw_norm or "H5FT" in raw_norm or "H5HT" in raw_norm:
            return {
                "vendor": "Renault",
                "engine_code": "1.2/1.3 TCe",
                "engine_name": "Renault 1.2/1.3 TCe H5Ft/H5Ht (Turbo benzyna bezpośredni wtrysk)",
                "fuel_type": "petrol",
                "has_turbo": True,
                "has_dpf": False,
                "ecu_family": "EMS3125",
                "recommended_protocol": "ISO_14229_UDS",
            }

        # --- TOYOTA ---
        # 30. Toyota 1.8 Hybrid HSD (Denso THS-II / HV ECU)
        if (
            "THS-II" in raw_norm
            or "THS" in raw_norm
            or "2ZR-FXE" in raw_norm
            or ("TOYOTA" in raw_norm and "HYBRID" in raw_norm)
            or "PRIUS" in raw_norm
            or ("AURIS" in raw_norm and "HYBRID" in raw_norm)
        ):
            return {
                "vendor": "Toyota",
                "engine_code": "1.8 Hybrid 2ZR-FXE",
                "engine_name": "Toyota 1.8 Hybrid HSD (Bateria trakcyjna HV bloki 1-14, inwerter MG1/MG2, cykl Atkinsona)",
                "fuel_type": "hybrid",
                "has_turbo": False,
                "has_dpf": False,
                "ecu_family": "DensoHV",
                "recommended_protocol": "ISO_14229_UDS",
            }

        # 31. Toyota 2.0 / 2.2 D-4D (Denso ECD-U2 / D-CAT)
        if (
            "D-4D" in raw_norm
            or "D4D" in raw_norm
            or "1CD-FTV" in raw_norm
            or "2AD-FHV" in raw_norm
            or ("TOYOTA" in raw_norm and "DENSO" in raw_norm and "DIESEL" in raw_norm)
        ):
            return {
                "vendor": "Toyota",
                "engine_code": "2.0/2.2 D-4D",
                "engine_name": "Toyota 2.0/2.2 D-4D 1CD/2AD (Wtryskiwacze Denso, zawór SCV)",
                "fuel_type": "diesel",
                "has_turbo": True,
                "has_dpf": True,
                "ecu_family": "DensoECD",
                "recommended_protocol": "ISO_14229_UDS",
            }

        # Domyślny fallback: Uniwersalny sterownik OBD-II
        return {
            "vendor": "Standard",
            "engine_code": "Generic OBD-II",
            "engine_name": "Standardowy silnik OBD-II / EOBD",
            "fuel_type": "petrol",
            "has_turbo": False,
            "has_dpf": False,
            "ecu_family": "Generic_OBD",
            "recommended_protocol": "SAE_J1979",
        }


class VehicleProfiler:
    """Główny silnik profilera - tworzy kompletny profil pojazdu i konfiguruje czujniki."""

    @classmethod
    def detect_profile(
        cls,
        vin: Optional[str] = None,
        ecu_id: Optional[str] = None,
    ) -> VehicleProfile:
        """Tworzy profil pojazdu na podstawie numeru VIN oraz/lub identyfikatora ECU."""
        vin_data = VINDecoder.decode(vin) if vin else {}
        ecu_data = ECUIdentifier.identify(ecu_id) if ecu_id else {}

        vendor = ecu_data.get("vendor") or vin_data.get("vendor") or "Standard"
        brand = vin_data.get("brand") or ("VAG" if vendor == "VAG" else "Uniwersalny")
        model = vin_data.get("model") or "Pojazd OBD-II"
        generation = vin_data.get("generation", "")
        model_year = vin_data.get("model_year")

        engine_code = ecu_data.get("engine_code", "Generic OBD-II")
        engine_name = ecu_data.get("engine_name", "Standardowy silnik OBD-II")
        fuel_type = ecu_data.get("fuel_type", "petrol")
        has_turbo = ecu_data.get("has_turbo", False)
        has_dpf = ecu_data.get("has_dpf", False)
        ecu_family = ecu_data.get("ecu_family", "Generic_OBD")
        recommended_proto = ecu_data.get("recommended_protocol", "SAE_J1979")

        # -------------------------------------------------------------
        # Dobór rekomendowanych czujników telemetrycznych
        # -------------------------------------------------------------
        active_sensors = ["Engine RPM", "Vehicle Speed", "Engine Coolant Temp", "Calculated Engine Load"]

        # Silniki Diesla
        if fuel_type == "diesel":
            if vendor == "BMW":
                active_sensors.extend(
                    [
                        "BMW DDE Common Rail Pressure",
                        "BMW DDE DPF Soot Mass",
                        "BMW DDE DPF Exhaust Backpressure",
                        "Control Module Voltage",
                    ]
                )
            elif vendor in ["PSA", "Ford"]:
                active_sensors.extend(
                    [
                        "PSA HDi Rail Fuel Pressure",
                        "PSA FAP Differential Pressure",
                        "PSA FAP Eolys Additive Level",
                        "Control Module Voltage",
                    ]
                )
            elif vendor == "Mercedes":
                active_sensors.extend(
                    [
                        "Mercedes CDI Common Rail Pressure",
                        "Mercedes CDI DPF Ash Content",
                        "Control Module Voltage",
                    ]
                )
            elif vendor == "Renault":
                active_sensors.extend(
                    [
                        "Renault 1.5 dCi Rail Pressure",
                        "Renault dCi DPF Soot Load",
                        "Control Module Voltage",
                    ]
                )
            elif vendor == "Toyota":
                active_sensors.extend(
                    [
                        "Toyota D-4D Denso SCV Valve Duty",
                        "Fuel Rail High Pressure Actual",
                        "Control Module Voltage",
                    ]
                )
            elif "PD" in engine_code or ecu_family == "EDC15P":
                active_sensors.extend(
                    [
                        "VAG Torsion Value",
                        "VAG Actual Boost G31",
                        "VAG Specified Boost KWP",
                        "VAG N75 Valve Duty Cycle",
                        "VAG Coolant Temp G62",
                        "Control Module Voltage",
                    ]
                )
            elif has_dpf or "CR" in engine_code or ecu_family in ["PCR2.1", "EDC17"]:
                active_sensors.extend(
                    [
                        "DPF Soot Mass",
                        "DPF Differential Pressure",
                        "EGT Temp pre Turbo",
                        "EGT Temp pre DPF",
                        "Fuel Rail High Pressure Actual",
                        "Boost Pressure",
                        "Engine Oil Temp",
                        "Control Module Voltage",
                    ]
                )
        # Napędy hybrydowe (Toyota HSD / Prius / Auris)
        elif fuel_type == "hybrid":
            active_sensors.extend(
                [
                    "Toyota HSD HV Battery State of Charge",
                    "Toyota HSD HV Battery Current",
                    "Toyota HSD HV Battery Block Min Voltage",
                    "Toyota HSD HV Battery Block Max Voltage",
                    "Toyota HSD HV Battery Block Delta Voltage",
                    "Toyota HSD Inverter Temp MG1",
                    "Toyota HSD Inverter Temp MG2",
                    "Control Module Voltage",
                ]
            )
        # BMW silniki benzynowe (Vanos + Valvetronic)
        elif vendor == "BMW" and fuel_type == "petrol":
            active_sensors.extend(
                [
                    "BMW Vanos Intake Cam Angle",
                    "BMW Vanos Exhaust Cam Angle",
                    "BMW Valvetronic Eccentric Shaft Angle",
                    "Control Module Voltage",
                ]
            )
        # PSA / Ford silniki z paskiem w kąpieli olejowej (PureTech / EcoBoost)
        elif (
            vendor in ["PSA", "Ford"] or "PureTech" in engine_code or "EcoBoost" in engine_code
        ) and fuel_type == "petrol":
            active_sensors.extend(
                [
                    "Ford PureTech Wet Belt Oil Pressure",
                    "Intake Manifold Absolute Pressure",
                    "Control Module Voltage",
                ]
            )
        # Mercedes benzynowe (M271)
        elif vendor == "Mercedes" and "M271" in engine_code:
            active_sensors.extend(
                [
                    "Mercedes M271 Camshaft Phase Deviation",
                    "Intake Manifold Absolute Pressure",
                    "Control Module Voltage",
                ]
            )
        # Renault TCe
        elif vendor == "Renault" and "TCe" in engine_code:
            active_sensors.extend(
                [
                    "Renault TCe Manifold Boost Pressure",
                    "Control Module Voltage",
                ]
            )
        # VAG silniki benzynowe wolnossące (1.6 MPI 8V, VR6, 4.2 V8)
        elif not has_turbo and vendor == "VAG":
            if "VR6" in engine_code:
                active_sensors.extend(
                    [
                        "Camshaft Phase Bank 1 (Ch 208)",
                        "Camshaft Phase Bank 2 (Ch 209)",
                        "Engine Oil Temp",
                        "Intake Manifold Absolute Pressure",
                        "Throttle Position",
                        "Control Module Voltage",
                    ]
                )
            elif "4.2" in engine_code:
                active_sensors.extend(
                    [
                        "MAF Air Flow Rate Bank 1",
                        "MAF Air Flow Rate Bank 2",
                        "Engine Oil Temp",
                        "Throttle Position",
                        "Control Module Voltage",
                    ]
                )
            else:
                active_sensors.extend(
                    [
                        "Intake Manifold Absolute Pressure",
                        "Throttle Position",
                        "VAG Lambda Additive Idle",
                        "VAG Lambda Multiplicative Partial",
                        "VAG Coolant Temp G62",
                        "Control Module Voltage",
                    ]
                )
        # Silniki benzynowe turbodoładowane (1.8T 20V, 1.2 TSI, 1.4 TSI, 2.0 TFSI, 2.0 TSI)
        elif has_turbo and vendor == "VAG":
            if ecu_family == "ME7.5":
                active_sensors.extend(
                    [
                        "VAG Actual Boost G31",
                        "VAG Specified Boost KWP",
                        "VAG N75 Valve Duty Cycle",
                        "VAG Knock Retard Cyl 1",
                        "VAG Knock Retard Cyl 2",
                        "VAG Knock Retard Cyl 3",
                        "VAG Knock Retard Cyl 4",
                        "VAG Lambda Additive Idle",
                        "VAG Coolant Temp G62",
                        "Control Module Voltage",
                    ]
                )
            elif "2.0" in engine_code:
                active_sensors.extend(
                    [
                        "Boost Pressure",
                        "Boost Pressure Specified",
                        "Fuel Rail High Pressure Actual",
                        "Fuel Rail Low Pressure Actual",
                        "Engine Oil Temp",
                        "Control Module Voltage",
                        "MAF Air Flow Rate",
                    ]
                )
            else:
                active_sensors.extend(
                    [
                        "Boost Pressure",
                        "Boost Pressure Specified",
                        "Engine Oil Temp",
                        "Fuel Rail High Pressure Actual",
                        "Control Module Voltage",
                        "MAF Air Flow Rate",
                    ]
                )
        else:
            active_sensors.extend(
                [
                    "Intake Manifold Absolute Pressure",
                    "MAF Air Flow Rate",
                    "Throttle Position",
                    "Short Term Fuel Trim Bank 1",
                    "Control Module Voltage",
                ]
            )

        # -------------------------------------------------------------
        # Rekomendowane wskaźniki zegarowe na pulpit
        # -------------------------------------------------------------
        gauges = ["rpm", "speed", "coolant"]
        if has_turbo:
            gauges.append("boost")
        if has_dpf:
            gauges.append("dpf_soot")
        elif "PD" in engine_code:
            gauges.append("torsion_value")
        elif not has_turbo:
            gauges.append("voltage")

        # -------------------------------------------------------------
        # Rekomendowane testy elementów wykonawczych
        # -------------------------------------------------------------
        actuator_tests: list[str] = []
        if vendor == "VAG":
            actuator_tests.extend(
                [
                    "vag_hvac_v70_central_flap",
                    "vag_hvac_v68_temp_flap",
                    "vag_j17_fuel_pump_relay",
                    "vag_v7_cooling_fan",
                ]
            )
            if has_turbo:
                actuator_tests.append("vag_n75_boost_valve")
            if fuel_type == "petrol":
                actuator_tests.append("vag_n80_purge_valve")

        # Podsumowanie tekstowe
        year_str = f" ({model_year})" if model_year else ""
        gen_str = f" {generation}" if generation else ""
        summary = f"{brand} {model}{gen_str}{year_str} - {engine_name} [{ecu_family}]"

        return VehicleProfile(
            vin=vin_data.get("vin", vin or ""),
            vendor=vendor,
            brand=brand,
            model=model,
            generation=generation,
            model_year=model_year,
            engine_code=engine_code,
            engine_name=engine_name,
            fuel_type=fuel_type,
            has_turbo=has_turbo,
            has_dpf=has_dpf,
            ecu_family=ecu_family,
            recommended_protocol=recommended_proto,
            active_sensor_names=active_sensors,
            dashboard_gauge_keys=gauges,
            applicable_actuator_tests=actuator_tests,
            summary_description=summary,
        )
