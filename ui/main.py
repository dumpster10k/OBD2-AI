from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import Any, Optional

# Zapewnienie dostępności modułów nadrzędnych (core, services)
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from kivy.app import App
    from kivy.core.window import Window
    from kivy.graphics import Color, Line, Rectangle, RoundedRectangle
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.label import Label
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.widget import Widget

    KIVY_AVAILABLE = True
except ImportError:
    KIVY_AVAILABLE = False

    class WidgetStub:
        def __init__(self, *args, **kwargs):
            self.children: list[Any] = []
            self.text: str = kwargs.get("text", "")
            self.color: list[float] = kwargs.get("color", [1.0, 1.0, 1.0, 1.0])
            self.size_hint_y = kwargs.get("size_hint_y", 1)
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

        def setter(self, name: str) -> Any:
            def _setter(val: Any) -> None:
                setattr(self, name, val)
            return _setter

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


from core.obd_client import OBDClient
from services.ai_engine import AIEngine
from services.diagnostic_ai import DiagnosisReport
from services.llm_engine import DISCLAIMER_TEXT

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

        # Przyciski wyboru metryki
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

        # 2. Pasek informacyjny: Min / Max / Aktualna wartość
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

        # 3. Obszar rysowania wykresu (Plot Area)
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
            self.plot_area = WidgetStub(size_hint=(1, 1))
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
    """Kontroler pulpitu diagnostycznego oddzielający logikę biznesową, symulację i telemetrię od Kivy."""

    def __init__(
        self,
        obd_client: Optional[OBDClient] = None,
        ai_engine: Optional[AIEngine] = None,
    ):
        self.obd = obd_client or OBDClient()
        self.ai = ai_engine or AIEngine()
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
        self.dtc_clear_pending: bool = False
        self.session_log: list[dict[str, Any]] = []

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

        if text_query and not audio_data:
            audio_data = self.ai.voice.speech.text_to_speech(text_query)

        query, response, out_audio = self.ai.handle_voice_command(
            audio_data or b"",
            vehicle_context=vehicle_context,
        )
        self.last_voice_query = query
        self.last_voice_response = response
        return query, response, out_audio


class CarDoctorUI(BoxLayout):
    """Nowoczesny pulpit mobilny Kivy z telemetrią na żywo, wykresem trendu, symulatorem i asystentem AI."""

    def __init__(self, controller: Optional[DashboardController] = None, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.controller = controller or DashboardController()

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
        # 2. Pulpit telemetrii na żywo (Siatka 2x2 kart parametrów)
        # ---------------------------------------------------------------------
        telemetry_container = StyledCard(
            orientation="vertical",
            size_hint_y=None,
            height=240,
            padding=[14, 14, 14, 14],
            spacing=10,
        )

        telemetry_title = Label(
            text="📊 TELEMETRIA NA ŻYWO (OBD-II)",
            font_size="13sp",
            bold=True,
            size_hint_y=None,
            height=20,
            color=COLOR_TEXT_MUTED,
        )
        telemetry_container.add_widget(telemetry_title)

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
        # 4. Panel symulatora awarii & scenariuszy demo
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

        # Siatka przycisków scenariuszy
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
        # 5. Panel raportu diagnostycznego AI
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
        # 6. Panel akcji (Skanowanie, Asystent głosowy, Dwuetapowe kasowanie)
        # ---------------------------------------------------------------------
        actions_card = StyledCard(
            orientation="vertical",
            size_hint_y=None,
            height=180,
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

    def update_telemetry_ui(self) -> None:
        t = self.controller.telemetry
        self.rpm_label.text = f"Obroty: {t.get('rpm', 0)} RPM"
        self.speed_label.text = f"Prędkość: {t.get('speed', 0)} km/h"
        coolant = t.get("coolant_temp", 0)
        self.coolant_label.text = f"Temp. płynu: {coolant} °C"
        voltage = t.get("voltage", 0.0)
        self.voltage_label.text = f"Napięcie: {voltage:.1f} V"

        # Aktualizacja wykresu trendu
        hist = self.controller.get_telemetry_history(self.chart.current_metric)
        self.chart.update_history(hist)

        # Dynamiczne akcenty kolorystyczne
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
        # Automatyczne uruchomienie skanowania i diagnozy dla szybkiej weryfikacji
        self.on_scan_errors()

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

    def on_voice_assistant(self, _btn=None) -> None:
        query, answer, _ = self.controller.handle_voice_input(
            text_query="Co z autem?"
        )
        self.status_label.text = f"Głos: {query}"
        self.report_summary_label.text = (
            f"Odpowiedź asystenta głosowego:\n{answer}\n\n{DISCLAIMER_TEXT}"
        )


class AIDoctorApp(App):
    def build(self):
        return CarDoctorUI()


if __name__ == "__main__":
    AIDoctorApp().run()
