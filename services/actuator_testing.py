from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ActuatorProtocol(str, Enum):
    """Protokoły diagnostyczne używane do sterowania podzespołami."""

    KWP1281 = "KWP1281"  # VAG K-Line (Funkcja 03 Stellgliedtest / 04 Grundeinstellung)
    KWP2000 = "KWP2000"  # VAG K-Line / ISO 14230
    UDS_2F = "UDS_2F"  # ISO 14229 Service 0x2F (InputOutputControlByIdentifier)
    OBD_MODE_08 = "OBD_MODE_08"  # SAE J1979 Mode 08 (On-board system test)


class ActuatorTestCategory(str, Enum):
    """Kategorie podzespołów wykonawczych."""

    ENGINE = "engine"  # Sterownik silnika (01)
    HVAC = "hvac"  # Klimatyzacja / Climatronic (08)
    INSTRUMENTS = "instruments"  # Zestaw wskaźników / Licznik (17)
    BODY = "body"  # Moduł komfortu / Centralna elektryka (09 / 46)


class ActuatorTestStatus(str, Enum):
    """Status cyklu życia testu podzespołu."""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED_PREFLIGHT = "failed_preflight"
    FAILED_EXECUTION = "failed_execution"


@dataclass
class ActuatorTestDefinition:
    """Definicja testu podzespołu wykonawczego lub nastaw podstawowych."""

    test_id: str
    name: str
    category: ActuatorTestCategory
    target_ecu: str  # np. "01", "08", "17", "7E0"
    protocol: ActuatorProtocol
    start_payload: str  # Hex komendy uruchamiającej
    stop_payload: Optional[str] = None  # Hex komendy zatrzymującej / przywracającej kontrolę
    duration_sec: float = 15.0
    operator_instruction: str = ""
    evaluation_prompt: str = ""
    requires_engine_off: bool = True
    max_speed_kmh: float = 0.0
    min_voltage: float = 12.0
    description: str = ""


@dataclass
class ActuatorTestResult:
    """Wynik wykonania testu podzespołu."""

    test_id: str
    status: ActuatorTestStatus
    message: str
    start_time: float
    end_time: float
    operator_verified: Optional[bool] = None
    telemetry_snapshot: dict[str, Any] = field(default_factory=dict)
    ecu_responses: list[str] = field(default_factory=list)


class ActuatorSafetyPreflight:
    """Weryfikacja twardych warunków bezpieczeństwa przed uruchomieniem testu (AGENTS.md pkt 7)."""

    @staticmethod
    def verify(telemetry: dict[str, Any], test: ActuatorTestDefinition) -> tuple[bool, str]:
        speed = float(telemetry.get("speed", 0.0) or 0.0)
        rpm = int(telemetry.get("rpm", 0) or 0)
        voltage = float(telemetry.get("voltage", 12.4) or 12.4)

        if speed > test.max_speed_kmh:
            return (
                False,
                f"BLOKADA BEZPIECZEŃSTWA: Pojazd jest w ruchu ({speed:.1f} km/h > {test.max_speed_kmh:.1f} km/h). "
                "Test elementów wykonawczych dozwolony wyłącznie na postoju!",
            )

        if test.requires_engine_off and rpm > 50:
            return (
                False,
                f"BLOKADA BEZPIECZEŃSTWA: Silnik pracuje ({rpm} RPM). "
                "Wymagany zgaszony silnik z włączonym zapłonem (Ignition ON, Engine OFF)!",
            )

        if voltage < test.min_voltage:
            return (
                False,
                f"BLOKADA BEZPIECZEŃSTWA: Zbyt niskie napięcie akumulatora ({voltage:.2f} V < {test.min_voltage:.1f} V). "
                "Podłącz ładowarkę lub wyłącz odbiorniki prądu, aby zapobiec zawieszeniu ECU!",
            )

        return True, "Warunki bezpieczeństwa spełnione. Można bezpiecznie uruchomić test."


class ActuatorCatalog:
    """Katalog zdefiniowanych fabrycznie procedur testowych (np. Audi A4 B6 / platforma VAG & OBD-II)."""

    _TESTS: dict[str, ActuatorTestDefinition] = {
        # --- SILNIK (01 - Engine) ---
        "vag_n80_evap": ActuatorTestDefinition(
            test_id="vag_n80_evap",
            name="Zawór N80 odpowietrzania zbiornika paliwa (EVAP)",
            category=ActuatorTestCategory.ENGINE,
            target_ecu="01",
            protocol=ActuatorProtocol.KWP1281,
            start_payload="030101",
            stop_payload="030100",
            duration_sec=15.0,
            operator_instruction="Wsłuchaj się w okolice obudowy filtra powietrza po prawej stronie komory silnika. "
            "Cewka zaworu N80 powinna wydawać głośne, rytmiczne tykanie z częstotliwością ok. 10 Hz.",
            evaluation_prompt="Czy słyszałeś wyraźne, miarowe cykanie elektrozaworu N80?",
            requires_engine_off=True,
            min_voltage=12.0,
            description="Diagnoza zaworu par paliwa EVAP. Nieszczelność lub zacięcie powoduje błędy P0441 i trudny rozruch po tankowaniu.",
        ),
        "vag_n75_wastegate": ActuatorTestDefinition(
            test_id="vag_n75_wastegate",
            name="Zawór N75 sterowania doładowaniem (Wastegate / VNT)",
            category=ActuatorTestCategory.ENGINE,
            target_ecu="01",
            protocol=ActuatorProtocol.KWP1281,
            start_payload="030102",
            stop_payload="030100",
            duration_sec=18.0,
            operator_instruction="Obserwuj sztangę podciśnieniową przy turbosprężarce. "
            "Zawór cyklicznie załącza podciśnienie — sztanga powinna płynnie skakać w zakresie ok. 10–12 mm.",
            evaluation_prompt="Czy sztanga turbiny poruszała się płynnie w pełnym skoku bez przycinania?",
            requires_engine_off=True,
            min_voltage=12.0,
            description="Weryfikacja zaworu N75 i geometrii VNT / klapy wastegate celem eliminacji trybu awaryjnego (Notlauf / P0299 / P0234).",
        ),
        "vag_j17_fuel_pump": ActuatorTestDefinition(
            test_id="vag_j17_fuel_pump",
            name="Przekaźnik pompy paliwa J17 / Pompa zbiornika",
            category=ActuatorTestCategory.ENGINE,
            target_ecu="01",
            protocol=ActuatorProtocol.KWP1281,
            start_payload="030103",
            stop_payload="030100",
            duration_sec=12.0,
            operator_instruction="Wsłuchaj się w szum elektrycznej pompy paliwa pod tylną kanapą i sprawdź ciśnienie w układzie zasilania.",
            evaluation_prompt="Czy elektryczna pompa paliwa załączyła się i tłoczyła paliwo stabilnie?",
            requires_engine_off=True,
            min_voltage=12.0,
            description="Test ciągłości obwodu przekaźnika J17 i silnika pompy paliwa bez konieczności kręcenia rozrusznikiem.",
        ),
        "vag_radiator_fans": ActuatorTestDefinition(
            test_id="vag_radiator_fans",
            name="Wentylatory chłodnicy V7 / V177 (Bieg 1 i 2)",
            category=ActuatorTestCategory.ENGINE,
            target_ecu="01",
            protocol=ActuatorProtocol.KWP1281,
            start_payload="030104",
            stop_payload="030100",
            duration_sec=16.0,
            operator_instruction="Obserwuj oba wentylatory za chłodnicą w pasie przednim. Powinny załączyć się kolejno na biegu wolnym i szybkim.",
            evaluation_prompt="Czy oba wentylatory obracały się bez bicia i niepożądanych dźwięków?",
            requires_engine_off=True,
            min_voltage=12.0,
            description="Weryfikacja modułu sterownika wentylatorów chłodnicy oraz opornic pierwszego biegu.",
        ),
        "vag_n205_camshaft": ActuatorTestDefinition(
            test_id="vag_n205_camshaft",
            name="Zawór regulacji faz rozrządu N205",
            category=ActuatorTestCategory.ENGINE,
            target_ecu="01",
            protocol=ActuatorProtocol.KWP1281,
            start_payload="030105",
            stop_payload="030100",
            duration_sec=10.0,
            operator_instruction="Wsłuchaj się w klikanie elektrozaworu fazatora umieszczonego z tyłu pokrywy zaworów.",
            evaluation_prompt="Czy zawór N205 reagował kliknięciem na impulsy sterownika?",
            requires_engine_off=True,
            min_voltage=12.0,
            description="Sprawdzenie cewki nastawnika wałka rozrządu w silnikach 1.8T / 2.0 / 3.0 V6.",
        ),
        # --- CLIMATRONIC (08 - Auto HVAC) ---
        "vag_hvac_v2_blower": ActuatorTestDefinition(
            test_id="vag_hvac_v2_blower",
            name="Dmuchawa nawiewu V2 (Płynna regulacja obrotów)",
            category=ActuatorTestCategory.HVAC,
            target_ecu="08",
            protocol=ActuatorProtocol.KWP1281,
            start_payload="030801",
            stop_payload="030800",
            duration_sec=15.0,
            operator_instruction="Wsłuchaj się w nawiew w kabinie. Dmuchawa V2 powinna płynnie zwiększać prędkość od 0% do 100%, a następnie zwolnić.",
            evaluation_prompt="Czy dmuchawa osiągnęła pełną wydajność bez pisków i wibracji łożysk?",
            requires_engine_off=True,
            min_voltage=12.0,
            description="Weryfikacja silnika dmuchawy oraz elektronicznego rezystora (jeża / sterownika nawiewu).",
        ),
        "vag_hvac_v70_central_flap": ActuatorTestDefinition(
            test_id="vag_hvac_v70_central_flap",
            name="Silnik klapy centralnej V70 (Potencjometr G92)",
            category=ActuatorTestCategory.HVAC,
            target_ecu="08",
            protocol=ActuatorProtocol.KWP1281,
            start_payload="030802",
            stop_payload="030800",
            duration_sec=18.0,
            operator_instruction="Sprawdź przepływ powietrza z nawiewów centralnych na środku deski rozdzielczej podczas pełnego cyklu otwarcia i zamknięcia.",
            evaluation_prompt="Czy klapa centralna V70 przestawiła się płynnie w obie skrajne pozycje?",
            requires_engine_off=True,
            min_voltage=12.0,
            description="Typowa bolączka Audi A4 B6: wyrobione zębatki silniczka V70 lub zabrudzony potencjometr G92.",
        ),
        "vag_hvac_v68_temp_flap": ActuatorTestDefinition(
            test_id="vag_hvac_v68_temp_flap",
            name="Silnik klapy regulacji temperatury V68 (Potencjometr G112)",
            category=ActuatorTestCategory.HVAC,
            target_ecu="08",
            protocol=ActuatorProtocol.KWP1281,
            start_payload="030803",
            stop_payload="030800",
            duration_sec=18.0,
            operator_instruction="Obserwuj temperaturę z kratek nawiewu (od skrajnego zimna do pełnego gorąca). Silniczek znajduje się za schowkiem pasażera.",
            evaluation_prompt="Czy silnik klapy V68 przemieścił się bez charakterystycznego terkotania zębatek?",
            requires_engine_off=True,
            min_voltage=12.0,
            description="Sprawdzenie klapy mieszalnika ciepło/zimno. Uszkodzenie objawia się brakiem grzania lub ciągłym gorącym powietrzem.",
        ),
        "vag_hvac_v71_recirc_flap": ActuatorTestDefinition(
            test_id="vag_hvac_v71_recirc_flap",
            name="Silnik klapy spiętrzania / obiegu zamkniętego V71 (G113)",
            category=ActuatorTestCategory.HVAC,
            target_ecu="08",
            protocol=ActuatorProtocol.KWP1281,
            start_payload="030804",
            stop_payload="030800",
            duration_sec=18.0,
            operator_instruction="Zdejmij osłonę podszybia / filtra kabinowego lub posłuchaj zmiany dźwięku powietrza w kabinie przy zamknięciu obiegu.",
            evaluation_prompt="Czy klapa V71 zamknęła i otworzyła obieg świeżego powietrza?",
            requires_engine_off=True,
            min_voltage=12.0,
            description="Diagnoza silniczka klapy recyrkulacji. Uszkodzenie powoduje parowanie szyb w deszczowe dni (kod błędu 00604).",
        ),
        "vag_hvac_v85_footwell_flap": ActuatorTestDefinition(
            test_id="vag_hvac_v85_footwell_flap",
            name="Silnik klapy nawiewu na nogi / odmrażania V85 (G114)",
            category=ActuatorTestCategory.HVAC,
            target_ecu="08",
            protocol=ActuatorProtocol.KWP1281,
            start_payload="030805",
            stop_payload="030800",
            duration_sec=18.0,
            operator_instruction="Przyłóż dłoń do wylotów w przestrzeni nóg kierowcy oraz kratek odmrażania przedniej szyby.",
            evaluation_prompt="Czy strumień powietrza przełączył się w pełni na strefę nóg?",
            requires_engine_off=True,
            min_voltage=12.0,
            description="Test klapy sterującej podziałem powietrza dół/góra w zespole nagrzewnicy.",
        ),
        "vag_hvac_basic_settings_001": ActuatorTestDefinition(
            test_id="vag_hvac_basic_settings_001",
            name="Nastawy podstawowe Climatronic (Adaptacja klap - Grupa 001)",
            category=ActuatorTestCategory.HVAC,
            target_ecu="08",
            protocol=ActuatorProtocol.KWP1281,
            start_payload="040801",
            stop_payload="040800",
            duration_sec=30.0,
            operator_instruction="Nie dotykaj panelu klimatyzacji! Sterownik automatycznie przemieści wszystkie silniczki klap od skrajności do skrajności, "
            "aby skalibrować wartości graniczne potencjometrów. Procedura trwa ok. 25–30 sekund.",
            evaluation_prompt="Czy wszystkie 4 pola wartości powróciły do stanu 0 (kalibracja zakończona sukcesem)?",
            requires_engine_off=True,
            min_voltage=12.2,
            description="Pełna adaptacja nastaw podstawowych VCDS/Ross-Tech dla modułu 08 Auto HVAC po wymianie silniczków lub akumulatora.",
        ),
        # --- ZESTAW WSKAŹNIKÓW (17 - Instruments) ---
        "vag_kombi_needle_sweep": ActuatorTestDefinition(
            test_id="vag_kombi_needle_sweep",
            name="Test zegarów i kontrolek (Kombiinstrument Needle Sweep)",
            category=ActuatorTestCategory.INSTRUMENTS,
            target_ecu="17",
            protocol=ActuatorProtocol.KWP1281,
            start_payload="031701",
            stop_payload="031700",
            duration_sec=15.0,
            operator_instruction="Obserwuj zegary: wskazówki obrotomierza, prędkościomierza, temperatury i paliwa wychylą się na 100%, "
            "a następnie zatrzymają dokładnie pośrodku (3000 RPM, 100 km/h, 90°C, 1/2 zbiornika). Nastąpi też test brzęczyka i kontrolek.",
            evaluation_prompt="Czy wszystkie wskazówki zatrzymały się idealnie w pionowych pozycjach środkowych?",
            requires_engine_off=True,
            min_voltage=12.0,
            description="Weryfikacja silniczków krokowych wskaźników szafy (np. liczniki Jaeger / Bosch RB4 / RB8 w Audi A4 B6).",
        ),
        # --- UNIWERSALNE OBD-II / UDS ---
        "obd_mode08_evap_leak": ActuatorTestDefinition(
            test_id="obd_mode08_evap_leak",
            name="Uniwersalny test szczelności EVAP (OBD-II Mode 08 PID 01)",
            category=ActuatorTestCategory.ENGINE,
            target_ecu="7E0",
            protocol=ActuatorProtocol.OBD_MODE_08,
            start_payload="0801",
            stop_payload="0800",
            duration_sec=20.0,
            operator_instruction="Sterownik silnika zamyka zawór odpowietrzania i wytwarza podciśnienie celem kontroli szczelności oparów paliwa.",
            evaluation_prompt="Czy test szczelności EVAP zakończył się bez zgłoszenia błędu wycieku?",
            requires_engine_off=True,
            min_voltage=12.0,
            description="Standardowy test diagnostyczny Mode 08 SAE J1979 zgodny z normami emisji EOBD.",
        ),
        "uds_radiator_fan_low": ActuatorTestDefinition(
            test_id="uds_radiator_fan_low",
            name="Sterowanie wentylatorem chłodnicy (UDS Service 0x2F)",
            category=ActuatorTestCategory.ENGINE,
            target_ecu="7E0",
            protocol=ActuatorProtocol.UDS_2F,
            start_payload="2F04500332",  # Service 0x2F, Identifier 0x0450, Short Term Adjust, 50%
            stop_payload="2F045000",  # Return Control to ECU
            duration_sec=12.0,
            operator_instruction="Sterownik UDS wysterowuje wentylator na 50% mocy PWM. Obserwuj obroty wirnika chłodnicy.",
            evaluation_prompt="Czy wentylator chłodnicy obracał się z zadaną prędkością?",
            requires_engine_off=True,
            min_voltage=12.0,
            description="Nowoczesne sterowanie podzespołem według normy ISO 14229 Service 0x2F.",
        ),
    }

    @classmethod
    def list_tests(cls, category: Optional[ActuatorTestCategory] = None) -> list[ActuatorTestDefinition]:
        """Zwraca listę dostępnych testów podzespołów, opcjonalnie przefiltrowaną po kategorii."""
        tests = list(cls._TESTS.values())
        if category is not None:
            tests = [t for t in tests if t.category == category]
        return tests

    @classmethod
    def get_test(cls, test_id: str) -> Optional[ActuatorTestDefinition]:
        """Pobiera definicję testu po unikalnym identyfikatorze."""
        return cls._TESTS.get(test_id)

    @classmethod
    def register_test(cls, test: ActuatorTestDefinition) -> None:
        """Pozwala na dynamiczne rozszerzenie katalogu o dodatkowy test."""
        cls._TESTS[test.test_id] = test


class ActuatorTestRunner:
    """Orkiestrator procedur testowania podzespołów z obsługą watchdog timeoutu i audytu."""

    def __init__(
        self,
        obd_client: Optional[Any] = None,
        telemetry_logger: Optional[Any] = None,
        mock_mode: bool = False,
    ):
        self.obd_client = obd_client
        self.telemetry_logger = telemetry_logger
        self.mock_mode = mock_mode

        self._active_test: Optional[ActuatorTestDefinition] = None
        self._current_status: ActuatorTestStatus = ActuatorTestStatus.IDLE
        self._test_start_time: float = 0.0
        self._test_end_time: float = 0.0
        self._last_result: Optional[ActuatorTestResult] = None
        self._ecu_responses: list[str] = []

    @property
    def is_running(self) -> bool:
        return self._current_status == ActuatorTestStatus.RUNNING

    @property
    def active_test(self) -> Optional[ActuatorTestDefinition]:
        return self._active_test

    @property
    def last_result(self) -> Optional[ActuatorTestResult]:
        return self._last_result

    def start_test(
        self,
        test_id: str,
        current_telemetry: dict[str, Any],
        now: Optional[float] = None,
    ) -> ActuatorTestResult:
        """Uruchamia test podzespołu po pozytywnej weryfikacji warunków wstępnych (Pre-flight)."""
        current_time = now if now is not None else time.time()
        test = ActuatorCatalog.get_test(test_id)
        if not test:
            result = ActuatorTestResult(
                test_id=test_id,
                status=ActuatorTestStatus.FAILED_PREFLIGHT,
                message=f"Błąd: Nie znaleziono testu o identyfikatorze '{test_id}'.",
                start_time=current_time,
                end_time=current_time,
                telemetry_snapshot=dict(current_telemetry),
            )
            self._last_result = result
            return result

        if self.is_running:
            result = ActuatorTestResult(
                test_id=test_id,
                status=ActuatorTestStatus.FAILED_PREFLIGHT,
                message=f"Błąd: Inny test ('{self._active_test.test_id}') jest obecnie w trakcie wykonywania. "
                "Zatrzymaj go przed uruchomieniem kolejnego!",
                start_time=current_time,
                end_time=current_time,
                telemetry_snapshot=dict(current_telemetry),
            )
            self._last_result = result
            return result

        # 1. Weryfikacja bezpieczeństwa (Pre-flight)
        is_safe, preflight_msg = ActuatorSafetyPreflight.verify(current_telemetry, test)
        if not is_safe:
            result = ActuatorTestResult(
                test_id=test.test_id,
                status=ActuatorTestStatus.FAILED_PREFLIGHT,
                message=preflight_msg,
                start_time=current_time,
                end_time=current_time,
                telemetry_snapshot=dict(current_telemetry),
            )
            self._last_result = result
            self._log_event("actuator_preflight_rejected", test.test_id, preflight_msg)
            return result

        # 2. Wysłanie komendy diagnostycznej do ECU
        self._active_test = test
        self._current_status = ActuatorTestStatus.RUNNING
        self._test_start_time = current_time
        self._ecu_responses = []

        response = self._send_ecu_command(test.start_payload, ecu=test.target_ecu)
        self._ecu_responses.append(response)

        result = ActuatorTestResult(
            test_id=test.test_id,
            status=ActuatorTestStatus.RUNNING,
            message=f"Test '{test.name}' uruchomiony pomyślnie. {test.operator_instruction}",
            start_time=current_time,
            end_time=0.0,
            telemetry_snapshot=dict(current_telemetry),
            ecu_responses=list(self._ecu_responses),
        )
        self._last_result = result
        self._log_event("actuator_test_started", test.test_id, f"Start testu {test.name}")
        return result

    def update_progress(
        self,
        current_telemetry: dict[str, Any],
        now: Optional[float] = None,
    ) -> ActuatorTestResult:
        """Monitoruje stan pracującego testu, weryfikuje warunki w czasie rzeczywistym i egzekwuje watchdog timeout."""
        current_time = now if now is not None else time.time()
        if not self.is_running or self._active_test is None:
            return self._last_result or ActuatorTestResult(
                test_id="",
                status=ActuatorTestStatus.IDLE,
                message="Brak aktywnego testu.",
                start_time=0.0,
                end_time=0.0,
            )

        test = self._active_test

        # 1. Sprawdzenie naruszenia bezpieczeństwa w trakcie testu (np. ruszenie pojazdem lub rozruch)
        speed = float(current_telemetry.get("speed", 0.0) or 0.0)
        rpm = int(current_telemetry.get("rpm", 0) or 0)

        if speed > test.max_speed_kmh or (test.requires_engine_off and rpm > 50):
            abort_reason = (
                f"AWARYJNE PRZERWANIE TESTU: Wykryto zmianę stanu pojazdu (speed={speed} km/h, rpm={rpm} RPM). "
                "Sterowanie natychmiast zwrócone do ECU!"
            )
            return self.abort_test(reason=abort_reason, current_telemetry=current_telemetry, now=current_time)

        # 2. Watchdog Timeout — automatyczne zakończenie po upływie zadanego czasu
        elapsed = current_time - self._test_start_time
        if elapsed >= test.duration_sec:
            # Wysłanie komendy stop / reset do ECU
            if test.stop_payload:
                stop_res = self._send_ecu_command(test.stop_payload, ecu=test.target_ecu)
                self._ecu_responses.append(stop_res)

            self._current_status = ActuatorTestStatus.COMPLETED
            self._test_end_time = current_time

            result = ActuatorTestResult(
                test_id=test.test_id,
                status=ActuatorTestStatus.COMPLETED,
                message=f"Test '{test.name}' zakończony pomyślnie po {elapsed:.1f} s. {test.evaluation_prompt}",
                start_time=self._test_start_time,
                end_time=self._test_end_time,
                telemetry_snapshot=dict(current_telemetry),
                ecu_responses=list(self._ecu_responses),
            )
            self._last_result = result
            self._log_event("actuator_test_completed", test.test_id, f"Czas trwania: {elapsed:.1f}s")
            self._active_test = None
            return result

        # W trakcie wykonywania
        result = ActuatorTestResult(
            test_id=test.test_id,
            status=ActuatorTestStatus.RUNNING,
            message=f"Test w toku ({elapsed:.1f}/{test.duration_sec:.1f} s)... {test.operator_instruction}",
            start_time=self._test_start_time,
            end_time=0.0,
            telemetry_snapshot=dict(current_telemetry),
            ecu_responses=list(self._ecu_responses),
        )
        self._last_result = result
        return result

    def abort_test(
        self,
        reason: str = "Przerwano ręcznie przez operatora (Emergency Abort).",
        current_telemetry: Optional[dict[str, Any]] = None,
        now: Optional[float] = None,
    ) -> ActuatorTestResult:
        """Natychmiastowe przerwanie testu i wysłanie ramki przywracającej kontrolę ECU."""
        current_time = now if now is not None else time.time()
        if not self.is_running or self._active_test is None:
            return ActuatorTestResult(
                test_id="",
                status=ActuatorTestStatus.IDLE,
                message="Brak aktywnego testu do przerwania.",
                start_time=0.0,
                end_time=current_time,
            )

        test = self._active_test

        # Natychmiastowe wysłanie ramki resetującej sterowanie
        if test.stop_payload:
            stop_res = self._send_ecu_command(test.stop_payload, ecu=test.target_ecu)
            self._ecu_responses.append(stop_res)

        self._current_status = ActuatorTestStatus.ABORTED
        self._test_end_time = current_time

        telemetry = dict(current_telemetry) if current_telemetry is not None else {}
        result = ActuatorTestResult(
            test_id=test.test_id,
            status=ActuatorTestStatus.ABORTED,
            message=reason,
            start_time=self._test_start_time,
            end_time=self._test_end_time,
            telemetry_snapshot=telemetry,
            ecu_responses=list(self._ecu_responses),
        )
        self._last_result = result
        self._log_event("actuator_test_aborted", test.test_id, reason)
        self._active_test = None
        return result

    def record_operator_feedback(
        self,
        test_id: str,
        passed: bool,
        notes: str = "",
    ) -> Optional[ActuatorTestResult]:
        """Zapisuje subiektywną weryfikację mechanika/operatora po teście podzespołu."""
        if self._last_result and self._last_result.test_id == test_id:
            self._last_result.operator_verified = passed
            status_text = "POZYTYWNY (Potwierdzono działanie)" if passed else "NEGATYWNY (Brak reakcji/usterka)"
            self._log_event(
                "actuator_operator_feedback",
                test_id,
                f"Wynik operatora: {status_text}. Notatki: {notes}",
            )
            return self._last_result
        return None

    def _send_ecu_command(self, payload: str, ecu: str = "01") -> str:
        """Wysyła polecenie diagnostyczne do ECU lub symuluje odpowiedź w środowisku testowym."""
        if self.mock_mode or self.obd_client is None or not getattr(self.obd_client, "is_connected", lambda: False)():
            # Zwróć syntetyczną pozytywną odpowiedź diagnostyczną (np. 6F lub 43 lub OK)
            return f"SIMULATED_ACK_{ecu}_{payload}"

        try:
            # W środowisku rzeczywistym wysyłamy bezpośrednią ramkę przez connection
            conn = getattr(self.obd_client, "connection", None)
            if conn and hasattr(conn, "send"):
                return str(conn.send(payload))
            return f"ACK_{payload}"
        except Exception as e:
            return f"ERR_{str(e)}"

    def _log_event(self, event_type: str, test_id: str, details: str) -> None:
        """Loguje zdarzenie do TelemetryLogger jeśli jest dostępny."""
        if self.telemetry_logger and hasattr(self.telemetry_logger, "log_audit_event"):
            try:
                self.telemetry_logger.log_audit_event(
                    event_type=event_type,
                    details=f"[{test_id}] {details}",
                )
            except Exception:
                pass
