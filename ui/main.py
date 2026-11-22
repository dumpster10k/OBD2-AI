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

logger = logging.getLogger(__name__)


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

        # Konfiguracja modelu AI
        self.available_models: list[LLMModelSpec] = list(RECOMMENDED_LLM_MODELS.values())
        self.current_model_spec: Optional[LLMModelSpec] = self.available_models[0] if self.available_models else None
        self.model_backend_status: str = "Dostępny (Mock)"

        # Konfiguracja mowy (STT/TTS)
        self.available_stt_models: list[SpeechModelSpec] = [m for m in RECOMMENDED_SPEECH_MODELS.values() if m.type == "stt"]
        self.available_tts_models: list[SpeechModelSpec] = [m for m in RECOMMENDED_SPEECH_MODELS.values() if m.type == "tts"]
        self.current_stt_model_spec: Optional[SpeechModelSpec] = self.available_stt_models[0] if self.available_stt_models else None
        self.current_tts_model_spec: Optional[SpeechModelSpec] = self.available_tts_models[0] if self.available_tts_models else None
        self.mic_enabled: bool = True

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

    def load_available_models(self) -> None:
        """Pobiera listę dostępnych modeli LLM."""
        self.available_models = list(RECOMMENDED_LLM_MODELS.values())

    def on_model_select(self, model_spec: LLMModelSpec) -> None:
        """Obsługa wybrania modelu LLM."""
        self.current_model_spec = model_spec
        self.model_backend_status = "Dostępny (Mock)"
        logger.info(f"Wybrano model: {model_spec.name}")

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
    """Główny interfejs mobilny Kivy z pulpitem telemetrii, raportem AI i asystentem głosowym."""

    def __init__(self, controller: Optional[DashboardController] = None, **kwargs):
        super().__init__(orientation="vertical", spacing=10, padding=10, **kwargs)
        self.controller = controller or DashboardController()
        self.controller.load_available_speech_models()  # Inicjalizacja modeli mowy

        # 1. Pasek nagłówka / statusu
        self.status_label = Label(
            text="AI Car Doctor — gotowy do diagnostyki",
            size_hint_y=None,
            height=40,
        )
        self.add_widget(self.status_label)

        # 2. Panel selektora modeli mowy (STT/TTS)
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
        self.add_widget(speech_selector_box)

        # 4. Panel selektora modeli AI
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
        self.add_widget(model_selector_box)

        # 5. Pulpit telemetrii (Karty parametrów na żywo)
        telemetry_box = BoxLayout(
            orientation="vertical", size_hint_y=None, height=140, spacing=5
        )
        self.grid_telemetry = GridLayout(cols=2, spacing=5)

        self.rpm_label = Label(text="Obroty: 0 RPM")
        self.speed_label = Label(text="Prędkość: 0 km/h")
        self.coolant_label = Label(text="Temp. płynu: 0 °C")
        self.voltage_label = Label(text="Napięcie: 0.0 V")

        self.grid_telemetry.add_widget(self.rpm_label)
        self.grid_telemetry.add_widget(self.speed_label)
        self.grid_telemetry.add_widget(self.coolant_label)
        self.grid_telemetry.add_widget(self.voltage_label)

        self.refresh_telemetry_btn = Button(
            text="🔄 Odśwież telemetrię",
            size_hint_y=None,
            height=35,
        )
        self.refresh_telemetry_btn.bind(on_press=self.on_refresh_telemetry)

        telemetry_box.add_widget(self.grid_telemetry)
        telemetry_box.add_widget(self.refresh_telemetry_btn)
        self.add_widget(telemetry_box)

        # 3. Panel raportu diagnostycznego AI
        report_box = BoxLayout(orientation="vertical", spacing=5)
        self.urgency_badge = Label(
            text="[ Status AI: Brak aktywnego raportu ]",
            size_hint_y=None,
            height=30,
        )
        self.report_summary_label = Label(
            text=f"Brak wykrytych usterek.\n\n{DISCLAIMER_TEXT}",
            halign="left",
            valign="top",
        )
        report_box.add_widget(self.urgency_badge)
        report_box.add_widget(self.report_summary_label)
        self.add_widget(report_box)

        # 6. Panel akcji (Skanowanie, Dwuetapowe kasowanie, Asystent głosowy)
        actions_box = BoxLayout(
            orientation="vertical", size_hint_y=None, height=150, spacing=8
        )

        self.scan_btn = Button(
            text="🔍 Skanuj błędy OBD i diagnozuj AI",
            size_hint_y=None,
            height=40,
        )
        self.scan_btn.bind(on_press=self.on_scan_errors)
        actions_box.add_widget(self.scan_btn)

        self.clear_btn = Button(
            text="🗑️ Skasuj kody błędów DTC",
            size_hint_y=None,
            height=40,
        )
        self.clear_btn.bind(on_press=self.on_clear_dtc)
        actions_box.add_widget(self.clear_btn)

        self.voice_btn = Button(
            text="🎙️ Asystent głosowy (Zapytaj AI)",
            size_hint_y=None,
            height=40,
        )
        self.voice_btn.bind(on_press=self.on_voice_assistant)
        actions_box.add_widget(self.voice_btn)

        self.add_widget(actions_box)

        # 7. Przycisk włącz/wyłącz mikrofon
        self.mic_btn = Button(
            text="🎤 Mikrofon: ON",
            size_hint_y=None,
            height=40,
            font_size=12,
            bold=True,
            color=0x00FF00 if self.controller.mic_enabled else 0xFF0000,  # Zielony/OFF
        )
        self.mic_btn.bind(on_press=self.on_toggle_mic)
        self.add_widget(self.mic_btn)

        # Inicjalne odświeżenie danych telemetrii
        self.update_telemetry_ui()

    def _create_speech_model_cards(self) -> None:
        """Tworzy karty dla modeli STT i TTS."""
        # Kolumna STT (lewa)
        stt_col = GridLayout(cols=1, spacing_y=5)
        for model in self.controller.available_stt_models:
            card = self._create_speech_card(model, "STT")
            stt_col.add_widget(card)

        # Kolumna TTS (prawa)
        tts_col = GridLayout(cols=1, spacing_y=5)
        for model in self.controller.available_tts_models:
            card = self._create_speech_card(model, "TTS")
            tts_col.add_widget(card)

        # Dodajemy oba do głównego gridu
        self.speech_grid.add_widget(stt_col)
        self.speech_grid.add_widget(tts_col)

    def _create_speech_card(self, model: SpeechModelSpec, model_type: str) -> BoxLayout:
        """Tworzy kartę modelu mowy."""
        card = BoxLayout(orientation="vertical", size_hint_y=None, height=70, spacing=3)

        # Nazwa modelu
        name_label = Label(
            text=model.name,
            size_hint_y=None,
            height=20,
            font_size=11,
            bold=True,
        )

        # Specyfikacja
        spec_label = Label(
            text=f"📦 {model.size_mb} MB | 💾 {model.ram_required_mb} MB",
            size_hint_y=None,
            height=16,
            font_size=10,
        )

        # Opis
        desc_label = Label(
            text=model.description[:50] + "..." if len(model.description) > 50 else model.description,
            size_hint_y=None,
            height=16,
            font_size=9,
            color=1,
        )

        card.add_widget(name_label)
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
        self.coolant_label.text = f"Temp. płynu: {t.get('coolant_temp', 0)} °C"
        self.voltage_label.text = f"Napięcie: {t.get('voltage', 0.0):.1f} V"

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

        if not codes:
            self.status_label.text = "Nie wykryto błędów DTC"
            self.urgency_badge.text = "[ Bezpieczna jazda: TAK | Brak błędów ]"
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
        else:
            res = self.controller.confirm_clear_dtc()
            self.clear_btn.text = "🗑️ Skasuj kody błędów DTC"
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
