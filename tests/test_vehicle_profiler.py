from __future__ import annotations

from services.vehicle_profiler import ECUIdentifier, VehicleProfile, VehicleProfiler, VINDecoder
from ui.main import DashboardController


def test_vin_decoder_audi_a4_b6():
    # WAU = Audi, 8E = A4 B6/B7, 3 = 2003 r.
    vin = "WAUZZZ8E33A123456"
    res = VINDecoder.decode(vin)
    assert res["valid"] is True
    assert res["vendor"] == "VAG"
    assert res["brand"] == "Audi"
    assert "A4" in res["model"]
    assert "B6" in res["generation"]
    assert res["model_year"] == 2003


def test_vin_decoder_vw_golf_4():
    # WVW = VW, 1J = Golf 4, 1 = 2001 r.
    vin = "WVWZZZ1JZ1W654321"
    res = VINDecoder.decode(vin)
    assert res["valid"] is True
    assert res["brand"] == "Volkswagen"
    assert "Golf" in res["model"]
    assert res["model_year"] == 2001


def test_vin_decoder_skoda_and_seat():
    # TMB = Skoda, 1Z = Octavia 2, 8 = 2008 r.
    skoda_res = VINDecoder.decode("TMBBK41Z882123456")
    assert skoda_res["brand"] == "Skoda"
    assert "Octavia" in skoda_res["model"]
    assert skoda_res["model_year"] == 2008

    # VSS = Seat, 1P = Leon 2, A = 2010 r.
    seat_res = VINDecoder.decode("VSSZZZ1PZAR123456")
    assert seat_res["brand"] == "Seat"
    assert "Leon" in seat_res["model"]
    assert seat_res["model_year"] == 2010


def test_vin_decoder_invalid_or_short():
    res = VINDecoder.decode("SHORT")
    assert res["valid"] is False


def test_ecu_identifier_vag_1_6_mpi():
    # 1.6 MPI 8V (BSE / ALZ - Simos)
    ecu_info = ECUIdentifier.identify("06A906033 BSE 1.6 Simos")
    assert ecu_info["vendor"] == "VAG"
    assert "1.6 MPI" in ecu_info["engine_name"]
    assert ecu_info["fuel_type"] == "petrol"
    assert ecu_info["has_turbo"] is False
    assert ecu_info["has_dpf"] is False
    assert ecu_info["ecu_family"] == "Simos3"


def test_ecu_identifier_vag_1_6_fsi():
    # 1.6 FSI (BLF / BAG - MED9.5)
    ecu_info = ECUIdentifier.identify("03C906056 BLF 1.6 FSI MED9")
    assert "1.6 FSI" in ecu_info["engine_name"]
    assert ecu_info["has_turbo"] is False
    assert ecu_info["fuel_type"] == "petrol"


def test_ecu_identifier_vag_1_6_tdi_cr():
    # 1.6 TDI CR (CAYC 105KM / PCR2.1)
    ecu_info = ECUIdentifier.identify("03L906023 CAYC PCR2.1")
    assert "1.6 TDI" in ecu_info["engine_name"]
    assert ecu_info["fuel_type"] == "diesel"
    assert ecu_info["has_turbo"] is True
    assert ecu_info["has_dpf"] is True
    assert ecu_info["ecu_family"] == "PCR2.1"


def test_ecu_identifier_vag_small_tsi():
    # 1.2 TSI EA111 (CBZA Simos10)
    tsi_12 = ECUIdentifier.identify("03F906070 CBZA Simos10")
    assert "1.2 TSI" in tsi_12["engine_name"]
    assert tsi_12["has_turbo"] is True

    # 1.4 TSI EA111 (CAXA MED17)
    tsi_14 = ECUIdentifier.identify("03C906016 CAXA MED17")
    assert "1.4 TSI" in tsi_14["engine_name"]
    assert tsi_14["has_turbo"] is True

    # 1.0/1.2/1.4 TSI EA211 (V465 wastegate)
    tsi_ea211 = ECUIdentifier.identify("MED17.5.21 EA211 CZCA")
    assert "EA211" in tsi_ea211["engine_name"]
    assert tsi_ea211["has_turbo"] is True


def test_ecu_identifier_vag_1_8t_and_1_9_tdi():
    # 1.8T 20V ME7.5
    me7 = ECUIdentifier.identify("06B906018 BFB ME7.5 1.8T")
    assert "1.8T" in me7["engine_name"]
    assert me7["has_turbo"] is True
    assert me7["fuel_type"] == "petrol"

    # 1.9 TDI PD EDC15P
    edc15 = ECUIdentifier.identify("038906019FP AVF EDC15P")
    assert "1.9 TDI PD" in edc15["engine_name"]
    assert edc15["has_turbo"] is True
    assert edc15["has_dpf"] is False
    assert edc15["recommended_protocol"] == "KWP1281"


def test_vehicle_profiler_detect_and_sensor_configuration():
    # 1. Test dla Audi A4 B6 1.9 TDI PD
    p_tdi = VehicleProfiler.detect_profile(
        vin="WAUZZZ8E33A123456",
        ecu_id="038906019FP AVF EDC15",
    )
    assert p_tdi.brand == "Audi"
    assert "A4" in p_tdi.model
    assert p_tdi.model_year == 2003
    assert p_tdi.fuel_type == "diesel"
    assert "VAG Torsion Value" in p_tdi.active_sensor_names
    assert "VAG Actual Boost G31" in p_tdi.active_sensor_names
    assert "torsion_value" in p_tdi.dashboard_gauge_keys
    assert "vag_n75_boost_valve" in p_tdi.applicable_actuator_tests

    # 2. Test dla Golfa 4 1.6 MPI (BSE wolnossący)
    p_mpi = VehicleProfiler.detect_profile(
        vin="WVWZZZ1JZ3W654321",
        ecu_id="06A906033 BSE 1.6",
    )
    assert p_mpi.brand == "Volkswagen"
    assert "Golf" in p_mpi.model
    assert p_mpi.has_turbo is False
    assert "Throttle Position" in p_mpi.active_sensor_names
    assert "VAG Lambda Additive Idle" in p_mpi.active_sensor_names
    assert "vag_n80_purge_valve" in p_mpi.applicable_actuator_tests

    # 3. Test dla Skody Octavia 1.6 TDI CR (CAYC DPF)
    p_cr = VehicleProfiler.detect_profile(
        vin="TMBBK41Z882123456",
        ecu_id="03L906023 CAYC PCR2.1",
    )
    assert p_cr.brand == "Skoda"
    assert p_cr.has_dpf is True
    assert "DPF Soot Mass" in p_cr.active_sensor_names
    assert "EGT Temp pre Turbo" in p_cr.active_sensor_names
    assert "dpf_soot" in p_cr.dashboard_gauge_keys


def test_dashboard_controller_vehicle_profiling_integration():
    controller = DashboardController()

    # Automatyczne profilowanie w scenariuszu symulacji
    scen = controller.load_simulation_scenario("lean_mix")
    assert scen["name"] == "Uboga mieszanka / MAF (P0171, P0101)"
    assert controller.vehicle_profile.brand == "Volkswagen"
    assert "1.6 MPI" in controller.vehicle_profile.engine_name

    # Scenariusz wypadania zapłonów
    controller.load_simulation_scenario("misfire")
    assert controller.vehicle_profile.brand == "Audi"
    assert "1.8T" in controller.vehicle_profile.engine_name

    # Ręczne wykrycie profilu
    prof = controller.detect_and_apply_vehicle_profile(
        vin="WAUZZZ8E13A123456",
        ecu_id="038906019FP AVF 1.9 TDI",
    )
    assert isinstance(prof, VehicleProfile)
    assert "1.9 TDI" in prof.engine_name
    assert controller.vehicle_profile == prof


def test_ecu_identifier_vag_expanded_engines():
    # 2.0 TFSI EA113 (BWA / MED9.1)
    tfsi_ea113 = ECUIdentifier.identify("1K0907115 BWA MED9.1")
    assert "2.0 TFSI EA113" in tfsi_ea113["engine_code"]
    assert tfsi_ea113["has_turbo"] is True
    assert tfsi_ea113["fuel_type"] == "petrol"

    # 2.0 TSI EA888 (CHHA Simos18)
    tsi_ea888 = ECUIdentifier.identify("5G0906259 CHHA Simos18 EA888")
    assert "2.0 TSI EA888" in tsi_ea888["engine_code"]
    assert tsi_ea888["has_turbo"] is True

    # 3.0 TDI V6 CR (ASB / EDC16CP34 / CDUC)
    tdi_v6 = ECUIdentifier.identify("4F0907401 ASB 3.0TDI EDC16CP34")
    assert "3.0 TDI V6" in tdi_v6["engine_code"]
    assert tdi_v6["has_dpf"] is True
    assert tdi_v6["fuel_type"] == "diesel"

    # VR6 3.2 (BUB ME7.1.1)
    vr6 = ECUIdentifier.identify("022906032 BUB R32 VR6")
    assert "VR6" in vr6["engine_code"]
    assert vr6["has_turbo"] is False

    # 4.2 V8 (BBK S4)
    v8 = ECUIdentifier.identify("8E0907559 BBK 4.2V8")
    assert "4.2 V8" in v8["engine_code"]
    assert v8["has_turbo"] is False


def test_vehicle_profiler_expanded_sensor_sets():
    p_tfsi = VehicleProfiler.detect_profile(vin="WAUZZZ8P15A123456", ecu_id="8P0907115 BWA")
    assert "Fuel Rail High Pressure Actual" in p_tfsi.active_sensor_names
    assert "Fuel Rail Low Pressure Actual" in p_tfsi.active_sensor_names

    p_vr6 = VehicleProfiler.detect_profile(vin="WVWZZZ1KZ8W123456", ecu_id="BUB VR6")
    assert "Camshaft Phase Bank 1 (Ch 208)" in p_vr6.active_sensor_names
