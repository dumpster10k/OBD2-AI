from __future__ import annotations

from pathlib import Path

from services.diagnostic_knowledge_base import (
    DiagnosticKnowledgeBase,
    DiagnosticProcedureRegistry,
    LookupStatus,
    SensorLocationCatalog,
)


def test_sensor_location_catalog() -> None:
    # 1. Czujnik doładowania MAP G31
    loc_boost = SensorLocationCatalog.get_location("boost_pressure")
    assert loc_boost is not None
    assert "G31" in loc_boost.full_name
    assert "Grupa 115" in loc_boost.channel_kwp
    assert "intercooler" in loc_boost.physical_location.lower()

    # 2. Pompa wysokiego ciśnienia HPFP G247
    loc_hpfp = SensorLocationCatalog.get_location("fuel_pressure_high")
    assert loc_hpfp is not None
    assert "G247" in loc_hpfp.full_name
    assert "Grupa 140" in loc_hpfp.channel_kwp

    # 3. Czujnik różnicy ciśnień DPF G450
    loc_dpf = SensorLocationCatalog.get_location("dpf_differential_pressure")
    assert loc_dpf is not None
    assert "G450" in loc_dpf.full_name
    assert "grodziowej" in loc_dpf.physical_location

    # 4. Fazy rozrządu VR6 (208/209)
    loc_cam = SensorLocationCatalog.get_location("camshaft_phase")
    assert loc_cam is not None
    assert "208" in loc_cam.channel_kwp
    assert "209" in loc_cam.channel_kwp

    # 5. Nieznany czujnik
    assert SensorLocationCatalog.get_location("unknown_sensor_xyz") is None

    # 6. Nowe czujniki europejskie i światowe
    loc_vvt = SensorLocationCatalog.get_location("bmw_valvetronic")
    assert loc_vvt is not None
    assert "Valvetronic" in loc_vvt.full_name
    assert "0x2005" in loc_vvt.obd_pid

    loc_eolys = SensorLocationCatalog.get_location("psa_fap_additive")
    assert loc_eolys is not None
    assert "Eolys" in loc_eolys.full_name

    loc_wet_belt = SensorLocationCatalog.get_location("ford_psa_wet_belt")
    assert loc_wet_belt is not None
    assert "Wet Belt" in loc_wet_belt.full_name

    loc_toyota_hv = SensorLocationCatalog.get_location("toyota_hybrid_battery")
    assert loc_toyota_hv is not None
    assert "baterii trakcyjnej" in loc_toyota_hv.full_name


def test_diagnostic_procedure_registry() -> None:
    # 1. Procedura niedoładowania P0299
    proc_turbo = DiagnosticProcedureRegistry.find_by_dtc("P0299")
    assert proc_turbo is not None
    assert "Niedładowanie" in proc_turbo.title
    assert len(proc_turbo.steps) >= 3
    assert any("N75" in s.title for s in proc_turbo.steps)

    # 2. Procedura ubogiej mieszanki P0171
    proc_lean = DiagnosticProcedureRegistry.find_by_dtc("P0171")
    assert proc_lean is not None
    assert "Zbyt uboga" in proc_lean.title
    assert any("032" in s.title for s in proc_lean.steps)

    # 3. Procedura szklanki pompy HPFP P0087
    proc_hpfp = DiagnosticProcedureRegistry.find_by_dtc("P0087")
    assert proc_hpfp is not None
    assert "szklanki" in proc_hpfp.steps[1].title.lower() or "cam follower" in proc_hpfp.steps[1].title.lower()

    # 4. Procedura Valvetronic BMW 2A67
    proc_vvt = DiagnosticProcedureRegistry.find_by_dtc("2A67")
    assert proc_vvt is not None
    assert "Valvetronic" in proc_vvt.title
    assert any("wtyczce" in s.title.lower() for s in proc_vvt.steps)

    # 5. Procedura paska w oleju PureTech/EcoBoost P15A4
    proc_puretech = DiagnosticProcedureRegistry.find_by_dtc("P15A4")
    assert proc_puretech is not None
    assert "wet-belt" in proc_puretech.title.lower()
    assert any("przymiarem" in s.title.lower() for s in proc_puretech.steps)

    # 6. Procedura baterii hybrydowej Toyota P0A80
    proc_toyota = DiagnosticProcedureRegistry.find_by_dtc("P0A80")
    assert proc_toyota is not None
    assert "baterii trakcyjnej" in proc_toyota.title.lower()
    assert any("delta" in s.title.lower() for s in proc_toyota.steps)

    # 7. Procedura łańcucha rozrządu BMW N47 P0016
    proc_n47 = DiagnosticProcedureRegistry.find_by_dtc("P0016")
    assert proc_n47 is not None
    assert "łańcucha" in proc_n47.title.lower()

    # 4. Pobieranie po ID
    proc_by_id = DiagnosticProcedureRegistry.get_procedure("dpf_regeneration_failure")
    assert proc_by_id is not None
    assert "DPF" in proc_by_id.title


def test_diagnostic_knowledge_base_offline_known(tmp_path: Path) -> None:
    db_file = tmp_path / "knowledge_test.db"
    kb = DiagnosticKnowledgeBase(db_path=db_file)

    # Znany kod z bazy wbudowanej
    res = kb.lookup_dtc("P0171")
    assert res.status == LookupStatus.FOUND_OFFLINE
    assert "ubog" in res.description.lower()
    assert res.diagnostic_procedure is not None


def test_diagnostic_knowledge_base_web_consent_flow(tmp_path: Path) -> None:
    db_file = tmp_path / "knowledge_test.db"
    kb = DiagnosticKnowledgeBase(db_path=db_file)

    # Rzadki kod, którego nie ma w offline bazie
    uncommon_code = "P1654"
    context = {"vin": "WAUZZZ8E74A123456", "engine_code": "2.0 TFSI"}

    # 1. Zapytanie bez zgody na sieć -> Wymaga potwierdzenia użytkownika
    res_prompt = kb.lookup_dtc(uncommon_code, vehicle_context=context, allow_web_search=False)
    assert res_prompt.status == LookupStatus.NEEDS_USER_CONFIRMATION
    assert res_prompt.confirmation_prompt is not None
    assert "Czy zezwalasz asystentowi" in res_prompt.confirmation_prompt
    # Bezpieczeństwo: VIN musi być zamaskowany
    assert "WAU***" in res_prompt.confirmation_prompt
    assert "WAUZZZ8E74A123456" not in res_prompt.confirmation_prompt

    # 2. Użytkownik wyraża zgodę -> Wyszukiwanie online i zapis w cache
    res_online = kb.lookup_dtc(uncommon_code, vehicle_context=context, allow_web_search=True)
    assert res_online.status == LookupStatus.FOUND_ONLINE
    assert "Biuletyn techniczny" in res_online.description

    # 3. Kolejne zapytanie o ten sam kod -> Działa natychmiast offline z cache!
    res_cached = kb.lookup_dtc(uncommon_code, vehicle_context=context, allow_web_search=False)
    assert res_cached.status == LookupStatus.FOUND_OFFLINE
    assert res_cached.source == "local_cache"


def test_explain_sensor_location(tmp_path: Path) -> None:
    kb = DiagnosticKnowledgeBase(db_path=tmp_path / "test.db")

    explanation = kb.explain_sensor_location("boost_pressure")
    assert "G31" in explanation
    assert "Grupa 115" in explanation
    assert "Lokalizacja fizyczna" in explanation

    unknown_exp = kb.explain_sensor_location("non_existent_part")
    assert "Sprawdź standardowe grupy" in unknown_exp
