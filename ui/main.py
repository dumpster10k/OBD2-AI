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
    from kivy.graphics import Color, Line, RoundedRectangle
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.label import Label
    from kivy.uix.scrollview import ScrollView

    KIVY_AVAILABLE = True
except ImportError:
    KIVY_AVAILABLE = False

    class WidgetStub:
        def __init__(self, *args, **kwargs):
            self.children: list[Any] = []
            self.text: str = kwargs.get("text", "")
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

    class App:
        def build(self) -> Any:
            return None

        def run(self) -> None:
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


class DashboardController:
    """Kontroler pulpitu diagnostycznego oddzielający logikę biznesową od warstwy Kivy."""

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

    def refresh_telemetry(self) -> dict[str, Any]:
        """Pobiera i aktualizuje bieżące parametry telemetryczne pojazdu."""
        self.telemetry = self.obd.get_telemetry()
        return self.telemetry

    def scan_dtc_and_diagnose(self) -> tuple[list[Any], Optional[DiagnosisReport]]:
        """Skanuje kody błędów OBD oraz generuje kompleksowy raport diagnostyczny AI."""
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
    """Nowoczesny, responsywny pulpit mobilny Kivy z telemetrią na żywo, raportami AI i asystentem głosowym."""

    def __init__(self, controller: Optional[DashboardController] = None, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.controller = controller or DashboardController()

        # Ustawienie ciemnego tła okna aplikacji
        if KIVY_AVAILABLE:
            try:
                Window.clearcolor = COLOR_BG
            except Exception:
                pass

        # Główny kontener z przewijaniem (ScrollView)
        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.content_box = BoxLayout(
            orientation="vertical",
            spacing=14,
            padding=[16, 16, 16, 20],
            size_hint_y=None,
        )
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

        # Karty indywidualne metryk
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
        # 3. Panel raportu diagnostycznego AI
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
        # 4. Asystent mowy & Panel akcji
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

        # Dołączenie kontenera do ScrollView i okna
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
