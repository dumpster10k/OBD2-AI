from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

# Mockowanie modułu obd przed załadowaniem obd_client
sys.modules['obd'] = MagicMock()

from core.obd_client import OBDClient
from services.ai_engine import AIEngine
from services.diagnostic_ai import DiagnosisReport
from services.llm_engine import LLMModelSpec
from ui.main import AIDoctorApp, CarDoctorUI, DashboardController


class FakeOBDConnection:
    def __init__(self, dtc=None, rpm=0, speed=0, coolant=85, voltage=12.6, clear_succeeds=True):
        self.dtc = dtc or []
        self.rpm = rpm
        self.speed = speed
        self.coolant = coolant
        self.voltage = voltage
        self.clear_succeeds = clear_succeeds
        self.cleared = False

    def is_connected(self):
        return True

    def query(self, cmd):
        name = getattr(cmd, "name", "")
        if "GET_DTC" in name:
            class DTCRes:
                value = self.dtc
            return DTCRes()
        if "CLEAR_DTC" in name:
            self.cleared = True
            if self.clear_succeeds:
                self.dtc = []
            succ = self.clear_succeeds
            class ClearRes:
                def was_successful(self):
                    return succ
            return ClearRes()
        if "RPM" in name:
            return type("Res", (), {"value": type("Val", (), {"magnitude": self.rpm})()})()
        if "SPEED" in name:
            return type("Res", (), {"value": type("Val", (), {"magnitude": self.speed})()})()
        if "COOLANT" in name:
            return type("Res", (), {"value": type("Val", (), {"magnitude": self.coolant})()})()
        if "VOLTAGE" in name:
            return type("Res", (), {"value": type("Val", (), {"magnitude": self.voltage})()})()
        return None


def test_dashboard_controller_init():
    controller = DashboardController()
    assert controller.telemetry["rpm"] == 0
    assert controller.dtc_clear_pending is False
    assert controller.session_log == []


def test_dashboard_controller_refresh_telemetry():
    fake_conn = FakeOBDConnection(rpm=2200, speed=55, coolant=90, voltage=14.1)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)

    telemetry = controller.refresh_telemetry()
    assert telemetry["rpm"] == 2200
    assert telemetry["speed"] == 55
    assert telemetry["coolant_temp"] == 90
    assert abs(telemetry["voltage"] - 14.1) < 1e-4


def test_dashboard_controller_scan_and_diagnose_with_dtc():
    fake_conn = FakeOBDConnection(
        dtc=[("P0300", "Random Misfire"), "P0171"],
        rpm=2500,
        speed=0,
    )
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)

    codes, report = controller.scan_dtc_and_diagnose()
    assert len(codes) == 2
    assert report is not None
    assert isinstance(report, DiagnosisReport)
    assert report.overall_urgency in ["info", "warning", "critical", "low", "medium", "high"]
    assert controller.dtc_clear_pending is False


def test_dashboard_controller_scan_and_diagnose_clean():
    fake_conn = FakeOBDConnection(dtc=[], speed=0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)

    codes, report = controller.scan_dtc_and_diagnose()
    assert codes == []
    assert report is not None
    assert report.safe_to_drive is True


def test_dashboard_controller_clear_dtc_safety_when_moving():
    # AGENTS.md: Kasowanie dozwolone wyłącznie na postoju
    fake_conn = FakeOBDConnection(dtc=[("P0300", "Misfire")], speed=45)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    controller.refresh_telemetry()

    res = controller.request_clear_dtc()
    assert res["success"] is False
    assert res["pending"] is False
    assert "Pojazd w ruchu" in res["message"]
    assert controller.dtc_clear_pending is False


def test_dashboard_controller_two_step_clear_dtc_stationary():
    fake_conn = FakeOBDConnection(dtc=[("P0300", "Misfire")], speed=0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    controller.scan_dtc_and_diagnose()

    # Krok 1: Inicjacja żądania
    req = controller.request_clear_dtc()
    assert req["success"] is True
    assert req["pending"] is True
    assert controller.dtc_clear_pending is True

    # Krok 2: Potwierdzenie kasowania
    confirm = controller.confirm_clear_dtc()
    assert confirm["success"] is True
    assert controller.dtc_clear_pending is False
    assert controller.current_dtcs == []
    assert len(controller.session_log) == 1
    assert controller.session_log[0]["action"] == "clear_dtc"


def test_dashboard_controller_confirm_clear_failure_from_ecu():
    fake_conn = FakeOBDConnection(dtc=[("P0300", "Misfire")], speed=0, clear_succeeds=False)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    controller.scan_dtc_and_diagnose()

    controller.request_clear_dtc()
    confirm = controller.confirm_clear_dtc()
    assert confirm["success"] is False
    assert "nie powiodło się" in confirm["message"]


def test_dashboard_controller_confirm_clear_without_request():
    controller = DashboardController()
    res = controller.confirm_clear_dtc()
    assert res["success"] is False
    assert "Brak aktywnego żądania" in res["message"]


def test_dashboard_controller_confirm_clear_aborts_if_vehicle_starts_moving():
    fake_conn = FakeOBDConnection(dtc=[("P0300", "Misfire")], speed=0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    controller.scan_dtc_and_diagnose()

    controller.request_clear_dtc()
    assert controller.dtc_clear_pending is True

    # Pojazd nagle rusza
    controller.telemetry["speed"] = 30
    res = controller.confirm_clear_dtc()
    assert res["success"] is False
    assert "Pojazd ruszył" in res["message"]
    assert controller.dtc_clear_pending is False


def test_dashboard_controller_cancel_clear():
    controller = DashboardController()
    controller.dtc_clear_pending = True
    controller.cancel_clear_dtc()
    assert controller.dtc_clear_pending is False


def test_dashboard_controller_handle_voice_input():
    controller = DashboardController()
    # Test z tekstem
    query, answer, audio = controller.handle_voice_input(text_query="Czy mogę jechać?")
    assert "jechać" in query.lower()
    assert len(answer) > 0
    assert isinstance(audio, bytes)
    assert controller.last_voice_query == query
    assert controller.last_voice_response == answer

    # Test bezpośrednio z bajtami audio
    q2, a2, aud2 = controller.handle_voice_input(audio_data=audio)
    assert isinstance(q2, str)
    assert isinstance(a2, str)


def test_car_doctor_ui_widget_tree_and_callbacks():
    fake_conn = FakeOBDConnection(
        dtc=[("P0300", "Misfire")],
        rpm=2100,
        speed=0,
        coolant=89,
        voltage=13.9,
    )
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    # Weryfikacja struktury widżetów
    assert hasattr(ui, "rpm_label")
    assert hasattr(ui, "scan_btn")
    assert hasattr(ui, "clear_btn")
    assert hasattr(ui, "voice_btn")

    # Odświeżenie telemetrii
    ui.on_refresh_telemetry()
    assert "2100" in ui.rpm_label.text
    assert "89" in ui.coolant_label.text

    # Skanowanie błędów
    ui.on_scan_errors()
    assert "Wykryto 1 kod" in ui.status_label.text
    assert "Pilność:" in ui.urgency_badge.text

    # Dwuetapowe kasowanie: Krok 1
    ui.on_clear_dtc()
    assert "POTWIERDŹ KASOWANIE" in ui.clear_btn.text

    # Dwuetapowe kasowanie: Krok 2
    ui.on_clear_dtc()
    assert "Skasuj kody błędów DTC" in ui.clear_btn.text
    assert "Błędy DTC zostały pomyślnie skasowane" in ui.status_label.text

    # Ponowne skanowanie gdy brak błędów
    fake_conn.dtc = []
    ui.on_scan_errors()
    assert "Nie wykryto błędów DTC" in ui.status_label.text

    # Wywołanie asystenta głosowego z UI
    ui.on_voice_assistant()
    assert "Głos:" in ui.status_label.text
    assert "Odpowiedź asystenta głosowego" in ui.report_summary_label.text


def test_dashboard_controller_model_configuration():
    """Testuje konfigurację modeli AI w DashboardController."""
    controller = DashboardController()

    # Sprawdzenie dostępnych modeli
    assert controller.available_models is not None
    assert len(controller.available_models) >= 3

    # Sprawdzenie domyślnego modelu
    assert controller.current_model_spec is not None
    assert isinstance(controller.current_model_spec, LLMModelSpec)

    # Sprawdzenie statusu backendu
    assert controller.model_backend_status == "Dostępny (Mock)"


def test_dashboard_controller_on_model_select():
    """Testuje metodę on_model_select w DashboardController."""
    controller = DashboardController()

    # Wybór modelu
    selected_model = controller.available_models[1]
    controller.on_model_select(selected_model)

    # Weryfikacja
    assert controller.current_model_spec == selected_model
    assert controller.model_backend_status == "Dostępny (Mock)"


def test_car_doctor_ui_has_model_selector():
    """Testuje obecność panelu selektora modeli w UI."""
    fake_conn = FakeOBDConnection(dtc=[], speed=0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    # Sprawdzenie widżetów selektora
    assert hasattr(ui, "model_status_label")
    assert hasattr(ui, "models_grid")

    # Weryfikacja początkowego statusu
    assert "Nie wybrano" in ui.model_status_label.text


def test_car_doctor_ui_model_selection():
    """Testuje wybór modelu w UI."""
    fake_conn = FakeOBDConnection(dtc=[], speed=0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    # Pobranie pierwszego przycisku z karty modelu
    if ui.models_grid.children:
        first_card = ui.models_grid.children[0]
        if hasattr(first_card, 'children') and first_card.children:
            first_btn = first_card.children[-1]  # Ostatni widżet to przycisk
            if hasattr(first_btn, 'user_data'):
                model = first_btn.user_data
                if model:
                    # Wybór modelu
                    ui._on_model_card_press(first_btn)

                    # Weryfikacja statusu
                    assert controller.current_model_spec == model
                    assert "Model AI:" in ui.model_status_label.text
                    assert ui.model_status_label.color == 0x00FF00


def test_ai_doctor_app_build_and_run():
    app = AIDoctorApp()
    widget = app.build()
    assert isinstance(widget, CarDoctorUI)
    app.run()
