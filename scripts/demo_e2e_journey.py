#!/usr/bin/env python3
"""demo_e2e_journey.py — Interaktywny pokaz podróży użytkownika End-to-End w aplikacji OBD2-AI.

Prezentuje przejście przez wszystkie ekrany aplikacji w stylu Car Scanner,
auto-profilowanie pojazdu, telemetrię na żywo, asystenta głosowego oraz diagnozę AI.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ustalenie katalogu głównego projektu
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.obd_client import OBDClient
from services.ai_engine import AIEngine
from services.llm_engine import RECOMMENDED_LLM_MODELS
from services.model_downloader import ModelDownloader
from services.telemetry_logger import TelemetryLogger
from tests.test_e2e_journey import E2EFakeOBDConnection
from ui.main import CarDoctorUI, DashboardController

# Kolory ANSI do estetycznej prezentacji w konsoli
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_MAGENTA = "\033[95m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"


def print_step(title: str, subtitle: str = ""):
    print(f"\n{C_CYAN}{C_BOLD}{'=' * 72}{C_RESET}")
    print(f"{C_CYAN}{C_BOLD}▶ {title}{C_RESET}")
    if subtitle:
        print(f"  {C_MAGENTA}{subtitle}{C_RESET}")
    print(f"{C_CYAN}{C_BOLD}{'=' * 72}{C_RESET}")


def run_demo():
    print(f"\n{C_GREEN}{C_BOLD}🏎️  AI CAR DOCTOR — POKAZ PODRÓŻY UŻYTKOWNIKA END-TO-END (E2E){C_RESET}")
    print("Modułowy interfejs w stylu Car Scanner ELM OBD2, auto-profilowanie i asystent AI.\n")

    # 1. Inicjalizacja
    print_step(
        "KROK 1: Start aplikacji i inicjalizacja kontrolera",
        "Uruchomienie DashboardController i interfejsu CarDoctorUI",
    )
    fake_conn = E2EFakeOBDConnection(
        dtc=[],
        rpm=850,
        speed=0,
        coolant=88,
        voltage=14.2,
        vin="WAUZZZ8E34A123456",
        ecu_name="EDC15P 1.9 TDI 038906019FP",
    )
    obd_client = OBDClient(connection=fake_conn)
    telemetry_logger = TelemetryLogger(db_path=":memory:")
    ai_engine = AIEngine()
    downloader = ModelDownloader(target_dir="./models")
    controller = DashboardController(
        obd_client=obd_client,
        ai_engine=ai_engine,
        telemetry_logger=telemetry_logger,
        model_downloader=downloader,
    )
    ui = CarDoctorUI(controller=controller)
    print(f"✅ {C_GREEN}Zainicjalizowano CarDoctorUI pomyślnie.{C_RESET}")
    print(f"   Domyślna zakładka: {C_BOLD}{ui.active_tab}{C_RESET}")
    print(f"   Pasek górny: {ui.bar_obd_status.text} | {ui.bar_vehicle_profile.text} | {ui.bar_voltage.text}")

    # 2. Zakładka Ustawienia i wybór modeli
    print_step("KROK 2: Przejście do zakładki ⚙️ USTAWIENIA", "Wybór modelu AI LLM, modelu mowy i profilu adaptera")
    ui.set_active_tab("settings")
    print(f"   Aktywna zakładka: {C_BOLD}{ui.active_tab}{C_RESET}")

    # Wybór modelu AI
    qwen_model = RECOMMENDED_LLM_MODELS.get("qwen2.5-0.5b", list(RECOMMENDED_LLM_MODELS.values())[0])
    controller.on_model_select(qwen_model)
    print(f"   Wybrano model LLM: {C_GREEN}{controller.current_model_spec.name}{C_RESET}")

    # Wybór profilu połączenia
    ui.on_select_connection_profile("mobile_bt")
    print(f"   Wybrano profil adaptera: {C_CYAN}{ui.connection_status_label.text}{C_RESET}")

    # 3. Połączenie OBD i auto-profilowanie pojazdu
    print_step(
        "KROK 3: Połączenie z adapterem ELM327 i auto-detekcja pojazdu",
        "Odczyt VIN i ECU ID, powiązanie dedykowanych sensorów",
    )
    controller.obd.connect = lambda **kwargs: setattr(controller.obd, "connection", fake_conn) or True
    ui.on_connect_obd()
    print(f"   Status połączenia: {C_GREEN}{ui.connection_status_label.text}{C_RESET}")
    if controller.vehicle_profile:
        print(
            f"   🚗 Wykryto pojazd: {C_BOLD}{controller.vehicle_profile.brand} {controller.vehicle_profile.model} {controller.vehicle_profile.generation}{C_RESET}"
        )
        print(
            f"   🔧 Silnik / ECU: {C_BOLD}{controller.vehicle_profile.engine_name} ({controller.vehicle_profile.ecu_family}){C_RESET}"
        )
        print(f"   📊 Aktywne sensory dedykowane: {len(controller.vehicle_profile.active_sensor_names)} parametrów")

    # Aktualizacja telemetrii
    ui.update_telemetry_ui()
    print(
        f"   Pasek górny po połączeniu: {C_GREEN}{ui.bar_obd_status.text}{C_RESET} | {ui.bar_vehicle_profile.text} | {ui.bar_voltage.text}"
    )

    # 4. Pulpit i telemetria podczas jazdy
    print_step(
        "KROK 4: Powrót do zakładki 🏎️ PULPIT (Dashboard)",
        "Symulacja jazdy, odczyt wskaźników z Min/Max i zegara Dial Gauge",
    )
    ui.set_active_tab("dashboard")

    # Symulacja parametrów jazdy
    fake_conn.rpm = 2350
    fake_conn.speed = 82
    fake_conn.coolant = 91
    fake_conn.voltage = 14.1
    ui.on_refresh_telemetry()

    print(f"   [{C_CYAN}{ui.rpm_label.text}{C_RESET}] -> {ui.rpm_min_max_label.text}")
    print(f"   [{C_CYAN}{ui.speed_label.text}{C_RESET}] -> {ui.speed_min_max_label.text}")
    print(f"   [{C_GREEN}{ui.coolant_label.text}{C_RESET}] -> {ui.coolant_min_max_label.text}")
    print(f"   [{C_GREEN}{ui.voltage_label.text}{C_RESET}] -> {ui.voltage_min_max_label.text}")
    print(
        f"   ⏱️ Zegar Dial Gauge: {ui.dial_rpm.value_label.text} ({ui.dial_rpm.status_badge.text}, kąt: {ui.dial_rpm.gauge_angle}°)"
    )

    # 5. Zakładka Wszystkie sensory
    print_step("KROK 5: Przejście do zakładki 📊 WSZYSTKIE SENSORY", "Wyszukiwanie i filtrowanie PID-ów na żywo")
    ui.set_active_tab("all_sensors")
    print(f"   Liczba widocznych kart sensorów: {len(ui.all_sensors_grid.children)}")

    # Filtrowanie
    query = "010C"
    ui.sensor_search_input.text = query
    ui.on_sensor_search_change(ui.sensor_search_input, query)
    print(f"   Wynik wyszukiwania '{query}': {len(ui.all_sensors_grid.children)} dopasowań.")

    # 6. Zakładka Wykresy
    print_step("KROK 6: Przejście do zakładki 📈 WYKRESY (Charts)", "Wykres trendu czasowego i statystyki serii próbek")
    ui.set_active_tab("charts")
    ui.chart.set_metric("coolant_temp")
    print(f"   Aktywny wykres: {ui.chart.chart_title.text}")
    print(f"   Statystyki: {ui.chart.stats_label.text}")

    # 7. Symulacja usterki i diagnoza AI
    print_step(
        "KROK 7: Wystąpienie usterki i analiza diagnostyczna AI",
        "Symulacja przegrzania (P0217) i naturalne wyjaśnienie przez AI",
    )
    ui.set_active_tab("dashboard")
    ui.on_toggle_simulation()
    ui.on_select_scenario("overheat")

    ui.set_active_tab("diagnostics")
    print(f"   Status AI: {C_RED}{ui.urgency_badge.text}{C_RESET}")
    print(f"   Podsumowanie usterki:\n   {C_YELLOW}{ui.report_summary_label.text[:220]}...{C_RESET}")

    # 8. Asystent głosowy Hands-Free
    print_step("KROK 8: Asystent głosowy kierowcy (Hands-Free)", "Pytania kierowcy i natychmiastowa odpowiedź głosowa")
    print("   🎙️ Pytanie 1: 'Jaka jest temperatura płynu chłodzącego?'")
    ui.on_quick_voice_command("Jaka jest temperatura płynu chłodzącego?")
    print(f"   🗣️ Odpowiedź: {C_GREEN}{ui.voice_response_label.text}{C_RESET}")

    print("\n   🎙️ Pytanie 2: 'Czy mogę bezpiecznie jechać dalej?'")
    ui.voice_custom_input.text = "Czy mogę bezpiecznie kontynuować podróż?"
    ui.on_send_custom_voice_query()
    print(f"   🗣️ Odpowiedź: {C_RED}{ui.voice_response_label.text}{C_RESET}")

    # 9. Bezpieczne kasowanie błędów na postoju
    print_step(
        "KROK 9: Bezpieczne dwuetapowe kasowanie błędów DTC na postoju",
        "Zatrzymanie pojazdu, potwierdzenie procedury i weryfikacja",
    )
    # Próba w ruchu
    print("   Próba kasowania w ruchu (blokada bezpieczeństwa):")
    ui.on_clear_dtc()
    print(f"   Status blokady: {C_RED}{ui.status_label.text}{C_RESET}")

    # Zatrzymanie pojazdu
    ui.on_toggle_simulation()
    fake_conn.speed = 0
    fake_conn.dtc = ["P0217"]
    controller.refresh_telemetry()

    print("\n   Próba 1 na postoju (kliknięcie 'Skasuj'):")
    ui.on_clear_dtc()
    print(f"   Stan przycisku: {C_YELLOW}{ui.clear_btn.text}{C_RESET}")

    print("\n   Próba 2 na postoju (potwierdzenie kasowania):")
    ui.on_clear_dtc()
    print(f"   Wynik: {C_GREEN}{ui.status_label.text}{C_RESET}")

    ui.on_scan_errors()
    print(f"   Stan po ponownym skanie: {C_GREEN}{ui.status_label.text}{C_RESET}")

    # 10. Responsywny layout (Obrót ekranu)
    print_step(
        "KROK 10: Responsywność ekranu (Obrót Landscape HUD vs Portrait)",
        "Dopasowanie kolumn wskaźników do uchwytu w samochodzie",
    )
    # Poziom
    ui.apply_responsive_layout(1024, 600)
    print(
        f"   Obrót do poziomu (1024x600): {C_BOLD}Landscape={ui.is_landscape}{C_RESET} | Kafelki cols={ui.grid_telemetry.cols} (1 rząd) | Zakładki cols={ui.tab_nav_bar.cols}"
    )
    # Pion
    ui.apply_responsive_layout(390, 844)
    print(
        f"   Obrót do pionu (390x844):     {C_BOLD}Landscape={ui.is_landscape}{C_RESET} | Kafelki cols={ui.grid_telemetry.cols} (2 kolumny) | Zakładki cols={ui.tab_nav_bar.cols} (2 rzędy)"
    )

    print(f"\n{C_GREEN}{C_BOLD}{'=' * 72}{C_RESET}")
    print(f"{C_GREEN}{C_BOLD}✅ PEŁNA PODRÓŻ END-TO-END ZAKOŃCZONA POMYŚLNIE!{C_RESET}")
    print(f"{C_GREEN}{C_BOLD}{'=' * 72}{C_RESET}\n")


if __name__ == "__main__":
    run_demo()
