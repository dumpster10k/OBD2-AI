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
        "WF0": ("Ford", "Ford"),
        "W0L": ("Opel", "Opel"),
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
        if "EDC16" in raw_norm or "03G906016" in raw_norm or "03G906021" in raw_norm:
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
        if "EDC17" in raw_norm or "03L906018" in raw_norm or "03L906022" in raw_norm:
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

        # VAG silniki Diesla
        if fuel_type == "diesel":
            if "PD" in engine_code or ecu_family == "EDC15P":
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
        # VAG silniki benzynowe wolnossące (1.6 MPI 8V)
        elif not has_turbo and vendor == "VAG":
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
        # Silniki benzynowe turbodoładowane (1.8T 20V, 1.2 TSI, 1.4 TSI, 2.0 TSI)
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
