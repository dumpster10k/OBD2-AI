def test_connection_settings_panel_widgets():
    """Testuje obecność panelu ustawień połączenia w UI."""
    fake_conn = FakeOBDConnection(dtc=[], speed=0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    # Weryfikacja kontrolek ustawień połączenia
    assert hasattr(ui, "connection_status_label")
    assert hasattr(ui, "port_input")
    assert hasattr(ui, "btn_baud_select")
    assert hasattr(ui, "btn_prof_mobile_bt")
    assert hasattr(ui, "btn_prof_laptop_linux")
    assert hasattr(ui, "btn_prof_laptop_win")
    assert hasattr(ui, "btn_prof_laptop_bt")
    assert hasattr(ui, "btn_prof_auto")
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


def test_dashboard_controller_simulation_mode():
    """Testuje tryb symulacji w DashboardController."""
    controller = DashboardController()

    # Domyślnie symulacja wyłączona
    assert controller.simulation_mode is False

    # Włączenie symulacji ze scenariuszem
    controller.enable_simulation("check_engine")
    assert controller.simulation_mode is True
    assert controller.active_scenario == "check_engine"
    assert len(controller.simulated_dtc) > 0

    # Włączona symulacja zwraca symulowane dane
    telemetry = controller.refresh_telemetry()
    assert telemetry["rpm"] == 0  # Scenariusz check_engine ma rpm=0

    # Wyłączenie symulacji
    controller.disable_simulation()
    assert controller.simulation_mode is False


def test_car_doctor_ui_telemetry_widgets():
    """Testuje obecność widżetów telemetrii w UI."""
    fake_conn = FakeOBDConnection(dtc=[], speed=0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    # Weryfikacja kontrolek telemetrii
    assert hasattr(ui, "rpm_label")
    assert hasattr(ui, "speed_label")
    assert hasattr(ui, "coolant_label")
    assert hasattr(ui, "voltage_label")
    assert hasattr(ui, "grid_telemetry")


def test_car_doctor_ui_telemetry_update():
    """Testuje aktualizację UI telemetrii."""
    fake_conn = FakeOBDConnection(dtc=[], speed=60, rpm=2000, coolant=90, voltage=13.5)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    controller.refresh_telemetry()
    ui = CarDoctorUI(controller=controller)

    # Weryfikacja wartości w UI
    assert "2000 RPM" in ui.rpm_label.text
    assert "60 km/h" in ui.speed_label.text
    assert "90 °C" in ui.coolant_label.text
    assert "13.5 V" in ui.voltage_label.text


def test_car_doctor_ui_telemetry_color_indication():
    """Testuje kolory wskaźników telemetrii (bezpieczeństwo/warunkowe/niebezpieczeństwo)."""
    # Krytyczna temperatura (powyżej 115°C)
    fake_conn = FakeOBDConnection(dtc=[], speed=0, coolant=120, voltage=13.0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    controller.refresh_telemetry()
    ui = CarDoctorUI(controller=controller)

    # Temperatura powinna być czerwona (COLOR_DANGER)
    assert ui.coolant_label.color[3] == 1.0  # Alpha channel

    # Niskie napięcie (poniżej 11.8V)
    fake_conn2 = FakeOBDConnection(dtc=[], speed=0, coolant=90, voltage=11.0)
    client2 = OBDClient(connection=fake_conn2)
    controller2 = DashboardController(obd_client=client2)
    controller2.refresh_telemetry()
    ui2 = CarDoctorUI(controller=controller2)

    # Napięcie powinno być żółte (COLOR_WARNING)
    assert ui2.voltage_label.color[1] > ui2.voltage_label.color[0]  # Yellow has higher green component


def test_car_doctor_ui_telemetry_logging_controls():
    fake_conn = FakeOBDConnection(dtc=[], rpm=1200, speed=30, coolant=85, voltage=14.0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    # Weryfikacja kontrolek logowania telemetrii
    assert hasattr(ui, "btn_toggle_logging")
    assert hasattr(ui, "log_file_label")

    # Przełączenie logowania
    ui.on_toggle_logging(ui.btn_toggle_logging)
    assert controller.telemetry_logger.is_active()


def test_car_doctor_ui_mic_toggle():
    """Testuje przełączanie mikrofonu w UI."""
    fake_conn = FakeOBDConnection(dtc=[], speed=0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    # Domyślnie mikrofon WŁĄCZONY
    assert controller.mic_enabled is True
    assert "ON" in ui.mic_btn.text
    assert ui.mic_btn.color == 0x00FF00  # Zielony

    # Przełączanie na OFF
    ui.on_toggle_mic(ui.mic_btn)
    assert controller.mic_enabled is False
    assert "OFF" in ui.mic_btn.text
    assert ui.mic_btn.color == 0xFF0000  # Czerwony

    # Przełączanie z powrotem na ON
    ui.on_toggle_mic(ui.mic_btn)
    assert controller.mic_enabled is True
    assert "ON" in ui.mic_btn.text
    assert ui.mic_btn.color == 0x00FF00


def test_car_doctor_ui_speech_selection():
    """Testuje wybór modeli mowy w UI."""
    fake_conn = FakeOBDConnection(dtc=[], speed=0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    # Kliknięcie karty STT
    stt_card = ui.speech_grid.get_children()[0].get_children()[0].get_children()[-1]  # Ostatni widget to przycisk
    stt_card.bind(on_press=ui._on_speech_card_press)
    ui._on_speech_card_press(stt_card)

    # Status powinien być zaktualizowany
    assert "STT:" in ui.speech_status_label.text
    assert controller.current_stt_model_spec is not None

    # Kliknięcie karty TTS
    tts_card = ui.speech_grid.get_children()[1].get_children()[0].get_children()[-1]
    ui._on_speech_card_press(tts_card)
    assert "TTS:" in ui.speech_status_label.text
    assert controller.current_tts_model_spec is not None


def test_car_doctor_ui_model_selection():
    """Testuje wybór modelu AI w UI."""
    fake_conn = FakeOBDConnection(dtc=[], speed=0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client)
    ui = CarDoctorUI(controller=controller)

    # Kliknięcie karty modelu
    model_card = ui.models_grid.get_children()[0].get_children()[-1]  # Przycisk wyboru
    model_card.bind(on_press=ui._on_model_card_press)
    ui._on_model_card_press(model_card)

    # Status powinien być zaktualizowany
    assert "Model AI:" in ui.model_status_label.text
    assert controller.current_model_spec is not None
    assert controller.model_backend_status == "Dostępny (Mock)"
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
