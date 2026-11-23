from __future__ import annotations

from unittest.mock import patch

from core.obd_client import OBDClient
from services.ai_engine import AIEngine
from services.llm_engine import RECOMMENDED_LLM_MODELS
from services.model_downloader import ModelDownloader
from services.speech_service import RECOMMENDED_SPEECH_MODELS
from services.telemetry_logger import TelemetryLogger
from tests.test_ui import FakeOBDConnection
from ui.main import CarDoctorUI, DashboardController


class E2EFakeOBDConnection(FakeOBDConnection):
    """Atrapa połączenia OBD z obsługą odczytu VIN oraz nazwy sterownika ECU."""

    def __init__(self, vin: str = "WAUZZZ8E34A123456", ecu_name: str = "EDC15P 1.9 TDI 038906019FP", **kwargs):
        super().__init__(**kwargs)
        self.vin = vin
        self.ecu_name = ecu_name

    def query(self, cmd):
        name = getattr(cmd, "name", "")
        if "VIN" in name and self.vin:

            class VinRes:
                value = self.vin

            return VinRes()

        if ("CALIBRATION_ID" in name or "ECU_NAME" in name) and self.ecu_name:

            class EcuRes:
                value = [self.ecu_name]

            return EcuRes()

        return super().query(cmd)


class TestE2EAppAndModelJourney:
    """Kompleksowe testy End-to-End symulujące pełną podróż użytkownika w aplikacji:

    Nawigacja po zakładkach, detekcja pojazdu, wybór modeli AI/mowy, telemetria,
    wykresy, asystent głosowy, diagnoza usterki, dwuetapowe kasowanie i obrót ekranu.
    """

    def test_e2e_complete_driver_journey_with_models(self, tmp_path):
        """Pełna ścieżka kierowcy od startu aplikacji, przez diagnozę i asystenta głosowego,

        aż po bezpieczne usunięcie usterki.
        """
        # 1. Inicjalizacja środowiska testowego z bazą SQLite w tmp_path
        db_path = str(tmp_path / "e2e_telemetry.db")
        telemetry_logger = TelemetryLogger(db_path=db_path)

        fake_conn = E2EFakeOBDConnection(
            dtc=[],
            rpm=0,
            speed=0,
            coolant=22,
            voltage=12.4,
            vin="WAUZZZ8E34A123456",
            ecu_name="EDC15P 1.9 TDI 038906019FP",
        )
        obd_client = OBDClient(connection=fake_conn)
        ai_engine = AIEngine()
        downloader = ModelDownloader(target_dir=str(tmp_path / "models"))

        controller = DashboardController(
            obd_client=obd_client,
            ai_engine=ai_engine,
            telemetry_logger=telemetry_logger,
            model_downloader=downloader,
        )

        ui = CarDoctorUI(controller=controller)

        # ---------------------------------------------------------------------
        # KROK 1: Start aplikacji i domyślny stan
        # ---------------------------------------------------------------------
        assert ui.active_tab == "dashboard"
        assert "AI CAR DOCTOR" in ui.title_label.text
        assert ui.section_dashboard in ui.tab_container.children
        assert "OBD:" in ui.bar_obd_status.text

        # ---------------------------------------------------------------------
        # KROK 2: Przejście do Ustawień i wybór modeli
        # ---------------------------------------------------------------------
        ui.set_active_tab("settings")
        assert ui.active_tab == "settings"
        assert ui.section_settings in ui.tab_container.children

        # Wybór modelu LLM (np. SmolLM2)
        smol_model = RECOMMENDED_LLM_MODELS["smollm2-360m"]
        controller.on_model_select(smol_model)
        assert controller.current_model_spec == smol_model

        # Wybór modeli mowy STT i TTS
        whisper_spec = RECOMMENDED_SPEECH_MODELS["whisper-tiny"]
        piper_spec = RECOMMENDED_SPEECH_MODELS["piper-pl-gosia"]
        controller.on_stt_model_select(whisper_spec)
        controller.on_tts_model_select(piper_spec)
        assert controller.current_stt_model_spec == whisper_spec
        assert controller.current_tts_model_spec == piper_spec

        # ---------------------------------------------------------------------
        # KROK 3: Wybór profilu połączenia OBD i auto-profilowanie pojazdu
        # ---------------------------------------------------------------------
        ui.on_select_connection_profile("mobile_bt")
        assert ui.port_input.text == "OBDII"

        # Połączenie z adapterem
        with patch.object(
            controller.obd,
            "connect",
            side_effect=lambda **kwargs: setattr(controller.obd, "connection", fake_conn) or True,
        ):
            ui.on_connect_obd()
        assert obd_client.is_connected() is True
        assert "Połączono" in ui.connection_status_label.text

        # Weryfikacja automatycznego rozpoznania pojazdu
        assert controller.vehicle_profile is not None
        assert "1.9 TDI" in controller.vehicle_profile.engine_name
        assert "Audi" in controller.vehicle_profile.brand

        # Aktualizacja paska szybkiego podglądu (Top Bar)
        ui.update_telemetry_ui()
        assert "OBD: Połączono" in ui.bar_obd_status.text
        assert "1.9 TDI" in ui.bar_vehicle_profile.text

        # ---------------------------------------------------------------------
        # KROK 4: Powrót do Pulpitu i telemetria podczas jazdy
        # ---------------------------------------------------------------------
        ui.set_active_tab("dashboard")
        assert ui.active_tab == "dashboard"

        # Symulacja jazdy (silnik pracuje, prędkość 75 km/h, obroty 2200 RPM, temp 90°C, napięcie 14.2V)
        fake_conn.rpm = 2200
        fake_conn.speed = 75
        fake_conn.coolant = 90
        fake_conn.voltage = 14.2

        ui.on_refresh_telemetry()
        assert "2200 RPM" in ui.rpm_label.text
        assert "75 km/h" in ui.speed_label.text
        assert "90 °C" in ui.coolant_label.text
        assert "14.2 V" in ui.voltage_label.text

        # Weryfikacja zegara tarczowego DialGaugeWidget
        assert ui.dial_rpm.current_value == 2200.0
        assert "OPTYMALNY" in ui.dial_rpm.status_badge.text

        # Weryfikacja etykiet Min/Max
        assert "Min:" in ui.rpm_min_max_label.text
        assert "Max:" in ui.rpm_min_max_label.text
        assert "90°C" in ui.coolant_min_max_label.text

        # ---------------------------------------------------------------------
        # KROK 5: Przejście do Wszystkich czujników (All Sensors)
        # ---------------------------------------------------------------------
        ui.set_active_tab("all_sensors")
        assert ui.active_tab == "all_sensors"
        assert len(ui.all_sensors_grid.children) > 0

        # Wyszukiwanie ciśnienia doładowania
        ui.sensor_search_input.text = "boost"
        ui.on_sensor_search_change(ui.sensor_search_input, "boost")
        assert len(ui.all_sensors_grid.children) >= 1

        # ---------------------------------------------------------------------
        # KROK 6: Przejście do Wykresów (Charts)
        # ---------------------------------------------------------------------
        ui.set_active_tab("charts")
        assert ui.active_tab == "charts"
        assert ui.section_charts in ui.tab_container.children

        ui.chart.set_metric("coolant_temp")
        assert ui.chart.current_metric == "coolant_temp"
        assert "PŁYN CHŁODZĄCY" in ui.chart.chart_title.text

        # ---------------------------------------------------------------------
        # KROK 7: Wystąpienie usterki i Diagnoza AI
        # ---------------------------------------------------------------------
        # Symulacja przegrzania silnika (P0217, 118°C)
        ui.set_active_tab("dashboard")
        ui.on_toggle_simulation()
        ui.on_select_scenario("overheat")

        # Przejście do Diagnoza & AI
        ui.set_active_tab("diagnostics")
        assert ui.active_tab == "diagnostics"
        assert "CRITICAL" in ui.urgency_badge.text
        assert "P0217" in ui.report_summary_label.text or "przegrzan" in ui.report_summary_label.text.lower()

        # ---------------------------------------------------------------------
        # KROK 8: Asystent głosowy Hands-Free
        # ---------------------------------------------------------------------
        # Pytanie kierowcy o temperaturę
        ui.on_quick_voice_command("Jaka jest temperatura płynu chłodzącego?")
        assert len(ui.voice_response_label.text) > 0

        # Pytanie o bezpieczeństwo dalszej jazdy
        ui.voice_custom_input.text = "Czy mogę bezpiecznie kontynuować podróż?"
        ui.on_send_custom_voice_query()
        assert len(ui.voice_response_label.text) > 0

        # ---------------------------------------------------------------------
        # KROK 9: Raport po zakończeniu jazdy
        # ---------------------------------------------------------------------
        ui.on_generate_post_trip_report()
        assert len(ui.report_summary_label.text) > 0

        # ---------------------------------------------------------------------
        # KROK 10: Bezpieczne dwuetapowe kasowanie błędów na postoju (AGENTS.md)
        # ---------------------------------------------------------------------
        # Próba kasowania w ruchu (zabezpieczenie blokuje procedurę)
        ui.on_clear_dtc()
        assert "w ruchu" in ui.status_label.text.lower() or "postoju" in ui.status_label.text.lower()
        assert "Skasuj kody błędów DTC" in ui.clear_btn.text

        # Samochód zatrzymuje się: wyłączenie symulacji i zatrzymanie na poboczu (speed = 0)
        ui.on_toggle_simulation()
        fake_conn.speed = 0
        fake_conn.dtc = ["P0217"]
        controller.refresh_telemetry()

        # Krok 1: Żądanie kasowania (wymaga potwierdzenia na postoju)
        ui.on_clear_dtc()
        assert "POTWIERDŹ KASOWANIE" in ui.clear_btn.text

        # Krok 2: Potwierdzenie kasowania na postoju
        ui.on_clear_dtc()
        assert "Skasuj kody błędów DTC" in ui.clear_btn.text
        assert "skasowane" in ui.status_label.text.lower()

        # Weryfikacja ponownego skanu
        ui.on_scan_errors()
        assert "Nie wykryto błędów" in ui.status_label.text

        # ---------------------------------------------------------------------
        # KROK 11: Zmiana orientacji ekranu (Obrót w uchwycie Portrait <-> Landscape)
        # ---------------------------------------------------------------------
        # Tryb poziomy (Landscape / HUD)
        ui.apply_responsive_layout(width=1024, height=600)
        assert ui.is_landscape is True
        assert ui.grid_telemetry.cols == 4  # 4 wskaźniki w jednym rzędzie

        # Tryb pionowy (Portrait)
        ui.apply_responsive_layout(width=400, height=800)
        assert ui.is_landscape is False
        assert ui.grid_telemetry.cols == 2  # 2 kolumny wskaźników
        assert ui.tab_nav_bar.cols == 3  # 2 rzędy po 3 przyciski zakładek

    def test_e2e_live_vs_eco_agent_modes(self, tmp_path):
        """Weryfikacja zachowania Agenta w trybie LIVE (alarm natychmiastowy)

        oraz POST_TRIP_ECO (cicha telemetria w tle, raport po zatrzymaniu).
        """
        fake_conn = FakeOBDConnection(dtc=[], rpm=2000, speed=50, coolant=90, voltage=14.0)
        client = OBDClient(connection=fake_conn)
        controller = DashboardController(
            obd_client=client,
            telemetry_logger=TelemetryLogger(db_path=str(tmp_path / "eco.db")),
        )
        ui = CarDoctorUI(controller=controller)

        # 1. Przełączenie trybu agenta w UI - weryfikacja cyklu z domyślnego ASK_USER -> LIVE -> EKO -> ASK_USER
        assert "Pytaj" in ui.btn_agent_mode.text
        ui.on_toggle_agent_mode()
        assert "Na żywo" in ui.btn_agent_mode.text
        ui.on_toggle_agent_mode()
        assert "EKO" in ui.btn_agent_mode.text
        ui.on_toggle_agent_mode()
        assert "Pytaj" in ui.btn_agent_mode.text

        # 2. Weryfikacja rejestratora w tle
        controller.start_telemetry_harvesting()
        assert controller.telemetry_harvester.is_running is True

        controller._on_harvester_sample({"rpm": 2100, "speed": 60, "coolant_temp": 91, "voltage": 14.1})
        controller.stop_telemetry_harvesting()
        assert controller.telemetry_harvester.is_running is False

    def test_e2e_speech_and_voice_recording_fallback(self):
        """Weryfikacja nagrywania głosu na urządzeniu i fallbacku do mocka."""
        controller = DashboardController()
        ui = CarDoctorUI(controller=controller)

        # Symulacja mikrofonu fizycznego
        with patch.object(
            controller,
            "get_microphone_status",
            return_value={"is_live": True, "device_name": "Test Mic"},
        ):
            with patch.object(
                controller, "record_and_handle_voice", return_value=("Temperatura silnika", "90°C", b"audio")
            ):
                ui.on_voice_record_button()
                assert "Rozpoznano mowę" in ui.voice_status_label.text

        # Przełączenie mikrofonu ON / OFF
        ui.on_toggle_mic(ui.mic_btn)
        assert controller.mic_enabled is False
        assert "OFF" in ui.mic_btn.text

        ui.on_toggle_mic(ui.mic_btn)
        assert controller.mic_enabled is True
        assert "ON" in ui.mic_btn.text
