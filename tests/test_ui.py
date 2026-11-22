from __future__ import annotations

from core.obd_client import OBDClient
from services.diagnostic_ai import DiagnosisReport
from services.llm_engine import LLMModelSpec
from services.speech_service import SpeechModelSpec
from ui.main import (
    COLOR_DANGER,
    COLOR_SUCCESS,
    AIDoctorApp,
    CarDoctorUI,
    DashboardController,
)


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


def test_ai_doctor_app_build_and_run(monkeypatch):
    app = AIDoctorApp()
    widget = app.build()
    assert isinstance(widget, CarDoctorUI)
    monkeypatch.setattr(app, "run", lambda: None)
    app.run()


def test_car_doctor_ui_telemetry_warning_and_critical_colors():
    fake_conn = FakeOBDConnection(
        dtc=[],
        rpm=1500,
        speed=0,
        coolant=108,  # Warning
        voltage=11.2,  # Low voltage warning
    )
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    ui.on_refresh_telemetry()
    assert tuple(ui.coolant_label.color) == (0.96, 0.62, 0.14, 1.0)
    assert tuple(ui.voltage_label.color) == (0.96, 0.62, 0.14, 1.0)

    # Coolant critical >= 115
    fake_conn.coolant = 120
    ui.on_refresh_telemetry()
    assert tuple(ui.coolant_label.color) == (0.88, 0.11, 0.28, 1.0)


def test_car_doctor_ui_critical_urgency_badge():
    # P0600 - magistrala CAN lub wysokie obroty + misfire
    fake_conn = FakeOBDConnection(
        dtc=["P0600"],
        rpm=3500,
        speed=0,
        coolant=90,
    )
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    ui.on_scan_errors()
    assert "CRITICAL" in ui.urgency_badge.text
    assert tuple(ui.urgency_badge.color) == (0.88, 0.11, 0.28, 1.0)


def test_dashboard_controller_simulation_mode():
    controller = DashboardController()
    assert controller.simulation_mode is False

    # Włączenie symulacji z domyślnym scenariuszem
    scen = controller.enable_simulation("misfire")
    assert controller.simulation_mode is True
    assert controller.active_scenario == "misfire"
    assert len(controller.simulated_dtc) == 2
    assert controller.telemetry["rpm"] == 2800

    # Skanowanie w trybie symulacji
    codes, report = controller.scan_dtc_and_diagnose()
    assert len(codes) == 2
    assert report is not None
    assert report.safe_to_drive is True or report.overall_urgency in ["warning", "critical", "info"]

    # Zmiana na scenariusz przegrzania
    scen_overheat = controller.load_simulation_scenario("overheat")
    assert scen_overheat["name"] == "Przegrzanie silnika (Krytyczne P0217)"
    assert controller.telemetry["coolant_temp"] == 119
    _, report_overheat = controller.scan_dtc_and_diagnose()
    assert report_overheat.overall_urgency == "critical"
    assert report_overheat.safe_to_drive is False

    # Kasowanie DTC w trybie symulacji na postoju
    controller.simulated_telemetry["speed"] = 0
    controller.refresh_telemetry()
    controller.request_clear_dtc()
    clear_res = controller.confirm_clear_dtc()
    assert clear_res["success"] is True
    assert controller.simulated_dtc == []
    assert controller.current_dtcs == []

    # Wyłączenie symulacji
    controller.disable_simulation()
    assert controller.simulation_mode is False


def test_dashboard_controller_telemetry_history_buffer():
    controller = DashboardController()
    # Zapis ponad 50 punktów dla weryfikacji ograniczenia bufora
    for i in range(65):
        controller.record_telemetry_point({"rpm": 1000 + i, "speed": i, "coolant_temp": 80, "voltage": 14.0})

    hist_rpm = controller.get_telemetry_history("rpm")
    assert len(hist_rpm) == 50
    assert hist_rpm[-1] == 1064.0

    hist_speed = controller.get_telemetry_history("speed")
    assert len(hist_speed) == 50
    assert hist_speed[-1] == 64.0


def test_telemetry_chart_metrics_and_history():
    from ui.main import TelemetryChart

    chart = TelemetryChart()

    # Zmiana metryk
    chart.set_metric("speed")
    assert chart.current_metric == "speed"
    assert "PRĘDKOŚĆ" in chart.chart_title.text

    chart.set_metric("coolant_temp")
    assert chart.current_metric == "coolant_temp"
    assert "PŁYN" in chart.chart_title.text

    chart.set_metric("voltage")
    assert chart.current_metric == "voltage"
    assert "NAPIĘCIE" in chart.chart_title.text

    chart.set_metric("rpm")
    assert chart.current_metric == "rpm"

    # Aktualizacja historii próbkowania
    chart.update_history([800.0, 1200.0, 2500.0, 3100.0])
    assert "Bieżące: 3100 RPM" in chart.stats_label.text
    assert "Min: 800 RPM" in chart.stats_label.text
    assert "Max: 3100 RPM" in chart.stats_label.text


def test_car_doctor_ui_simulation_and_chart_integration():
    fake_conn = FakeOBDConnection(dtc=[], rpm=800, speed=0, coolant=85, voltage=14.0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    # Weryfikacja obecności komponentów wykresu i symulatora
    assert hasattr(ui, "chart")
    assert hasattr(ui, "sim_toggle_btn")
    assert hasattr(ui, "btn_scen_overheat")

    # Przełączenie trybu symulacji z poziomu UI
    ui.on_toggle_simulation()
    assert controller.simulation_mode is True
    assert "Symulacja: WŁ" in ui.sim_toggle_btn.text

    # Wybór scenariusza przegrzania
    ui.on_select_scenario("overheat")
    assert controller.active_scenario == "overheat"
    assert "Wykryto 1 kod" in ui.status_label.text
    assert "CRITICAL" in ui.urgency_badge.text

    # Wyłączenie symulacji przez ponowne kliknięcie toggle
    ui.on_toggle_simulation()
    assert controller.simulation_mode is False
    assert "Symulacja: WYŁ" in ui.sim_toggle_btn.text


def test_dashboard_controller_connection_profiles():
    controller = DashboardController()

    # Profil Mobile Bluetooth
    prof_mobile = controller.apply_connection_profile("mobile_bt")
    assert prof_mobile["type"] == "bluetooth"
    assert prof_mobile["port"] == "OBDII"
    assert controller.connection_config["port"] == "OBDII"

    # Profil Laptop USB Linux
    prof_linux = controller.apply_connection_profile("laptop_usb_linux")
    assert prof_linux["type"] == "usb"
    assert prof_linux["port"] == "/dev/ttyUSB0"
    assert prof_linux["baudrate"] == 115200

    # Ręczna zmiana parametrów
    custom = controller.update_connection_settings(port="COM7", baudrate=38400, connection_type="usb")
    assert custom["port"] == "COM7"
    assert custom["baudrate"] == 38400


def test_dashboard_controller_connect_and_disconnect_obd():
    class ConnectableClient:
        def __init__(self):
            self.connected = False

        def connect(self, port=None, baudrate=None):
            if port == "VALID_PORT":
                self.connected = True
                return True
            self.connected = False
            return False

        def disconnect(self):
            self.connected = False

        def is_connected(self):
            return self.connected

        def get_telemetry(self):
            return {"rpm": 850, "speed": 0, "coolant_temp": 89, "voltage": 14.1}

    mock_client = ConnectableClient()
    controller = DashboardController(obd_client=mock_client)

    # Połączenie zakończone błędem
    res_fail = controller.connect_obd(port="INVALID_PORT", baudrate=38400)
    assert res_fail["success"] is False
    assert res_fail["connected"] is False

    # Pomyślne połączenie
    res_ok = controller.connect_obd(port="VALID_PORT", baudrate=115200)
    assert res_ok["success"] is True
    assert res_ok["connected"] is True
    assert "Połączono pomyślnie" in res_ok["message"]

    # Rozłączenie
    res_disc = controller.disconnect_obd()
    assert res_disc["success"] is True
    assert res_disc["connected"] is False


def test_car_doctor_ui_settings_panel_and_interactions():
    fake_conn = FakeOBDConnection(dtc=[], rpm=800, speed=0, coolant=85, voltage=14.0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    # Weryfikacja kontrolek ustawień
    assert hasattr(ui, "port_input")
    assert hasattr(ui, "btn_prof_mobile_bt")
    assert hasattr(ui, "btn_prof_laptop_linux")
    assert hasattr(ui, "connect_btn")
    assert hasattr(ui, "disconnect_btn")

    # Wybór profilu Laptop USB
    ui.on_select_connection_profile("laptop_usb_linux")
    assert ui.port_input.text == "/dev/ttyUSB0"
    assert "115200 baud" in ui.btn_baud_select.text
    assert "Laptop USB" in ui.connection_status_label.text

    # Zmiana baudrate cyklicznie
    ui.on_cycle_baudrate()
    assert ui.controller.connection_config["baudrate"] in [38400, 115200, 9600, 0]

    # Wybór profilu Mobile BT
    ui.on_select_connection_profile("mobile_bt")
    assert ui.port_input.text == "OBDII"

    # Wywołanie rozłączenia z UI
    ui.on_disconnect_obd()
    assert "Rozłączono adapter" in ui.connection_status_label.text

    # Wywołanie połączenia z UI
    ui.on_connect_obd()
    assert len(ui.connection_status_label.text) > 0


def test_dashboard_controller_voice_features():
    fake_conn = FakeOBDConnection(dtc=["P0300"], rpm=2500, speed=60, coolant=92, voltage=13.8)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    controller.refresh_telemetry()
    controller.scan_dtc_and_diagnose()

    # Szybka komenda tekstowa
    q, ans, audio = controller.handle_quick_voice_command("Jaka jest temperatura płynu chłodzącego?")
    assert "temperatura" in q.lower()
    assert "92°C" in ans
    assert len(audio) > 0
    assert controller.last_voice_query == q
    assert controller.last_voice_response == ans
    assert len(controller.last_voice_audio) > 0
    assert "Odpowiedź" in controller.voice_status_text

    # Nagranie i przetworzenie głosu
    q2, ans2, audio2 = controller.record_and_handle_voice(duration_sec=0.5)
    assert len(q2) > 0
    assert len(ans2) > 0
    assert len(audio2) > 0


def test_car_doctor_ui_voice_card_and_interactions():
    fake_conn = FakeOBDConnection(dtc=[], rpm=850, speed=0, coolant=88, voltage=14.1)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    controller.refresh_telemetry()
    ui = CarDoctorUI(controller=controller)

    # Weryfikacja kontrolek asystenta głosowego
    assert hasattr(ui, "voice_card")
    assert hasattr(ui, "btn_cmd_temp")
    assert hasattr(ui, "btn_cmd_volt")
    assert hasattr(ui, "btn_cmd_dtc")
    assert hasattr(ui, "btn_cmd_safe")
    assert hasattr(ui, "btn_cmd_speed")
    assert hasattr(ui, "btn_cmd_help")
    assert hasattr(ui, "btn_voice_record")
    assert hasattr(ui, "voice_custom_input")
    assert hasattr(ui, "btn_voice_send")
    assert hasattr(ui, "voice_status_label")
    assert hasattr(ui, "voice_response_label")

    # Kliknięcie szybkiej komendy - temperatura
    ui.on_quick_voice_command("Jaka jest temperatura płynu chłodzącego?")
    assert "Komenda" in ui.voice_status_label.text
    assert "88°C" in ui.voice_response_label.text

    # Kliknięcie nagrywania mikrofonu
    ui.on_voice_record_button()
    assert "Rozpoznano" in ui.voice_status_label.text
    assert len(ui.voice_response_label.text) > 0

    # Wpisanie własnego pytania i kliknięcie wyślij
    ui.voice_custom_input.text = "Czy mogę bezpiecznie jechać dalej?"
    ui.on_send_custom_voice_query()
    assert "Zapytanie" in ui.voice_status_label.text
    assert "Możesz kontynuować" in ui.voice_response_label.text

    # Wysłanie pustego pytania (fallback do 'Co z autem?')
    ui.voice_custom_input.text = ""
    ui.on_send_custom_voice_query()
    assert "Co z autem?" in ui.voice_status_label.text

    # Główny przycisk asystenta w panelu akcji
    ui.on_voice_assistant()
    assert "Komenda" in ui.voice_status_label.text
    assert "Odpowiedź asystenta głosowego" in ui.report_summary_label.text


def test_car_doctor_ui_telemetry_logging_controls():
    fake_conn = FakeOBDConnection(dtc=[], rpm=1200, speed=30, coolant=85, voltage=14.0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    assert hasattr(ui, "btn_toggle_logging")
    assert hasattr(ui, "btn_export_csv")

    # Start nagrywania
    ui.on_toggle_logging()
    assert controller.is_logging is True
    assert "🔴 Rejestrowanie WŁ" in ui.btn_toggle_logging.text
    assert "Rozpoczęto rejestrację" in ui.status_label.text

    # Pobranie próbki w trakcie nagrywania
    controller.refresh_telemetry()

    # Eksport CSV
    ui.on_export_csv()
    assert "Wyeksportowano" in ui.status_label.text

    # Zatrzymanie nagrywania
    ui.on_toggle_logging()
    assert controller.is_logging is False
    assert "WYŁ" in ui.btn_toggle_logging.text
    assert "Zatrzymano rejestrację" in ui.status_label.text


# =====================================================================
# NOWE TESTY SELEKTORA MODELI AI I MOWY (z feature/ai-model-selection)
# =====================================================================


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


def test_dashboard_controller_speech_configuration():
    """Testuje konfigurację modeli mowy w DashboardController."""
    controller = DashboardController()

    # Sprawdzenie dostępnych modeli STT i TTS
    assert controller.available_stt_models is not None
    assert len(controller.available_stt_models) >= 2  # Whisper Tiny, Vosk

    assert controller.available_tts_models is not None
    assert len(controller.available_tts_models) >= 2  # Piper Darkman, Gosia

    # Sprawdzenie domyślnych modeli
    assert controller.current_stt_model_spec is not None
    assert controller.current_tts_model_spec is not None
    assert isinstance(controller.current_stt_model_spec, SpeechModelSpec)
    assert isinstance(controller.current_tts_model_spec, SpeechModelSpec)

    # Sprawdzenie stanu mikrofonu
    assert controller.mic_enabled is True


def test_dashboard_controller_speech_model_select():
    """Testuje wybór modeli mowy w DashboardController."""
    controller = DashboardController()

    # Wybór modelu STT
    stt_model = controller.available_stt_models[0]
    controller.on_stt_model_select(stt_model)
    assert controller.current_stt_model_spec == stt_model

    # Wybór modelu TTS
    tts_model = controller.available_tts_models[0]
    controller.on_tts_model_select(tts_model)
    assert controller.current_tts_model_spec == tts_model

    # Przełączanie mikrofonu
    controller.toggle_mic_enabled(False)
    assert controller.mic_enabled is False

    controller.toggle_mic_enabled(True)
    assert controller.mic_enabled is True


def test_car_doctor_ui_has_speech_selector():
    """Testuje obecność panelu selektora modeli mowy w UI."""
    fake_conn = FakeOBDConnection(dtc=[], speed=0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    # Sprawdzenie widżetów selektora mowy
    assert hasattr(ui, "speech_status_label")
    assert hasattr(ui, "speech_grid")
    assert hasattr(ui, "mic_btn")

    # Weryfikacja początkowego statusu
    assert "STT:" in ui.speech_status_label.text
    assert "TTS:" in ui.speech_status_label.text
    assert "Mikrofon:" in ui.speech_status_label.text
    assert "ON" in ui.speech_status_label.text


def test_car_doctor_ui_speech_selection():
    """Testuje wybór modeli mowy w UI."""
    fake_conn = FakeOBDConnection(dtc=[], speed=0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    # Pobranie pierwszego przycisku z karty STT
    if ui.speech_grid.children:
        stt_col = ui.speech_grid.children[0]
        if hasattr(stt_col, "children") and stt_col.children:
            first_card = stt_col.children[0]
            if hasattr(first_card, "children") and first_card.children:
                first_btn = first_card.children[-1]  # Ostatni widżet to przycisk
                if hasattr(first_btn, "user_data"):
                    model, model_type = first_btn.user_data
                    if model and model_type == "STT":
                        # Wybór modelu STT
                        ui._on_speech_card_press(first_btn)

                        # Weryfikacja statusu
                        assert controller.current_stt_model_spec == model
                        assert "STT:" in ui.speech_status_label.text


def test_car_doctor_ui_mic_toggle():
    """Testuje przełączanie mikrofonu w UI."""
    fake_conn = FakeOBDConnection(dtc=[], speed=0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    # Weryfikacja początkowego stanu
    assert controller.mic_enabled is True
    assert "ON" in ui.mic_btn.text and tuple(ui.mic_btn.color) == COLOR_SUCCESS

    # Przełączanie mikrofonu
    ui.on_toggle_mic(ui.mic_btn)
    assert controller.mic_enabled is False
    assert "OFF" in ui.mic_btn.text
    assert tuple(ui.mic_btn.color) == COLOR_DANGER


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
        if hasattr(first_card, "children") and first_card.children:
            first_btn = first_card.children[-1]  # Ostatni widżet to przycisk
            if hasattr(first_btn, "user_data"):
                model = first_btn.user_data
                if model:
                    # Wybór modelu
                    ui._on_model_card_press(first_btn)

                    # Weryfikacja statusu
                    assert controller.current_model_spec == model
                    assert "Model AI:" in ui.model_status_label.text
                    assert tuple(ui.model_status_label.color) == COLOR_SUCCESS
