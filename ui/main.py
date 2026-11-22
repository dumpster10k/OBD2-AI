from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import Any, Optional

# Zapewnienie dostępności modułów nadrzędnych (core, services)
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

class WidgetStub:
    """Uniwersalna atrapa widżetów Kivy dla środowisk CI / headless / fallback."""

    def __init__(self, *args, **kwargs):
        self.children: list[Any] = []
        self.text: str = kwargs.get("text", "")
        self.color: list[float] = kwargs.get("color", [1.0, 1.0, 1.0, 1.0])
        self.size_hint_y = kwargs.get("size_hint_y", 1)
        self.size_hint_x = kwargs.get("size_hint_x", 1)
        self.height = kwargs.get("height", 100)
        self.width = kwargs.get("width", 100)
        self.pos = (0, 0)
        self.size = (100, 100)
        for k, v in kwargs.items():
            setattr(self, k, v)

    def add_widget(self, widget: Any, *args, **kwargs) -> None:
        self.children.append(widget)

    def bind(self, **kwargs) -> None:
        pass

    def fbind(self, *args, **kwargs) -> None:
        pass

    def unbind(self, *args, **kwargs) -> None:
        pass

    def funbind(self, *args, **kwargs) -> None:
        pass

    def setter(self, name: str) -> Any:
        def _setter(val: Any) -> None:
            setattr(self, name, val)
        return _setter


try:
    from kivy.app import App
    from kivy.core.window import Window
    from kivy.graphics import Color, Line, Rectangle, RoundedRectangle
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.label import Label
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.textinput import TextInput
    from kivy.uix.widget import Widget

    KIVY_AVAILABLE = True
except ImportError:
    KIVY_AVAILABLE = False

    class App:
        def build(self) -> Any:
            return None

        def run(self) -> None:
            pass

    class Widget(WidgetStub):
        pass

    class BoxLayout(WidgetStub):
        pass

    class GridLayout(WidgetStub):
        pass

    class Button(WidgetStub):
        pass

    class Label(WidgetStub):
        pass

    class ScrollView(WidgetStub):
        pass

    class TextInput(WidgetStub):
        pass


from core.obd_client import ConnectionConfig, OBDClient
from services.ai_engine import AIEngine
from services.diagnostic_ai import DiagnosisReport
from services.llm_engine import (
    DISCLAIMER_TEXT,
    LLMModelSpec,
    RECOMMENDED_LLM_MODELS,
)
from services.speech_service import (
    SpeechModelSpec,
    RECOMMENDED_SPEECH_MODELS,
    SpeechService,
)
from services.telemetry_logger import TelemetryLogger

logger = logging.getLogger(__name__)

# Paleta kolorów — motyw Dark Cyber Automotive
COLOR_BG = (0.06, 0.09, 0.16, 1.0)          # Głęboki grafit tła #0F172A
COLOR_CARD = (0.12, 0.16, 0.24, 1.0)        # Karty powierzchniowe #1E293B
COLOR_CARD_BORDER = (0.20, 0.25, 0.35, 1.0) # Ramki kart #334155
COLOR_PRIMARY = (0.01, 0.52, 0.78, 1.0)     # Akcent główny (Cyan/Blue #0284C7)
COLOR_SUCCESS = (0.06, 0.72, 0.51, 1.0)     # Sukces / Bezpieczny (Emerald #10B981)
COLOR_WARNING = (0.96, 0.62, 0.14, 1.0)     # Ostrzeżenie (Amber #F59E0B)
COLOR_DANGER = (0.88, 0.11, 0.28, 1.0)      # Krytyczny / Kasowanie (Rose #E11D48)
COLOR_VOICE = (0.49, 0.23, 0.93, 1.0)       # Asystent mowy (Violet #7C3AED)
COLOR_TEXT_MUTED = (0.58, 0.64, 0.72, 1.0)  # Tekst pomocniczy #94A3B8

# Profile połączeń z adapterem OBD (Mobile Bluetooth vs Laptop USB / Bluetooth)
CONNECTION_PROFILES: dict[str, dict[str, Any]] = {
    "mobile_bt": {
        "name": "📱 Mobile Bluetooth (Android / iOS)",
        "type": "bluetooth",
        "port": "OBDII",
        "baudrate": 38400,
        "description": "Bezprzewodowy profil Bluetooth SPP dla smartfonów i tabletów.",
    },
    "laptop_usb_linux": {
        "name": "💻 Laptop USB (Linux / macOS)",
        "type": "usb",
        "port": "/dev/ttyUSB0",
        "baudrate": 115200,
        "description": "Przewodowy port szeregowy USB FTDI/CH340 dla systemów Linux.",
    },
    "laptop_usb_win": {
        "name": "💻 Laptop USB (Windows COM)",
        "type": "usb",
        "port": "COM3",
        "baudrate": 38400,
        "description": "Wirtualny port COM adaptera USB ELM327 pod Windows.",
    },
    "laptop_bt": {
        "name": "💻 Laptop Bluetooth (RFCOMM)",
        "type": "bluetooth",
        "port": "/dev/rfcomm0",
        "baudrate": 38400,
        "description": "Powiązany port Bluetooth RFCOMM na komputerze przenośnym.",
    },
    "auto": {
        "name": "🔍 Automatyczne wykrywanie",
        "type": "auto",
        "port": "",
        "baudrate": 0,
        "description": "Automatyczne skanowanie wszystkich portów USB i Bluetooth.",
    },
}

# Predefiniowane realistyczne scenariusze symulacji awarii
SIMULATION_SCENARIOS: dict[str, dict[str, Any]] = {
    "clean": {
        "name": "Normalna praca (Brak usterek)",
        "dtc": [],
        "telemetry": {"rpm": 850, "speed": 0, "coolant_temp": 89, "voltage": 14.2},
    },
    "misfire": {
        "name": "Wypadanie zapłonów (P0300, P0301)",
        "dtc": [
            ("P0300", "Losowe wypadanie zapłonów"),
            ("P0301", "Wypadanie zapłonu cylinder 1"),
        ],
        "telemetry": {"rpm": 2800, "speed": 65, "coolant_temp": 93, "voltage": 13.9},
    },
    "overheat": {
        "name": "Przegrzanie silnika (Krytyczne P0217)",
        "dtc": [("P0217", "Stan przegrzania płynu chłodzącego silnika")],
        "telemetry": {"rpm": 2200, "speed": 40, "coolant_temp": 119, "voltage": 13.4},
    },
    "lean_mix": {
        "name": "Uboga mieszanka / MAF (P0171, P0101)",
        "dtc": [
            ("P0171", "System Too Lean Bank 1"),
            ("P0101", "Mass Air Flow Sensor Range/Performance"),
        ],
        "telemetry": {"rpm": 1950, "speed": 55, "coolant_temp": 88, "voltage": 14.0},
    },
    "low_voltage": {
        "name": "Niskie napięcie akumulatora (P0562)",
        "dtc": [("P0562", "System Voltage Low")],
        "telemetry": {"rpm": 0, "speed": 0, "coolant_temp": 65, "voltage": 11.1},
    },
}


class StyledCard(BoxLayout):
    """Elegancka karta z zaokrąglonymi rogami i obramowaniem."""

    def __init__(
        self,
        bg_color: tuple[float, float, float, float] = COLOR_CARD,
        border_color: tuple[float, float, float, float] = COLOR_CARD_BORDER,
        radius: float = 12.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.bg_color = bg_color
        self.border_color = border_color
        self.radius = radius

        if KIVY_AVAILABLE:
            with self.canvas.before:
                self._bg_col = Color(*self.bg_color)
                self._bg_rect = RoundedRectangle(
                    pos=self.pos, size=self.size, radius=[self.radius]
                )
                if self.border_color:
                    self._line_col = Color(*self.border_color)
                    self._line_rect = Line(
                        rounded_rectangle=(
                            self.x,
                            self.y,
                            self.width,
                            self.height,
                            self.radius,
                        ),
                        width=1.1,
                    )
            self.bind(pos=self._update_geometry, size=self._update_geometry)

    def _update_geometry(self, *args) -> None:
        if hasattr(self, "_bg_rect"):
            self._bg_rect.pos = self.pos
            self._bg_rect.size = self.size
        if hasattr(self, "_line_rect"):
            self._line_rect.rounded_rectangle = (
                self.x,
                self.y,
                self.width,
                self.height,
                self.radius,
            )

    def set_border_color(self, color: tuple[float, float, float, float]) -> None:
        if KIVY_AVAILABLE and hasattr(self, "_line_col"):
            self._line_col.rgba = color


class TelemetryChart(StyledCard):
    """Wykres trendu wybranego parametru telemetrycznego z historią próbkowania."""

    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            height=230,
            padding=[14, 12, 14, 12],
            spacing=8,
            **kwargs,
        )
        self.current_metric = "rpm"
        self.history: list[float] = [0.0]

        # 1. Pasek nagłówka z przełącznikiem metryk
        header_box = BoxLayout(size_hint_y=None, height=28, spacing=6)
        self.chart_title = Label(
            text="📈 WYKRES TELEMETRII (OBROTY - RPM)",
            font_size="13sp",
            bold=True,
            color=COLOR_TEXT_MUTED,
            size_hint_x=0.45,
            halign="left",
            valign="middle",
        )
        header_box.add_widget(self.chart_title)

        self.btn_rpm = Button(
            text="RPM",
            font_size="11sp",
            bold=True,
            size_hint_x=0.13,
            background_normal="",
            background_color=COLOR_PRIMARY,
        )
        self.btn_rpm.bind(on_press=lambda _b: self.set_metric("rpm"))
        header_box.add_widget(self.btn_rpm)

        self.btn_speed = Button(
            text="KM/H",
            font_size="11sp",
            bold=True,
            size_hint_x=0.14,
            background_normal="",
            background_color=(0.18, 0.22, 0.30, 1.0),
        )
        self.btn_speed.bind(on_press=lambda _b: self.set_metric("speed"))
        header_box.add_widget(self.btn_speed)

        self.btn_temp = Button(
            text="TEMP",
            font_size="11sp",
            bold=True,
            size_hint_x=0.14,
            background_normal="",
            background_color=(0.18, 0.22, 0.30, 1.0),
        )
        self.btn_temp.bind(on_press=lambda _b: self.set_metric("coolant_temp"))
        header_box.add_widget(self.btn_temp)

        self.btn_volt = Button(
            text="VOLT",
            font_size="11sp",
            bold=True,
            size_hint_x=0.14,
            background_normal="",
            background_color=(0.18, 0.22, 0.30, 1.0),
        )
        self.btn_volt.bind(on_press=lambda _b: self.set_metric("voltage"))
        header_box.add_widget(self.btn_volt)

        self.add_widget(header_box)

        # 2. Pasek informacyjny
        self.stats_label = Label(
            text="Bieżące: 0 RPM | Min: 0 RPM | Max: 0 RPM (próbek: 1)",
            font_size="11sp",
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=18,
            halign="left",
            valign="middle",
        )
        self.add_widget(self.stats_label)

        # 3. Obszar rysowania wykresu
        if KIVY_AVAILABLE:
            self.plot_area = Widget(size_hint=(1, 1))
            with self.plot_area.canvas:
                self._plot_bg_c = Color(0.07, 0.10, 0.17, 1.0)
                self._plot_bg = Rectangle(pos=self.plot_area.pos, size=self.plot_area.size)
                self._grid_c = Color(0.18, 0.22, 0.30, 0.8)
                self._grid_line_mid = Line(points=[], width=1.0)
                self._line_c = Color(0.06, 0.73, 0.85, 1.0)
                self._trend_line = Line(points=[], width=2.2)
            self.plot_area.bind(pos=self._redraw, size=self._redraw)
            self.add_widget(self.plot_area)
        else:
            self.plot_area = Widget(size_hint=(1, 1))
            self.add_widget(self.plot_area)

    def set_metric(self, metric: str) -> None:
        self.current_metric = metric
        titles = {
            "rpm": "📈 WYKRES TELEMETRII (OBROTY - RPM)",
            "speed": "📈 WYKRES TELEMETRII (PRĘDKOŚĆ - KM/H)",
            "coolant_temp": "📈 WYKRES TELEMETRII (PŁYN CHŁODZĄCY - °C)",
            "voltage": "📈 WYKRES TELEMETRII (NAPIĘCIE - V)",
        }
        self.chart_title.text = titles.get(metric, "📈 WYKRES TELEMETRII")
        btns = {
            "rpm": self.btn_rpm,
            "speed": self.btn_speed,
            "coolant_temp": self.btn_temp,
            "voltage": self.btn_volt,
        }
        for k, btn in btns.items():
            btn.background_color = COLOR_PRIMARY if k == metric else (0.18, 0.22, 0.30, 1.0)

    def update_history(self, history_data: list[float]) -> None:
        self.history = list(history_data) if history_data else [0.0]
        curr = self.history[-1] if self.history else 0.0
        min_v = min(self.history) if self.history else 0.0
        max_v = max(self.history) if self.history else 0.0

        if self.current_metric == "voltage":
            self.stats_label.text = f"Bieżące: {curr:.2f} V | Min: {min_v:.2f} V | Max: {max_v:.2f} V (próbek: {len(self.history)})"
        elif self.current_metric == "coolant_temp":
            self.stats_label.text = f"Bieżące: {int(curr)} °C | Min: {int(min_v)} °C | Max: {int(max_v)} °C (próbek: {len(self.history)})"
        elif self.current_metric == "speed":
            self.stats_label.text = f"Bieżące: {int(curr)} km/h | Min: {int(min_v)} km/h | Max: {int(max_v)} km/h (próbek: {len(self.history)})"
        else:
            self.stats_label.text = f"Bieżące: {int(curr)} RPM | Min: {int(min_v)} RPM | Max: {int(max_v)} RPM (próbek: {len(self.history)})"

        self._redraw()

    def _redraw(self, *args) -> None:
        if not KIVY_AVAILABLE or not hasattr(self, "_trend_line"):
            return

        w = self.plot_area.width
        h = self.plot_area.height
        x = self.plot_area.x
        y = self.plot_area.y

        self._plot_bg.pos = (x, y)
        self._plot_bg.size = (w, h)

        mid_y = y + h / 2.0
        self._grid_line_mid.points = [x, mid_y, x + w, mid_y]

        pts = self.history
        if len(pts) < 2:
            self._trend_line.points = []
            return

        min_val = min(pts)
        max_val = max(pts)
        val_range = max_val - min_val
        if val_range <= 1e-4:
            val_range = 1.0

        calc_points: list[float] = []
        n = len(pts)
        padding_y = 6.0
        draw_h = max(1.0, h - 2 * padding_y)

        for i, val in enumerate(pts):
            px = x + (i / (n - 1)) * w
            py = y + padding_y + ((val - min_val) / val_range) * draw_h
            calc_points.extend([px, py])

        if self.current_metric == "coolant_temp":
            self._line_c.rgba = COLOR_DANGER if pts[-1] >= 115 else (COLOR_WARNING if pts[-1] >= 105 else COLOR_SUCCESS)
        elif self.current_metric == "voltage":
            self._line_c.rgba = COLOR_WARNING if pts[-1] < 11.8 else COLOR_SUCCESS
        else:
            self._line_c.rgba = (0.06, 0.73, 0.85, 1.0)

        self._trend_line.points = calc_points


class DashboardController:
    """Kontroler pulpitu diagnostycznego oddzielający logikę biznesową, symulację, konfigurację i telemetrię od Kivy."""

    def __init__(
        self,
        obd_client: Optional[OBDClient] = None,
        ai_engine: Optional[AIEngine] = None,
        telemetry_logger: Optional[TelemetryLogger] = None,
    ):
        self.obd = obd_client or OBDClient()
        self.ai = ai_engine or AIEngine()
        self.telemetry_logger = telemetry_logger or TelemetryLogger()
        self.is_logging: bool = False
        self.current_session_id: Optional[str] = None
        self.telemetry: dict[str, Any] = {
            "rpm": 0,
            "speed": 0,
            "coolant_temp": 0,
            "voltage": 0.0,
        }
        self.current_dtcs: list[Any] = []
        self.latest_report: Optional[DiagnosisReport] = None
        self.last_voice_query: str = ""
        self.last_voice_response: str = ""
        self.last_voice_audio: bytes = b""
        self.voice_status_text: str = "Gotowy (naciśnij przycisk lub wybierz komendę)"
        self.dtc_clear_pending: bool = False
        self.session_log: list[dict[str, Any]] = []

        # Konfiguracja modelu AI
        self.available_models: list[LLMModelSpec] = list(RECOMMENDED_LLM_MODELS.values())
        self.current_model_spec: Optional[LLMModelSpec] = self.available_models[0] if self.available_models else None
        self.model_backend_status: str = "Dostępny (Mock)"

        # Konfiguracja mowy (STT/TTS)
        self.available_stt_models: list[SpeechModelSpec] = []
        self.available_tts_models: list[SpeechModelSpec] = []
        self.current_stt_model_spec: Optional[SpeechModelSpec] = None
        self.current_tts_model_spec: Optional[SpeechModelSpec] = None
        self.mic_enabled: bool = True

        # Moduł konfiguracji połączeń (Mobile BT / Laptop USB & BT)
        self.connection_config: dict[str, Any] = {
            "profile_key": "mobile_bt",
            "type": "bluetooth",
            "port": "OBDII",
            "baudrate": 38400,
        }

        # Moduł symulatora i historii trendów
        self.simulation_mode: bool = False
        self.active_scenario: str = "clean"
        self.simulated_dtc: list[Any] = []
        self.simulated_telemetry: dict[str, Any] = {
            "rpm": 0,
            "speed": 0,
            "coolant_temp": 0,
            "voltage": 0.0,
        }
        self.telemetry_history: dict[str, list[float]] = {
            "rpm": [0.0],
            "speed": [0.0],
            "coolant_temp": [0.0],
            "voltage": [0.0],
        }

    def apply_connection_profile(self, profile_key: str) -> dict[str, Any]:
        """Aplikuje predefiniowany profil połączenia (Mobile Bluetooth / Laptop USB / Laptop Bluetooth / Auto)."""
        prof = CONNECTION_PROFILES.get(profile_key, CONNECTION_PROFILES["auto"])
        self.connection_config = {
            "profile_key": profile_key,
            "type": prof["type"],
            "port": prof["port"],
            "baudrate": prof["baudrate"],
        }
        return prof

    def update_connection_settings(
        self, port: str, baudrate: int = 38400, connection_type: str = "auto"
    ) -> dict[str, Any]:
        """Aktualizuje indywidualne parametry portu i prędkości transmisji."""
        self.connection_config["port"] = port.strip()
        self.connection_config["baudrate"] = int(baudrate)
        self.connection_config["type"] = connection_type
        return dict(self.connection_config)

    def connect_obd(
        self, port: Optional[str] = None, baudrate: Optional[int] = None
    ) -> dict[str, Any]:
        """Nawiązuje połączenie z adapterem ELM327 według bieżących lub zadanych ustawień."""
        target_port = port if port is not None else self.connection_config.get("port")
        target_baud = baudrate if baudrate is not None else self.connection_config.get("baudrate")

        portstr = target_port.strip() if (target_port and target_port.strip()) else None
        baud = target_baud if (target_baud and target_baud > 0) else None

        success = self.obd.connect(port=portstr, baudrate=baud)
        if success:
            self.refresh_telemetry()
            msg = f"Połączono pomyślnie ({portstr or 'Auto'}, {baud or 'Auto'} baud)"
        else:
            msg = f"Brak połączenia z {portstr or 'Auto'} (sprawdź zasilanie, Bluetooth lub port USB)"

        return {
            "success": success,
            "message": msg,
            "connected": self.obd.is_connected(),
            "port": portstr,
            "baudrate": baud,
        }

    def disconnect_obd(self) -> dict[str, Any]:
        """Rozłącza adapter OBD."""
        self.obd.disconnect()
        return {
            "success": True,
            "message": "Rozłączono adapter OBD",
            "connected": False,
        }

    def record_telemetry_point(self, telemetry_data: dict[str, Any]) -> None:
        """Zapisuje bieżącą próbkę telemetrii w buforze historii (max 50 próbek)."""
        max_points = 50
        for key in ["rpm", "speed", "coolant_temp", "voltage"]:
            val = float(telemetry_data.get(key, 0.0))
            hist = self.telemetry_history.setdefault(key, [])
            hist.append(val)
            if len(hist) > max_points:
                self.telemetry_history[key] = hist[-max_points:]

    def get_telemetry_history(self, metric: str) -> list[float]:
        """Zwraca bufor historii dla podanej metryki."""
        return list(self.telemetry_history.get(metric, [0.0]))

    def enable_simulation(self, scenario_key: str = "clean") -> dict[str, Any]:
        """Włącza tryb symulacji i ładuje wybrany scenariusz usterek."""
        self.simulation_mode = True
        return self.load_simulation_scenario(scenario_key)

    def disable_simulation(self) -> None:
        """Wyłącza tryb symulacji i przełącza się na fizyczny adapter OBD."""
        self.simulation_mode = False
        self.refresh_telemetry()

    def load_simulation_scenario(self, scenario_key: str) -> dict[str, Any]:
        """Ładuje dane scenariusza symulacji."""
        scen = SIMULATION_SCENARIOS.get(scenario_key, SIMULATION_SCENARIOS["clean"])
        self.active_scenario = scenario_key
        self.simulated_dtc = list(scen["dtc"])
        self.simulated_telemetry = dict(scen["telemetry"])
        self.telemetry = dict(self.simulated_telemetry)
        self.record_telemetry_point(self.telemetry)
        return scen

    def refresh_telemetry(self) -> dict[str, Any]:
        """Pobiera i aktualizuje bieżące parametry telemetryczne pojazdu."""
        if self.simulation_mode:
            self.telemetry = dict(self.simulated_telemetry)
        else:
            self.telemetry = self.obd.get_telemetry()

        self.record_telemetry_point(self.telemetry)

        # Automatyczny zapis próbki do bazy SQLite, jeśli trwa nagrywanie sesji
        if self.is_logging and self.current_session_id and self.telemetry_logger:
            self.telemetry_logger.log_sample(self.current_session_id, self.telemetry)

        return self.telemetry

    def scan_dtc_and_diagnose(self) -> tuple[list[Any], Optional[DiagnosisReport]]:
        """Skanuje kody błędów OBD oraz generuje kompleksowy raport diagnostyczny AI."""
        if self.simulation_mode:
            self.current_dtcs = list(self.simulated_dtc)
        else:
            self.current_dtcs = self.obd.get_dtc()

        self.refresh_telemetry()

        dtc_str_list: list[str] = []
        for item in self.current_dtcs:
            if isinstance(item, (tuple, list)) and item:
                dtc_str_list.append(str(item[0]))
            elif item:
                dtc_str_list.append(str(item))

        vehicle_context = {
            "dtc_codes": dtc_str_list,
            "rpm": self.telemetry.get("rpm", 0),
            "speed": self.telemetry.get("speed", 0),
            "coolant_temp": self.telemetry.get("coolant_temp", 0),
            "voltage": self.telemetry.get("voltage", 0.0),
        }

        self.latest_report = self.ai.analyze_context(vehicle_context)
        self.dtc_clear_pending = False
        return self.current_dtcs, self.latest_report

    def request_clear_dtc(self) -> dict[str, Any]:
        """Inicjuje procedurę kasowania błędów DTC pod warunkiem postoju pojazdu (wymóg AGENTS.md)."""
        speed = self.telemetry.get("speed", 0)
        if speed > 0:
            self.dtc_clear_pending = False
            return {
                "success": False,
                "pending": False,
                "message": "Pojazd w ruchu! Kasowanie dozwolone wyłącznie na postoju (prędkość = 0 km/h).",
            }

        self.dtc_clear_pending = True
        return {
            "success": True,
            "pending": True,
            "message": "Wymagane drugie potwierdzenie: kliknij ponownie 'Potwierdź kasowanie na postoju'.",
        }

    def confirm_clear_dtc(self) -> dict[str, Any]:
        """Utrwala kody w logu sesji i wykonuje bezpieczne kasowanie DTC."""
        if not self.dtc_clear_pending:
            return {
                "success": False,
                "message": "Brak aktywnego żądania kasowania. Najpierw zainicjuj procedurę.",
            }

        speed = self.telemetry.get("speed", 0)
        if speed > 0:
            self.dtc_clear_pending = False
            return {
                "success": False,
                "message": "Pojazd ruszył! Kasowanie anulowane ze względów bezpieczeństwa.",
            }

        # Utrwalenie w logu sesji przed skasowaniem (AGENTS.md pkt 7)
        self.session_log.append(
            {
                "action": "clear_dtc",
                "cleared_codes": list(self.current_dtcs),
                "telemetry": dict(self.telemetry),
            }
        )
        if self.telemetry_logger and self.current_session_id:
            self.telemetry_logger.log_audit_event(
                session_id=self.current_session_id,
                event_type="DTC_CLEARED",
                details=f"Kasowanie kodów DTC: {list(self.current_dtcs)} na postoju",
                speed=0.0,
            )

        if self.simulation_mode:
            self.simulated_dtc = []
            cleared = True
        else:
            cleared = self.obd.clear_dtc()

        self.dtc_clear_pending = False
        if cleared:
            self.current_dtcs = []
            self.latest_report = None
            return {
                "success": True,
                "message": "Błędy DTC zostały pomyślnie skasowane i zarchiwizowane w logu sesji.",
            }
        else:
            return {
                "success": False,
                "message": "Kasowanie błędów nie powiodło się (brak połączenia z ECU lub odmowa).",
            }

    def cancel_clear_dtc(self) -> None:
        """Anuluje oczekujące potwierdzenie kasowania."""
        self.dtc_clear_pending = False

    def start_telemetry_logging(self, vehicle_name: str = "Pojazd") -> str:
        """Rozpoczyna rejestrację próbek telemetrii w bazie SQLite."""
        initial_dtcs = [
            str(c[0] if isinstance(c, (list, tuple)) else c)
            for c in self.current_dtcs
        ]
        self.current_session_id = self.telemetry_logger.start_session(
            vehicle_name=vehicle_name,
            initial_dtcs=initial_dtcs,
        )
        self.is_logging = True
        return self.current_session_id

    def stop_telemetry_logging(self) -> None:
        """Zatrzymuje rejestrację telemetrii."""
        if self.current_session_id:
            final_dtcs = [
                str(c[0] if isinstance(c, (list, tuple)) else c)
                for c in self.current_dtcs
            ]
            self.telemetry_logger.end_session(self.current_session_id, final_dtcs=final_dtcs)
        self.is_logging = False
        self.current_session_id = None

    def export_telemetry_csv(self, output_path: Optional[str] = None) -> dict[str, Any]:
        """Eksportuje próbki telemetrii z aktywnej lub ostatniej sesji do pliku CSV."""
        sess_id = self.current_session_id
        if not sess_id:
            sessions = self.telemetry_logger.list_sessions()
            if sessions:
                sess_id = sessions[0]["session_id"]
        if not sess_id:
            return {"success": False, "message": "Brak zarejestrowanych sesji do eksportu."}

        out = output_path or f"data/telemetry_{sess_id}.csv"
        try:
            path = self.telemetry_logger.export_to_csv(sess_id, out)
            return {
                "success": True,
                "message": f"Wyeksportowano pomyślnie do pliku {path.name}",
                "path": str(path),
                "session_id": sess_id,
            }
        except Exception as e:
            return {"success": False, "message": f"Błąd eksportu: {e}"}

    def handle_voice_input(
        self,
        audio_data: Optional[bytes] = None,
        text_query: Optional[str] = None,
    ) -> tuple[str, str, bytes]:
        """Przetwarza zapytanie głosowe kierowcy."""
        vehicle_context = {
            "dtc_codes": [
                str(c[0] if isinstance(c, (list, tuple)) else c)
                for c in self.current_dtcs
            ],
            "rpm": self.telemetry.get("rpm", 0),
            "speed": self.telemetry.get("speed", 0),
            "coolant_temp": self.telemetry.get("coolant_temp", 0),
            "voltage": self.telemetry.get("voltage", 0.0),
        }

        if text_query:
            query, response, out_audio = self.ai.handle_voice_text_command(
                text_query,
                vehicle_context=vehicle_context,
            )
        else:
            query, response, out_audio = self.ai.handle_voice_command(
                audio_data or b"",
                vehicle_context=vehicle_context,
            )

        self.last_voice_query = query
        self.last_voice_response = response
        self.last_voice_audio = out_audio
        self.voice_status_text = f"Odpowiedź wygenerowana dla: \"{query}\""
        return query, response, out_audio

    def record_and_handle_voice(self, duration_sec: float = 3.0) -> tuple[str, str, bytes]:
        """Nagrywa dźwięk z mikrofonu przez serwis mowy i przetwarza polecenie."""
        audio = self.ai.voice.speech.record_audio(duration_sec=duration_sec)
        return self.handle_voice_input(audio_data=audio)

    def handle_quick_voice_command(self, cmd_prompt: str) -> tuple[str, str, bytes]:
        """Obsługuje szybkie predefiniowane polecenie asystenta głosowego."""
        return self.handle_voice_input(text_query=cmd_prompt)

    # ---------------------------------------------------------------------
    # Model AI configuration
    # ---------------------------------------------------------------------
    def load_available_models(self) -> None:
        """Pobiera listę dostępnych modeli LLM."""
        self.available_models = list(RECOMMENDED_LLM_MODELS.values())

    def on_model_select(self, model_spec: LLMModelSpec) -> None:
        """Obsługa wybrania modelu LLM."""
        self.current_model_spec = model_spec
        self.model_backend_status = "Dostępny (Mock)"
        logger.info(f"Wybrano model: {model_spec.name}")

    # ---------------------------------------------------------------------
    # Speech models configuration
    # ---------------------------------------------------------------------
    def load_available_speech_models(self) -> None:
        """Pobiera listę dostępnych modeli mowy."""
        self.available_stt_models = [m for m in RECOMMENDED_SPEECH_MODELS.values() if m.type == "stt"]
        self.available_tts_models = [m for m in RECOMMENDED_SPEECH_MODELS.values() if m.type == "tts"]
        self.current_stt_model_spec = self.available_stt_models[0] if self.available_stt_models else None
        self.current_tts_model_spec = self.available_tts_models[0] if self.available_tts_models else None

    def on_stt_model_select(self, model_spec: SpeechModelSpec) -> None:
        """Obsługa wybrania modelu STT."""
        self.current_stt_model_spec = model_spec
        logger.info(f"Wybrano model STT: {model_spec.name}")

    def on_tts_model_select(self, model_spec: SpeechModelSpec) -> None:
        """Obsługa wybrania modelu TTS."""
        self.current_tts_model_spec = model_spec
        logger.info(f"Wybrano model TTS: {model_spec.name}")

    def toggle_mic_enabled(self, enabled: bool) -> None:
        """Przełącza stan mikrofonu."""
        self.mic_enabled = enabled
        logger.info(f"Mikrofon: {'WŁĄCZONY' if enabled else 'WYŁĄCZONY'}")


class CarDoctorUI(BoxLayout):
    """Nowoczesny pulpit mobilny Kivy z telemetrią na żywo, wykresem trendu, symulatorem i ustawieniami połączeń."""

    def __init__(self, controller: Optional[DashboardController] = None, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.controller = controller or DashboardController()
        self.controller.load_available_speech_models()  # Inicjalizacja modeli mowy

        if KIVY_AVAILABLE:
            try:
                Window.clearcolor = COLOR_BG
            except Exception:
                pass

        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.content_box = BoxLayout(
            orientation="vertical",
            spacing=14,
            padding=[16, 16, 16, 20],
            size_hint_y=None,
        )
        if hasattr(self.content_box, "setter"):
            self.content_box.bind(minimum_height=self.content_box.setter("height"))

        # ---------------------------------------------------------------------
        # 1. Nagłówek i status połączenia
        # ---------------------------------------------------------------------
        header_card = StyledCard(
            orientation="vertical",
            size_hint_y=None,
            height=85,
            padding=[16, 12, 16, 12],
            spacing=4,
        )
        self.title_label = Label(
            text="⚡ AI CAR DOCTOR",
            font_size="20sp",
            bold=True,
            size_hint_y=None,
            height=28,
            color=(0.95, 0.96, 0.98, 1.0),
        )
        self.status_label = Label(
            text="AI Car Doctor — gotowy do diagnostyki",
            font_size="13sp",
            size_hint_y=None,
            height=22,
            color=COLOR_TEXT_MUTED,
        )
        header_card.add_widget(self.title_label)
        header_card.add_widget(self.status_label)
        self.content_box.add_widget(header_card)

        # ---------------------------------------------------------------------
        # 2. Panel selektora modeli mowy (STT/TTS)
        # ---------------------------------------------------------------------
        speech_selector_box = BoxLayout(orientation="vertical", size_hint_y=None, height=140, spacing=5)
        self.speech_status_label = Label(
            text="🎙️ STT: Nie wybrano | 🗣️ TTS: Nie wybrano | Mikrofon: ON",
            size_hint_y=None,
            height=28,
            font_size=12,
            bold=True,
        )
        speech_selector_box.add_widget(self.speech_status_label)

        # Grid dla STT i TTS
        self.speech_grid = GridLayout(cols=2, spacing=5, size_hint_y=None)
        self.speech_grid.cols = 2  # Dwie kolumny: STT po lewej, TTS po prawej
        self.speech_grid.spacing_y = 5

        self._create_speech_model_cards()
        speech_selector_box.add_widget(self.speech_grid)
        self.content_box.add_widget(speech_selector_box)

        # ---------------------------------------------------------------------
        # 3. Panel selektora modeli AI
        # ---------------------------------------------------------------------
        model_selector_box = BoxLayout(orientation="vertical", size_hint_y=None, height=160, spacing=5)
        self.model_status_label = Label(
            text="🤖 Model AI: Nie wybrano",
            size_hint_y=None,
            height=30,
            font_size=14,
            bold=True,
        )
        model_selector_box.add_widget(self.model_status_label)

        self.models_grid = GridLayout(cols=2, spacing=5, size_hint_y=None)
        self.models_grid.cols = 1  # Jedna kolumna na małych ekranach
        self.models_grid.spacing_y = 5

        self._create_model_cards()
        model_selector_box.add_widget(self.models_grid)
        self.content_box.add_widget(model_selector_box)

        # ---------------------------------------------------------------------
        # 4. Pulpit telemetrii na żywo (Siatka 2x2 kart parametrów)
        # ---------------------------------------------------------------------
        telemetry_container = StyledCard(
            orientation="vertical",
            size_hint_y=None,
            height=240,
            padding=[14, 14, 14, 14],
            spacing=10,

        self.grid_telemetry = GridLayout(cols=2, spacing=10, size_hint_y=None, height=135)

        card_rpm = StyledCard(
            orientation="vertical",
            padding=[8, 8, 8, 8],
            bg_color=(0.09, 0.13, 0.20, 1.0),
        )
        card_rpm.add_widget(Label(text="OBROTY", font_size="11sp", color=COLOR_TEXT_MUTED, size_hint_y=None, height=16))
        self.rpm_label = Label(text="Obroty: 0 RPM", font_size="17sp", bold=True, color=(0.06, 0.73, 0.85, 1.0))
        card_rpm.add_widget(self.rpm_label)
        self.grid_telemetry.add_widget(card_rpm)

        card_speed = StyledCard(
            orientation="vertical",
            padding=[8, 8, 8, 8],
            bg_color=(0.09, 0.13, 0.20, 1.0),
        )
        card_speed.add_widget(Label(text="PRĘDKOŚĆ", font_size="11sp", color=COLOR_TEXT_MUTED, size_hint_y=None, height=16))
        self.speed_label = Label(text="Prędkość: 0 km/h", font_size="17sp", bold=True, color=(0.06, 0.73, 0.85, 1.0))
        card_speed.add_widget(self.speed_label)
        self.grid_telemetry.add_widget(card_speed)

        card_coolant = StyledCard(
            orientation="vertical",
            padding=[8, 8, 8, 8],
            bg_color=(0.09, 0.13, 0.20, 1.0),
        )
        card_coolant.add_widget(Label(text="PŁYN CHŁODZĄCY", font_size="11sp", color=COLOR_TEXT_MUTED, size_hint_y=None, height=16))
        self.coolant_label = Label(text="Temp. płynu: 0 °C", font_size="17sp", bold=True, color=(0.16, 0.80, 0.53, 1.0))
        card_coolant.add_widget(self.coolant_label)
        self.grid_telemetry.add_widget(card_coolant)

        card_volt = StyledCard(
            orientation="vertical",
            padding=[8, 8, 8, 8],
            bg_color=(0.09, 0.13, 0.20, 1.0),
        )
        card_volt.add_widget(Label(text="AKUMULATOR", font_size="11sp", color=COLOR_TEXT_MUTED, size_hint_y=None, height=16))
        self.voltage_label = Label(text="Napięcie: 0.0 V", font_size="17sp", bold=True, color=(0.16, 0.80, 0.53, 1.0))
        card_volt.add_widget(self.voltage_label)
        self.grid_telemetry.add_widget(card_volt)

        telemetry_container.add_widget(self.grid_telemetry)

        self.refresh_telemetry_btn = Button(
            text="🔄 Odśwież telemetrię",
            font_size="13sp",
            bold=True,
            size_hint_y=None,
            height=38,
            background_normal="",
            background_color=(0.20, 0.25, 0.35, 1.0),
        )
        self.refresh_telemetry_btn.bind(on_press=self.on_refresh_telemetry)
        telemetry_container.add_widget(self.refresh_telemetry_btn)

        self.content_box.add_widget(telemetry_container)

        # ---------------------------------------------------------------------
        # 3. Wykres przebiegu parametrów (Telemetry Trend Chart)
        # ---------------------------------------------------------------------
        self.chart = TelemetryChart()
        self.content_box.add_widget(self.chart)

        # ---------------------------------------------------------------------
        # 4. Panel ustawień połączenia (Bluetooth Mobile / USB Laptop)
        # ---------------------------------------------------------------------
        settings_card = StyledCard(
            orientation="vertical",
            size_hint_y=None,
            height=215,
            padding=[14, 12, 14, 12],
            spacing=8,
        )

        settings_header = BoxLayout(size_hint_y=None, height=24, spacing=6)
        settings_title = Label(
            text="⚙️ USTAWIENIA POŁĄCZENIA OBD-II",
            font_size="13sp",
            bold=True,
            color=COLOR_TEXT_MUTED,
            size_hint_x=0.7,
            halign="left",
            valign="middle",
        )
        settings_header.add_widget(settings_title)
        settings_card.add_widget(settings_header)

        # Szybkie profile połączenia
        profiles_grid = GridLayout(cols=5, spacing=4, size_hint_y=None, height=34)

        self.btn_prof_mobile_bt = Button(
            text="📱 Mobile BT",
            font_size="10sp",
            bold=True,
            background_normal="",
            background_color=COLOR_PRIMARY,
        )
        self.btn_prof_mobile_bt.bind(on_press=lambda _b: self.on_select_connection_profile("mobile_bt"))
        profiles_grid.add_widget(self.btn_prof_mobile_bt)

        self.btn_prof_laptop_linux = Button(
            text="💻 Linux USB",
            font_size="10sp",
            bold=True,
            background_normal="",
            background_color=(0.18, 0.22, 0.30, 1.0),
        )
        self.btn_prof_laptop_linux.bind(on_press=lambda _b: self.on_select_connection_profile("laptop_usb_linux"))
        profiles_grid.add_widget(self.btn_prof_laptop_linux)

        self.btn_prof_laptop_win = Button(
            text="💻 Win COM",
            font_size="10sp",
            bold=True,
            background_normal="",
            background_color=(0.18, 0.22, 0.30, 1.0),
        )
        self.btn_prof_laptop_win.bind(on_press=lambda _b: self.on_select_connection_profile("laptop_usb_win"))
        profiles_grid.add_widget(self.btn_prof_laptop_win)

        self.btn_prof_laptop_bt = Button(
            text="💻 Laptop BT",
            font_size="10sp",
            bold=True,
            background_normal="",
            background_color=(0.18, 0.22, 0.30, 1.0),
        )
        self.btn_prof_laptop_bt.bind(on_press=lambda _b: self.on_select_connection_profile("laptop_bt"))
        profiles_grid.add_widget(self.btn_prof_laptop_bt)

        self.btn_prof_auto = Button(
            text="🔍 Auto",
            font_size="10sp",
            bold=True,
            background_normal="",
            background_color=(0.18, 0.22, 0.30, 1.0),
        )
        self.btn_prof_auto.bind(on_press=lambda _b: self.on_select_connection_profile("auto"))
        profiles_grid.add_widget(self.btn_prof_auto)

        settings_card.add_widget(profiles_grid)

        # Wiersz konfiguracji portu i prędkości baudrate
        config_row = BoxLayout(size_hint_y=None, height=36, spacing=8)
        config_row.add_widget(Label(text="Port / ID:", font_size="12sp", color=COLOR_TEXT_MUTED, size_hint_x=0.25))
        self.port_input = TextInput(
            text="OBDII",
            multiline=False,
            font_size="12sp",
            size_hint_x=0.45,
            background_color=(0.15, 0.20, 0.30, 1.0),
            foreground_color=(1, 1, 1, 1),
        )
        config_row.add_widget(self.port_input)

        self.btn_baud_select = Button(
            text="38400 baud",
            font_size="11sp",
            size_hint_x=0.30,
            background_normal="",
            background_color=(0.20, 0.26, 0.36, 1.0),
        )
        self.btn_baud_select.bind(on_press=self.on_cycle_baudrate)
        config_row.add_widget(self.btn_baud_select)
        settings_card.add_widget(config_row)

        # Wiersz akcji połączenia
        conn_actions = BoxLayout(size_hint_y=None, height=36, spacing=8)
        self.connect_btn = Button(
            text="🔌 Połącz z adapterem",
            font_size="12sp",
            bold=True,
            size_hint_x=0.65,
            background_normal="",
            background_color=COLOR_SUCCESS,
        )
        self.connect_btn.bind(on_press=self.on_connect_obd)
        conn_actions.add_widget(self.connect_btn)

        self.disconnect_btn = Button(
            text="Rozłącz",
            font_size="12sp",
            size_hint_x=0.35,
            background_normal="",
            background_color=(0.18, 0.22, 0.30, 1.0),
        )
        self.disconnect_btn.bind(on_press=self.on_disconnect_obd)
        conn_actions.add_widget(self.disconnect_btn)
        settings_card.add_widget(conn_actions)

        # Etykieta statusu połączenia
        self.connection_status_label = Label(
            text="Aktywny profil: 📱 Mobile Bluetooth (OBDII, 38400 baud)",
            font_size="11sp",
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=18,
            halign="left",
            valign="middle",
        )
        settings_card.add_widget(self.connection_status_label)

        self.content_box.add_widget(settings_card)

        # ---------------------------------------------------------------------
        # 5. Panel symulatora awarii & scenariuszy demo
        # ---------------------------------------------------------------------
        sim_container = StyledCard(
            orientation="vertical",
            size_hint_y=None,
            height=165,
            padding=[14, 12, 14, 12],
            spacing=8,
        )

        sim_header = BoxLayout(size_hint_y=None, height=26, spacing=6)
        sim_title = Label(
            text="🎮 SYMULATOR USTEREK (DEMO)",
            font_size="13sp",
            bold=True,
            color=COLOR_TEXT_MUTED,
            size_hint_x=0.55,
            halign="left",
            valign="middle",
        )
        sim_header.add_widget(sim_title)

        self.sim_toggle_btn = Button(
            text="Symulacja: WYŁ",
            font_size="11sp",
            bold=True,
            size_hint_x=0.45,
            background_normal="",
            background_color=(0.18, 0.22, 0.30, 1.0),
        )
        self.sim_toggle_btn.bind(on_press=self.on_toggle_simulation)
        sim_header.add_widget(self.sim_toggle_btn)
        sim_container.add_widget(sim_header)

        scenarios_grid = GridLayout(cols=3, spacing=6, size_hint_y=None, height=72)

        self.btn_scen_clean = Button(
            text="🟢 Czysty (OK)",
            font_size="11sp",
            bold=True,
            background_normal="",
            background_color=(0.14, 0.22, 0.25, 1.0),
        )
        self.btn_scen_clean.bind(on_press=lambda _b: self.on_select_scenario("clean"))
        scenarios_grid.add_widget(self.btn_scen_clean)

        self.btn_scen_misfire = Button(
            text="🟡 Misfire P0300",
            font_size="11sp",
            bold=True,
            background_normal="",
            background_color=(0.28, 0.22, 0.15, 1.0),
        )
        self.btn_scen_misfire.bind(on_press=lambda _b: self.on_select_scenario("misfire"))
        scenarios_grid.add_widget(self.btn_scen_misfire)

        self.btn_scen_overheat = Button(
            text="🔴 Przegrzanie P0217",
            font_size="11sp",
            bold=True,
            background_normal="",
            background_color=(0.32, 0.14, 0.18, 1.0),
        )
        self.btn_scen_overheat.bind(on_press=lambda _b: self.on_select_scenario("overheat"))
        scenarios_grid.add_widget(self.btn_scen_overheat)

        self.btn_scen_lean = Button(
            text="🟠 Uboga P0171",
            font_size="11sp",
            bold=True,
            background_normal="",
            background_color=(0.25, 0.20, 0.14, 1.0),
        )
        self.btn_scen_lean.bind(on_press=lambda _b: self.on_select_scenario("lean_mix"))
        scenarios_grid.add_widget(self.btn_scen_lean)

        self.btn_scen_volt = Button(
            text="🔋 Akumulator P0562",
            font_size="11sp",
            bold=True,
            background_normal="",
            background_color=(0.24, 0.16, 0.22, 1.0),
        )
        self.btn_scen_volt.bind(on_press=lambda _b: self.on_select_scenario("low_voltage"))
        scenarios_grid.add_widget(self.btn_scen_volt)

        sim_container.add_widget(scenarios_grid)
        self.content_box.add_widget(sim_container)

        # ---------------------------------------------------------------------
        # 6. Panel raportu diagnostycznego AI
        # ---------------------------------------------------------------------
        self.report_card = StyledCard(
            orientation="vertical",
            size_hint_y=None,
            height=200,
            padding=[16, 14, 16, 14],
            spacing=8,
        )

        report_title = Label(
            text="🧠 ANALIZA DIAGNOSTYCZNA AI",
            font_size="13sp",
            bold=True,
            size_hint_y=None,
            height=20,
            color=COLOR_TEXT_MUTED,
        )
        self.report_card.add_widget(report_title)

        self.urgency_badge = Label(
            text="[ Status AI: Brak aktywnego raportu ]",
            font_size="13sp",
            bold=True,
            size_hint_y=None,
            height=28,
            color=COLOR_SUCCESS,
        )
        self.report_card.add_widget(self.urgency_badge)

        self.report_summary_label = Label(
            text=f"Brak wykrytych usterek.\n\n{DISCLAIMER_TEXT}",
            font_size="12sp",
            halign="left",
            valign="top",
            color=(0.88, 0.90, 0.94, 1.0),
        )
        self.report_card.add_widget(self.report_summary_label)
        self.content_box.add_widget(self.report_card)

        # ---------------------------------------------------------------------
        # 6. Panel asystenta głosowego (Hands-Free Speech AI: Whisper / Piper)
        # ---------------------------------------------------------------------
        self.voice_card = StyledCard(
            orientation="vertical",
            size_hint_y=None,
            height=290,
            padding=[16, 14, 16, 14],
            spacing=8,
        )

        voice_header = BoxLayout(orientation="horizontal", size_hint_y=None, height=28)
        voice_title = Label(
            text="🎙️ ASYSTENT GŁOSOWY KIEROWCY (HANDS-FREE)",
            font_size="13sp",
            bold=True,
            halign="left",
            color=COLOR_VOICE,
        )
        voice_header.add_widget(voice_title)
        self.voice_card.add_widget(voice_header)

        # Siatka 6 szybkich poleceń głosowych
        quick_grid = GridLayout(cols=3, spacing=6, size_hint_y=None, height=72)

        self.btn_cmd_temp = Button(
            text="🌡️ Temp. cieczy",
            font_size="11sp",
            bold=True,
            background_normal="",
            background_color=(0.20, 0.22, 0.32, 1.0),
        )
        self.btn_cmd_temp.bind(on_press=lambda _b: self.on_quick_voice_command("Jaka jest temperatura płynu chłodzącego?"))
        quick_grid.add_widget(self.btn_cmd_temp)

        self.btn_cmd_volt = Button(
            text="🔋 Akumulator",
            font_size="11sp",
            bold=True,
            background_normal="",
            background_color=(0.20, 0.22, 0.32, 1.0),
        )
        self.btn_cmd_volt.bind(on_press=lambda _b: self.on_quick_voice_command("Jakie jest napięcie akumulatora?"))
        quick_grid.add_widget(self.btn_cmd_volt)

        self.btn_cmd_dtc = Button(
            text="🚨 Błędy DTC",
            font_size="11sp",
            bold=True,
            background_normal="",
            background_color=(0.20, 0.22, 0.32, 1.0),
        )
        self.btn_cmd_dtc.bind(on_press=lambda _b: self.on_quick_voice_command("Jakie mam błędy?"))
        quick_grid.add_widget(self.btn_cmd_dtc)

        self.btn_cmd_safe = Button(
            text="🛡️ Czy jechać?",
            font_size="11sp",
            bold=True,
            background_normal="",
            background_color=(0.20, 0.22, 0.32, 1.0),
        )
        self.btn_cmd_safe.bind(on_press=lambda _b: self.on_quick_voice_command("Czy mogę bezpiecznie jechać dalej?"))
        quick_grid.add_widget(self.btn_cmd_safe)

        self.btn_cmd_speed = Button(
            text="🏎️ Prędkość/RPM",
            font_size="11sp",
            bold=True,
            background_normal="",
            background_color=(0.20, 0.22, 0.32, 1.0),
        )
        self.btn_cmd_speed.bind(on_press=lambda _b: self.on_quick_voice_command("Z jaką prędkością jadę i jakie mam obroty?"))
        quick_grid.add_widget(self.btn_cmd_speed)

        self.btn_cmd_help = Button(
            text="❓ Pomoc",
            font_size="11sp",
            bold=True,
            background_normal="",
            background_color=(0.20, 0.22, 0.32, 1.0),
        )
        self.btn_cmd_help.bind(on_press=lambda _b: self.on_quick_voice_command("Pomoc - jakie komendy mogę wydać?"))
        quick_grid.add_widget(self.btn_cmd_help)

        self.voice_card.add_widget(quick_grid)

        # Etykiety statusu i odpowiedzi asystenta
        self.voice_status_label = Label(
            text="Gotowy (naciśnij nagrywanie lub wybierz szybką komendę)",
            font_size="11sp",
            size_hint_y=None,
            height=20,
            halign="left",
            color=COLOR_TEXT_MUTED,
        )
        self.voice_card.add_widget(self.voice_status_label)

        self.voice_response_label = Label(
            text="Wybierz polecenie powyżej, aby usłyszeć odpowiedź asystenta mowy.",
            font_size="10sp",
            size_hint_y=None,
            height=16,
            halign="left",
            valign="top",
            color=(0.88, 0.90, 0.94, 1.0),
        )
        self.voice_card.add_widget(self.voice_response_label)

        # Wiersz sterowania asystentem
        voice_live_row = BoxLayout(size_hint_y=None, height=36, spacing=8)

        self.voice_custom_input = TextInput(
            text="",
            multiline=False,
            font_size="11sp",
            size_hint_x=0.55,
            background_color=(0.10, 0.14, 0.20, 1.0),
            foreground_color=(1.0, 1.0, 1.0, 1.0),
        )
        voice_live_row.add_widget(self.voice_custom_input)

        self.btn_voice_send = Button(
            text="Zapytaj",
            font_size="12sp",
            bold=True,
            size_hint_x=0.20,
            background_normal="",
            background_color=COLOR_PRIMARY,
        )
        self.btn_voice_send.bind(on_press=self.on_send_custom_voice_query)
        voice_live_row.add_widget(self.btn_voice_send)
        self.voice_card.add_widget(voice_live_row)

        self.voice_card.add_widget(self.voice_response_label)
        self.content_box.add_widget(self.voice_card)
        self.btn_cmd_help = Button(
            text="❓ Pomoc",
            font_size="11sp",
            bold=True,
            background_normal="",
            background_color=(0.20, 0.22, 0.32, 1.0),
        )
        self.btn_cmd_help.bind(on_press=lambda _b: self.on_quick_voice_command("Pomoc - jakie komendy mogę wydać?"))
        quick_grid.add_widget(self.btn_cmd_help)

        self.voice_card.add_widget(quick_grid)

        # Wiersz interakcji na żywo
        voice_live_row = BoxLayout(orientation="horizontal", spacing=6, size_hint_y=None, height=36)

        self.btn_voice_record = Button(
            text="🎙️ Nagraj (3s)",
            font_size="12sp",
            bold=True,
            size_hint_x=0.35,
            background_normal="",
            background_color=COLOR_VOICE,
        )
        self.btn_voice_record.bind(on_press=self.on_voice_record_button)
        voice_live_row.add_widget(self.btn_voice_record)

        self.voice_custom_input = TextInput(
            hint_text="Wpisz komendę lub pytanie...",
            text="",
            multiline=False,
            font_size="12sp",
            size_hint_x=0.45,
            background_color=(0.10, 0.14, 0.20, 1.0),
            foreground_color=(1.0, 1.0, 1.0, 1.0),
        )
        voice_live_row.add_widget(self.voice_custom_input)

        self.btn_voice_send = Button(
            text="Zapytaj",
            font_size="12sp",
            bold=True,
            size_hint_x=0.20,
            background_normal="",
            background_color=COLOR_PRIMARY,
        )
        self.btn_voice_send.bind(on_press=self.on_send_custom_voice_query)
        voice_live_row.add_widget(self.btn_voice_send)
        self.voice_card.add_widget(voice_live_row)

        # Etykiety statusu i odpowiedzi asystenta
        self.voice_status_label = Label(
            text="Gotowy (naciśnij nagrywanie lub wybierz szybką komendę)",
            font_size="11sp",
            size_hint_y=None,
            height=20,
            halign="left",
            color=COLOR_TEXT_MUTED,
        )
        self.voice_card.add_widget(self.voice_status_label)

        self.voice_response_label = Label(
            text="Wybierz polecenie powyżej, aby usłyszeć odpowiedź asystenta mowy.",
            font_size="11sp",
            size_hint_y=None,
            height=60,
            halign="left",
            valign="top",
            color=(0.90, 0.92, 0.96, 1.0),
        )
        self.voice_card.add_widget(self.voice_response_label)
        self.content_box.add_widget(self.voice_card)

        # ---------------------------------------------------------------------
        # 7. Panel akcji (Skanowanie, Asystent głosowy, Dwuetapowe kasowanie, Rejestrator)
        # ---------------------------------------------------------------------
        actions_card = StyledCard(
            orientation="vertical",
            size_hint_y=None,
            height=234,
            padding=[16, 14, 16, 14],
            spacing=10,
        )

        self.scan_btn = Button(
            text="🔍 Skanuj błędy OBD i diagnozuj AI",
            font_size="14sp",
            bold=True,
            size_hint_y=None,
            height=44,
            background_normal="",
            background_color=COLOR_PRIMARY,
        )
        self.scan_btn.bind(on_press=self.on_scan_errors)
        actions_card.add_widget(self.scan_btn)

        self.voice_btn = Button(
            text="🎙️ Asystent głosowy (Zapytaj AI)",
            font_size="14sp",
            bold=True,
            size_hint_y=None,
            height=44,
            background_normal="",
            background_color=COLOR_VOICE,
        )
        self.voice_btn.bind(on_press=self.on_voice_assistant)
        actions_card.add_widget(self.voice_btn)

        # Rząd rejestratora trasy (SQLite) i eksportu CSV
        logging_row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=44)

        self.btn_toggle_logging = Button(
            text="⏺️ Rejestruj trasę: WYŁ",
            font_size="13sp",
            bold=True,
            size_hint_x=0.55,
            background_normal="",
            background_color=(0.18, 0.22, 0.30, 1.0),
        )
        self.btn_toggle_logging.bind(on_press=self.on_toggle_logging)
        logging_row.add_widget(self.btn_toggle_logging)

        self.btn_export_csv = Button(
            text="💾 Eksportuj CSV",
            font_size="13sp",
            bold=True,
            size_hint_x=0.45,
            background_normal="",
            background_color=(0.14, 0.28, 0.22, 1.0),
        )
        self.btn_export_csv.bind(on_press=self.on_export_csv)
        logging_row.add_widget(self.btn_export_csv)
        actions_card.add_widget(logging_row)

        self.clear_btn = Button(
            text="🗑️ Skasuj kody błędów DTC",
            font_size="14sp",
            bold=True,
            size_hint_y=None,
            height=44,
            background_normal="",
            background_color=(0.18, 0.22, 0.30, 1.0),
        )
        self.clear_btn.bind(on_press=self.on_clear_dtc)
        actions_card.add_widget(self.clear_btn)

        self.content_box.add_widget(actions_card)

        scroll.add_widget(self.content_box)
        self.add_widget(scroll)

        # Inicjalne odświeżenie danych telemetrii
        self.update_telemetry_ui()

        # Przycisk włącz/wyłącz mikrofon
        self.mic_btn = Button(
            text="🎤 Mikrofon: ON",
            size_hint_y=None,
            height=40,
            font_size=12,
            bold=True,
            color=0x00FF00 if self.controller.mic_enabled else 0xFF0000,
        )
        self.mic_btn.bind(on_press=self.on_toggle_mic)
        self.add_widget(self.mic_btn)
        card.add_widget(spec_label)
        card.add_widget(desc_label)

        # Przycisk wyboru
        btn = Button(
            text=f"Wybierz {model_type}",
            size_hint_y=None,
            height=28,
            font_size=10,
        )
        btn.bind(on_press=self._on_speech_card_press)
        btn.user_data = (model, model_type)
        card.add_widget(btn)

        return card

    def _on_speech_card_press(self, _btn: Button) -> None:
        """Obsługa kliknięcia w kartę modelu mowy."""
        model, model_type = _btn.user_data
        if model_type == "STT":
            self.controller.on_stt_model_select(model)
            self.speech_status_label.text = f"🎙️ STT: {model.name} | 🗣️ TTS: {self.controller.current_tts_model_spec.name if self.controller.current_tts_model_spec else 'Nie wybrano'} | Mikrofon: {'ON' if self.controller.mic_enabled else 'OFF'}"
        else:
            self.controller.on_tts_model_select(model)
            self.speech_status_label.text = f"🎙️ STT: {self.controller.current_stt_model_spec.name if self.controller.current_stt_model_spec else 'Nie wybrano'} | 🗣️ TTS: {model.name} | Mikrofon: {'ON' if self.controller.mic_enabled else 'OFF'}"

    def _create_model_cards(self) -> None:
        """Tworzy karty dla każdego dostępnego modelu LLM."""
        for model in self.controller.available_models:
            # Karta modelu
            model_card = BoxLayout(orientation="vertical", size_hint_y=None, height=80, spacing=3)

            # Nazwa modelu
            model_name_label = Label(
                text=model.name,
                size_hint_y=None,
                height=24,
                font_size=13,
                bold=True,
            )

            # Specyfikacja (rozmiar, RAM)
            spec_label = Label(
                text=f"📦 {model.size_mb} MB | 💾 {model.ram_required_mb} MB RAM",
                size_hint_y=None,
                height=18,
                font_size=11,
            )

            # Rekomendacja
            rec_label = Label(
                text=self._get_recommendation_text(model),
                size_hint_y=None,
                height=16,
                font_size=10,
                color=1,  # Jasny kolor dla kontrastu
            )

            model_card.add_widget(model_name_label)
            model_card.add_widget(spec_label)
            model_card.add_widget(rec_label)

            # Przycisk wyboru
            select_btn = Button(
                text="Wybierz",
                size_hint_y=None,
                height=30,
                font_size=11,
            )
            select_btn.bind(on_press=self._on_model_card_press)
            select_btn.user_data = model  # Przechowujemy obiekt modelu
            model_card.add_widget(select_btn)

            self.models_grid.add_widget(model_card)

    def _get_recommendation_text(self, model: LLMModelSpec) -> str:
        """Zwraca tekst rekomendacji dla modelu."""
        rec = model.recommended_for
        if rec == "mobile_ultra_light":
            return "🚀 Dla starszych telefonów"
        elif rec == "mobile_standard":
            return "⭐ Zalecany domyślny"
        elif rec == "mobile_high_end":
            return "🏆 Najlepszy polski"
        return rec

    def _on_model_card_press(self, _btn: Button) -> None:
        """Obsługa kliknięcia w kartę modelu."""
        model = _btn.user_data
        if model:
            self.controller.on_model_select(model)
            self.model_status_label.text = f"🤖 Model AI: {model.name}"
            self.model_status_label.color = 0x00FF00  # Zielony
        else:
            self.model_status_label.text = f"🤖 Model AI: Nie wybrano"
            self.model_status_label.color = 1  # Szary

    def on_toggle_mic(self, _btn: Button) -> None:
        """Obsługa przycisku włącz/wyłącz mikrofon."""
        self.controller.toggle_mic_enabled(not self.controller.mic_enabled)
        new_text = "🎤 Mikrofon: ON" if self.controller.mic_enabled else "🎤 Mikrofon: OFF"
        new_color = 0x00FF00 if self.controller.mic_enabled else 0xFF0000
        self.mic_btn.text = new_text
        self.mic_btn.color = new_color

    def update_telemetry_ui(self) -> None:
        t = self.controller.telemetry
        self.rpm_label.text = f"Obroty: {t.get('rpm', 0)} RPM"
        self.speed_label.text = f"Prędkość: {t.get('speed', 0)} km/h"
        coolant = t.get("coolant_temp", 0)
        self.coolant_label.text = f"Temp. płynu: {coolant} °C"
        voltage = t.get("voltage", 0.0)
        self.voltage_label.text = f"Napięcie: {voltage:.1f} V"

        hist = self.controller.get_telemetry_history(self.chart.current_metric)
        self.chart.update_history(hist)

        if coolant >= 115:
            self.coolant_label.color = COLOR_DANGER
        elif coolant >= 105:
            self.coolant_label.color = COLOR_WARNING
        else:
            self.coolant_label.color = COLOR_SUCCESS

        if voltage > 0 and voltage < 11.8:
            self.voltage_label.color = COLOR_WARNING
        else:
            self.voltage_label.color = COLOR_SUCCESS

    def on_select_connection_profile(self, profile_key: str) -> None:
        """Wybiera profil połączenia i aktualizuje pola w GUI."""
        prof = self.controller.apply_connection_profile(profile_key)
        self.port_input.text = prof.get("port", "")
        baud = prof.get("baudrate", 38400)
        self.btn_baud_select.text = f"{baud} baud" if baud > 0 else "Auto baud"

        # Aktualizacja wizualnego podświetlenia przycisków profili
        btns = {
            "mobile_bt": self.btn_prof_mobile_bt,
            "laptop_usb_linux": self.btn_prof_laptop_linux,
            "laptop_usb_win": self.btn_prof_laptop_win,
            "laptop_bt": self.btn_prof_laptop_bt,
            "auto": self.btn_prof_auto,
        }
        for k, btn in btns.items():
            btn.background_color = COLOR_PRIMARY if k == profile_key else (0.18, 0.22, 0.30, 1.0)

        self.connection_status_label.text = f"Aktywny profil: {prof['name']} ({prof.get('port') or 'Auto'})"
        self.status_label.text = f"Wybrano profil: {prof['name']}"

    def on_cycle_baudrate(self, _btn=None) -> None:
        """Przełącza cyklicznie prędkości transmisji baudrate."""
        rates = [38400, 115200, 9600, 0]
        curr_baud = self.controller.connection_config.get("baudrate", 38400)
        idx = rates.index(curr_baud) if curr_baud in rates else 0
        next_baud = rates[(idx + 1) % len(rates)]
        self.controller.connection_config["baudrate"] = next_baud
        self.btn_baud_select.text = f"{next_baud} baud" if next_baud > 0 else "Auto baud"

    def on_connect_obd(self, _btn=None) -> None:
        """Próbuje nawiązać połączenie z adapterem ELM327 na podstawie ustawień z GUI."""
        port = self.port_input.text.strip()
        baud = self.controller.connection_config.get("baudrate", 38400)
        self.controller.update_connection_settings(port=port, baudrate=baud)

        self.connection_status_label.text = f"Łączenie z {port or 'Auto'}..."
        res = self.controller.connect_obd(port=port, baudrate=baud)

        self.connection_status_label.text = res["message"]
        self.status_label.text = res["message"]
        if res["connected"]:
            self.connect_btn.background_color = COLOR_SUCCESS
            self.on_refresh_telemetry()
        else:
            self.connect_btn.background_color = (0.25, 0.30, 0.40, 1.0)

    def on_disconnect_obd(self, _btn=None) -> None:
        """Rozłącza aktywne połączenie."""
        res = self.controller.disconnect_obd()
        self.connection_status_label.text = res["message"]
        self.status_label.text = "Adapter OBD rozłączony"
        self.connect_btn.background_color = COLOR_SUCCESS

    def on_toggle_simulation(self, _btn=None) -> None:
        """Przełącza tryb symulacji włączony / wyłączony."""
        if not self.controller.simulation_mode:
            self.controller.enable_simulation(self.controller.active_scenario)
            self.sim_toggle_btn.text = f"Symulacja: WŁ ({self.controller.active_scenario})"
            self.sim_toggle_btn.background_color = COLOR_SUCCESS
            self.status_label.text = f"Włączono tryb symulacji: {self.controller.active_scenario}"
        else:
            self.controller.disable_simulation()
            self.sim_toggle_btn.text = "Symulacja: WYŁ"
            self.sim_toggle_btn.background_color = (0.18, 0.22, 0.30, 1.0)
            self.status_label.text = "Wyłączono symulację (powrót do OBD)"

        self.update_telemetry_ui()

    def on_select_scenario(self, scenario_key: str) -> None:
        """Ładuje i aktywuje wybrany scenariusz symulacji."""
        scen = self.controller.load_simulation_scenario(scenario_key)
        self.controller.simulation_mode = True
        self.sim_toggle_btn.text = f"Symulacja: WŁ ({scenario_key})"
        self.sim_toggle_btn.background_color = COLOR_SUCCESS
        self.status_label.text = f"Załadowano scenariusz: {scen['name']}"
        self.update_telemetry_ui()
        self.on_scan_errors()

    def on_model_select_action(self, _btn: Button) -> None:
        """Obsługa przycisku wybrania modelu."""
        if self.controller.current_model_spec:
            self.controller.on_model_select(self.controller.current_model_spec)
            self.model_status_label.text = f"🤖 Model AI: {self.controller.current_model_spec.name}"
            self.model_status_label.color = 0x00FF00  # Zielony
        else:
            self.model_status_label.text = f"🤖 Model AI: Nie wybrano"
            self.model_status_label.color = 1  # Szary

    def on_refresh_telemetry(self, _btn=None) -> None:
        self.controller.refresh_telemetry()
        self.update_telemetry_ui()
        self.status_label.text = "Telemetria zaktualizowana"

    def on_scan_errors(self, _btn=None) -> None:
        codes, report = self.controller.scan_dtc_and_diagnose()
        self.update_telemetry_ui()

        self.clear_btn.text = "🗑️ Skasuj kody błędów DTC"
        self.clear_btn.background_color = (0.18, 0.22, 0.30, 1.0)

        if not codes:
            self.status_label.text = "Nie wykryto błędów DTC"
            self.urgency_badge.text = "[ Bezpieczna jazda: TAK | Brak błędów ]"
            self.urgency_badge.color = COLOR_SUCCESS
            self.report_summary_label.text = (
                f"Brak aktywnych kodów błędów w sterowniku ECU.\n\n{DISCLAIMER_TEXT}"
            )
            return

        self.status_label.text = f"Wykryto {len(codes)} kod(y) błędów"
        if report:
            safe_text = "TAK" if report.safe_to_drive else "NIE (Zatrzymaj pojazd!)"
            urgency_text = getattr(
                report, "overall_urgency", getattr(report, "urgency", "info")
            ).upper()
            self.urgency_badge.text = (
                f"[ Bezpieczna jazda: {safe_text} | Pilność: {urgency_text} ]"
            )
            if not report.safe_to_drive or urgency_text == "CRITICAL":
                self.urgency_badge.color = COLOR_DANGER
            elif urgency_text == "WARNING":
                self.urgency_badge.color = COLOR_WARNING
            else:
                self.urgency_badge.color = COLOR_SUCCESS

            steps = "\n".join(f"• {s}" for s in report.next_steps)
            self.report_summary_label.text = (
                f"Podsumowanie: {report.summary}\n\n"
                f"Zalecane kroki:\n{steps}\n\n"
                f"{DISCLAIMER_TEXT}"
            )
        else:
            self.report_summary_label.text = f"Kody: {codes}\n\n{DISCLAIMER_TEXT}"

    def on_clear_dtc(self, _btn=None) -> None:
        if not self.controller.dtc_clear_pending:
            res = self.controller.request_clear_dtc()
            self.status_label.text = res["message"]
            if res.get("pending"):
                self.clear_btn.text = "⚠️ POTWIERDŹ KASOWANIE NA POSTOJU"
                self.clear_btn.background_color = COLOR_DANGER
        else:
            res = self.controller.confirm_clear_dtc()
            self.clear_btn.text = "🗑️ Skasuj kody błędów DTC"
            self.clear_btn.background_color = (0.18, 0.22, 0.30, 1.0)
            if res.get("success"):
                self.on_scan_errors()
            self.status_label.text = res["message"]

    def on_quick_voice_command(self, prompt: str) -> None:
        """Wykonuje szybkie predefiniowane zapytanie głosowe."""
        query, answer, _ = self.controller.handle_quick_voice_command(prompt)
        self.voice_status_label.text = f"Komenda: \"{query}\""
        self.voice_response_label.text = answer
        self.status_label.text = f"Głos: {query}"
        self.report_summary_label.text = (
            f"Odpowiedź asystenta głosowego:\n{answer}\n\n{DISCLAIMER_TEXT}"
        )

    def on_voice_record_button(self, _btn=None) -> None:
        """Nagrywa mowę z mikrofonu i przetwarza przez STT -> Analiza -> TTS."""
        query, answer, _ = self.controller.record_and_handle_voice()
        self.voice_status_label.text = f"Rozpoznano mowę: \"{query}\""
        self.voice_response_label.text = answer
        self.status_label.text = f"Głos: {query}"
        self.report_summary_label.text = (
            f"Odpowiedź asystenta głosowego:\n{answer}\n\n{DISCLAIMER_TEXT}"
        )

    def on_send_custom_voice_query(self, _btn=None) -> None:
        """Wysyła zapytanie wpisane ręcznie w polu tekstowym asystenta."""
        txt = self.voice_custom_input.text.strip()
        if not txt:
            txt = "Co z autem?"
        query, answer, _ = self.controller.handle_voice_input(text_query=txt)
        self.voice_custom_input.text = ""
        self.voice_status_label.text = f"Zapytanie: \"{query}\""
        self.voice_response_label.text = answer
        self.status_label.text = f"Głos: {query}"
        self.report_summary_label.text = (
            f"Odpowiedź asystenta głosowego:\n{answer}\n\n{DISCLAIMER_TEXT}"
        )

    def on_voice_assistant(self, _btn=None) -> None:
        query, answer, _ = self.controller.handle_voice_input(
            text_query="Co z autem?"
        )
        self.voice_status_label.text = f"Komenda: \"{query}\""
        self.voice_response_label.text = answer
        self.status_label.text = f"Głos: {query}"
        self.report_summary_label.text = (
            f"Odpowiedź asystenta głosowego:\n{answer}\n\n{DISCLAIMER_TEXT}"
        )

    def on_toggle_logging(self, _btn=None) -> None:
        """Włącza lub wyłącza nagrywanie próbek telemetrii do bazy SQLite."""
        if not self.controller.is_logging:
            sess_id = self.controller.start_telemetry_logging()
            self.btn_toggle_logging.text = "🔴 Rejestrowanie WŁ"
            self.btn_toggle_logging.background_color = COLOR_DANGER
            self.status_label.text = f"Rozpoczęto rejestrację trasy ({sess_id})"
        else:
            self.controller.stop_telemetry_logging()
            self.btn_toggle_logging.text = "⏺️ Rejestruj trasę: WYŁ"
            self.btn_toggle_logging.background_color = (0.18, 0.22, 0.30, 1.0)
            self.status_label.text = "Zatrzymano rejestrację telemetrii"

    def on_export_csv(self, _btn=None) -> None:
        """Eksportuje zarejestrowaną sesję telemetrii do pliku CSV."""
        res = self.controller.export_telemetry_csv()
        self.status_label.text = res["message"]


class AIDoctorApp(App):
    def build(self):
        return CarDoctorUI()


if __name__ == "__main__":
    AIDoctorApp().run()
