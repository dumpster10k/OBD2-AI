import time
from unittest.mock import MagicMock

from services.actuator_testing import (
    ActuatorCatalog,
    ActuatorProtocol,
    ActuatorSafetyPreflight,
    ActuatorTestCategory,
    ActuatorTestDefinition,
    ActuatorTestRunner,
    ActuatorTestStatus,
)
from ui.main import DashboardController


def test_actuator_catalog_list_and_filter():
    """Weryfikuje pobieranie testów z katalogu fabrycznego oraz filtrowanie po kategoriach."""
    all_tests = ActuatorCatalog.list_tests()
    assert len(all_tests) >= 10

    engine_tests = ActuatorCatalog.list_tests(category=ActuatorTestCategory.ENGINE)
    assert any(t.test_id == "vag_n80_evap" for t in engine_tests)
    assert any(t.test_id == "vag_n75_wastegate" for t in engine_tests)
    assert all(t.category == ActuatorTestCategory.ENGINE for t in engine_tests)

    hvac_tests = ActuatorCatalog.list_tests(category=ActuatorTestCategory.HVAC)
    assert any(t.test_id == "vag_hvac_v70_central_flap" for t in hvac_tests)
    assert any(t.test_id == "vag_hvac_basic_settings_001" for t in hvac_tests)
    assert all(t.category == ActuatorTestCategory.HVAC for t in hvac_tests)

    instruments_tests = ActuatorCatalog.list_tests(category=ActuatorTestCategory.INSTRUMENTS)
    assert any(t.test_id == "vag_kombi_needle_sweep" for t in instruments_tests)


def test_actuator_catalog_get_and_register():
    """Weryfikuje pobieranie pojedynczego testu oraz dynamiczną rejestrację nowego testu."""
    n80 = ActuatorCatalog.get_test("vag_n80_evap")
    assert n80 is not None
    assert n80.target_ecu == "01"
    assert n80.requires_engine_off is True
    assert "N80" in n80.name

    assert ActuatorCatalog.get_test("non_existent_id") is None

    custom_test = ActuatorTestDefinition(
        test_id="custom_aux_heater",
        name="Dogrzewacz Webasto Thermo Top",
        category=ActuatorTestCategory.BODY,
        target_ecu="18",
        protocol=ActuatorProtocol.KWP2000,
        start_payload="031801",
        stop_payload="031800",
        duration_sec=20.0,
        operator_instruction="Sprawdź start pompki paliwa Webasto.",
        evaluation_prompt="Czy dogrzewacz wystartował?",
    )
    ActuatorCatalog.register_test(custom_test)
    assert ActuatorCatalog.get_test("custom_aux_heater") == custom_test


def test_safety_preflight_checks():
    """Weryfikuje twarde reguły bezpieczeństwa (Pre-flight Interlocks) zgodnie z AGENTS.md pkt 7."""
    test = ActuatorCatalog.get_test("vag_n80_evap")
    assert test is not None

    # 1. Pojazd w ruchu -> Odrzucenie
    safe, msg = ActuatorSafetyPreflight.verify({"speed": 15.0, "rpm": 0, "voltage": 12.5}, test)
    assert safe is False
    assert "Pojazd jest w ruchu" in msg

    # 2. Silnik uruchomiony -> Odrzucenie
    safe, msg = ActuatorSafetyPreflight.verify({"speed": 0.0, "rpm": 850, "voltage": 14.1}, test)
    assert safe is False
    assert "Silnik pracuje" in msg

    # 3. Zbyt niskie napięcie akumulatora -> Odrzucenie
    safe, msg = ActuatorSafetyPreflight.verify({"speed": 0.0, "rpm": 0, "voltage": 11.4}, test)
    assert safe is False
    assert "napięcie akumulatora" in msg

    # 4. Wszystkie warunki spełnione (Postój, Ignition ON, Engine OFF, V >= 12.0) -> Pozytywny
    safe, msg = ActuatorSafetyPreflight.verify({"speed": 0.0, "rpm": 0, "voltage": 12.4}, test)
    assert safe is True
    assert "spełnione" in msg


def test_actuator_runner_lifecycle_and_watchdog():
    """Weryfikuje pełny cykl życia testu podzespołu od uruchomienia do watchdog timeoutu."""
    mock_logger = MagicMock()
    runner = ActuatorTestRunner(obd_client=None, telemetry_logger=mock_logger, mock_mode=True)

    t0 = 1000.0
    telemetry = {"speed": 0.0, "rpm": 0, "voltage": 12.6}

    # 1. Nieznany test
    res = runner.start_test("unknown_test", telemetry, now=t0)
    assert res.status == ActuatorTestStatus.FAILED_PREFLIGHT

    # 2. Start poprawnego testu N80
    res = runner.start_test("vag_n80_evap", telemetry, now=t0)
    assert res.status == ActuatorTestStatus.RUNNING
    assert runner.is_running is True
    assert runner.active_test is not None
    assert runner.active_test.test_id == "vag_n80_evap"
    assert "SIMULATED_ACK" in res.ecu_responses[0]
    mock_logger.log_audit_event.assert_called()

    # 3. Próba uruchomienia drugiego testu w trakcie trwania pierwszego
    conflict_res = runner.start_test("vag_n75_wastegate", telemetry, now=t0 + 2.0)
    assert conflict_res.status == ActuatorTestStatus.FAILED_PREFLIGHT
    assert "Inny test" in conflict_res.message

    # 4. Odpytanie w trakcie (upływ 5 sekund < 15 sekund duration)
    prog_res = runner.update_progress(telemetry, now=t0 + 5.0)
    assert prog_res.status == ActuatorTestStatus.RUNNING
    assert runner.is_running is True

    # 5. Watchdog Timeout (upływ 15.5 sekundy >= 15.0 s) -> Zakończenie i wysłanie stop_payload
    end_res = runner.update_progress(telemetry, now=t0 + 15.5)
    assert end_res.status == ActuatorTestStatus.COMPLETED
    assert runner.is_running is False
    assert runner.active_test is None
    assert "Czy słyszałeś wyraźne" in end_res.message
    assert len(end_res.ecu_responses) >= 2  # start + stop

    # 6. Odpytanie update_progress gdy nic nie działa
    idle_res = runner.update_progress(telemetry, now=t0 + 20.0)
    assert idle_res.status == ActuatorTestStatus.COMPLETED  # Zwraca last_result


def test_actuator_runner_emergency_abort():
    """Weryfikuje ręczne awaryjne zatrzymanie testu (Emergency Abort)."""
    mock_logger = MagicMock()
    runner = ActuatorTestRunner(obd_client=None, telemetry_logger=mock_logger, mock_mode=True)

    t0 = 2000.0
    telemetry = {"speed": 0.0, "rpm": 0, "voltage": 12.5}
    runner.start_test("vag_n75_wastegate", telemetry, now=t0)
    assert runner.is_running is True

    # Emergency abort
    abort_res = runner.abort_test(reason="Przycisk STOP na ekranie", now=t0 + 3.0)
    assert abort_res.status == ActuatorTestStatus.ABORTED
    assert runner.is_running is False
    assert runner.active_test is None
    assert "STOP" in abort_res.message

    # Kolejny abort bez aktywnego testu
    abort_res2 = runner.abort_test()
    assert abort_res2.status == ActuatorTestStatus.IDLE


def test_actuator_runner_runtime_violation_abort():
    """Weryfikuje automatyczne przerwanie, gdy podczas testu pojazd ruszy lub uruchomi się silnik."""
    mock_logger = MagicMock()
    runner = ActuatorTestRunner(obd_client=None, telemetry_logger=mock_logger, mock_mode=True)

    t0 = 3000.0
    telemetry_ok = {"speed": 0.0, "rpm": 0, "voltage": 12.5}
    runner.start_test("vag_hvac_v2_blower", telemetry_ok, now=t0)
    assert runner.is_running is True

    # Nagły rozruch silnika lub ruszenie pojazdu w 4. sekundzie testu
    telemetry_violation = {"speed": 10.0, "rpm": 1200, "voltage": 13.8}
    abort_res = runner.update_progress(telemetry_violation, now=t0 + 4.0)
    assert abort_res.status == ActuatorTestStatus.ABORTED
    assert runner.is_running is False
    assert "AWARYJNE PRZERWANIE" in abort_res.message


def test_actuator_operator_feedback():
    """Weryfikuje zapis subiektywnej oceny mechanika / operatora po teście."""
    mock_logger = MagicMock()
    runner = ActuatorTestRunner(obd_client=None, telemetry_logger=mock_logger, mock_mode=True)

    t0 = 4000.0
    telemetry = {"speed": 0.0, "rpm": 0, "voltage": 12.5}
    runner.start_test("vag_n80_evap", telemetry, now=t0)
    runner.update_progress(telemetry, now=t0 + 16.0)  # Koniec testu

    # Weryfikacja pozytywna
    res = runner.record_operator_feedback("vag_n80_evap", passed=True, notes="Słychać głośne tykanie")
    assert res is not None
    assert res.operator_verified is True

    # Nieprawidłowe ID testu
    assert runner.record_operator_feedback("other_id", passed=False) is None


def test_actuator_runner_with_obd_client_connection():
    """Weryfikuje wysyłanie poleceń do podłączonego adaptera OBDClient."""
    mock_conn = MagicMock()
    mock_conn.send.return_value = "41 03 01"
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True
    mock_client.connection = mock_conn

    runner = ActuatorTestRunner(obd_client=mock_client, mock_mode=False)
    telemetry = {"speed": 0.0, "rpm": 0, "voltage": 12.5}
    res = runner.start_test("vag_n80_evap", telemetry)
    assert res.status == ActuatorTestStatus.RUNNING
    mock_conn.send.assert_called_with("030101")


def test_dashboard_controller_actuator_integration():
    """Weryfikuje integrację testów podzespołów z kontrolerem pulpitu (DashboardController)."""
    controller = DashboardController()
    controller.telemetry = {"speed": 0.0, "rpm": 0, "voltage": 12.5}

    # 1. Lista testów przez kontroler
    all_tests = controller.list_actuator_tests()
    assert len(all_tests) >= 10
    hvac_tests = controller.list_actuator_tests(category="hvac")
    assert len(hvac_tests) >= 4
    assert all(t.category == ActuatorTestCategory.HVAC for t in hvac_tests)

    # 2. Uruchomienie testu N80 przez kontroler
    start_res = controller.start_actuator_test("vag_n80_evap")
    assert start_res.status == ActuatorTestStatus.RUNNING

    # 3. Postęp i zakończenie
    controller.actuator_runner._test_start_time = time.time() - 20.0
    prog_res = controller.update_actuator_progress()
    assert prog_res.status == ActuatorTestStatus.COMPLETED

    # 4. Zapis feedbacku
    fb_res = controller.record_actuator_feedback("vag_n80_evap", passed=True, notes="OK")
    assert fb_res is not None
    assert fb_res.operator_verified is True

    # 5. Emergency abort przez kontroler
    controller.start_actuator_test("vag_n75_wastegate")
    abort_res = controller.abort_actuator_test(reason="Przerwano test z GUI")
    assert abort_res.status == ActuatorTestStatus.ABORTED
