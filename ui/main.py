from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from core.obd_client import OBDClient
from services.ai_engine import AIEngine


class CarDoctorUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.obd = OBDClient()
        self.ai = AIEngine()
        self.status = Label(text="AI Car Doctor — gotowy")
        self.add_widget(self.status)
        scan = Button(text="Skanuj błędy OBD")
        scan.bind(on_press=self.scan_errors)
        self.add_widget(scan)

    def scan_errors(self, _button):
        codes = self.obd.get_dtc()
        self.status.text = "Nie wykryto błędów lub brak połączenia" if not codes else str(codes)


class AIDoctorApp(App):
    def build(self):
        return CarDoctorUI()


if __name__ == "__main__":
    AIDoctorApp().run()
