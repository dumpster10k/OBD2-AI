from core.obd_client import OBDClient


class Response:
    value = [("P0300", "Random misfire")]

    def was_successful(self):
        return True


class Connection:
    def is_connected(self):
        return True

    def query(self, _):
        return Response()


class DisconnectedConnection:
    def is_connected(self):
        return False


class MockMagnitudeValue:
    def __init__(self, magnitude):
        self.magnitude = magnitude


class MockTelemetryResponse:
    def __init__(self, value):
        self.value = value


class MockTelemetryConnection:
    def __init__(self, rpm=2400, speed=65, coolant=92, voltage=14.2):
        self.rpm = rpm
        self.speed = speed
        self.coolant = coolant
        self.voltage = voltage

    def is_connected(self):
        return True

    def query(self, cmd):
        name = getattr(cmd, "name", "")
        if "RPM" in name:
            return MockTelemetryResponse(MockMagnitudeValue(self.rpm))
        elif "SPEED" in name:
            return MockTelemetryResponse(MockMagnitudeValue(self.speed))
        elif "COOLANT" in name:
            return MockTelemetryResponse(MockMagnitudeValue(self.coolant))
        elif "VOLTAGE" in name:
            return MockTelemetryResponse(MockMagnitudeValue(self.voltage))
        return None


class FailingTelemetryConnection:
    def is_connected(self):
        return True

    def query(self, _):
        raise RuntimeError("ECU Communication Timeout")


def test_get_dtc_without_hardware():
    assert OBDClient(connection=Connection()).get_dtc() == [("P0300", "Random misfire")]


def test_clear_dtc():
    assert OBDClient(connection=Connection()).clear_dtc() is True


def test_disconnected_client_is_safe():
    client = OBDClient(connection=DisconnectedConnection())
    assert client.is_connected() is False
    assert client.get_dtc() == []
    assert client.clear_dtc() is False


def test_get_telemetry_disconnected():
    client = OBDClient(connection=DisconnectedConnection())
    telemetry = client.get_telemetry()
    assert telemetry == {
        "rpm": 0,
        "speed": 0,
        "coolant_temp": 0,
        "voltage": 0.0,
    }


def test_get_telemetry_connected():
    client = OBDClient(connection=MockTelemetryConnection(rpm=3100, speed=90, coolant=88, voltage=13.8))
    telemetry = client.get_telemetry()
    assert telemetry["rpm"] == 3100
    assert telemetry["speed"] == 90
    assert telemetry["coolant_temp"] == 88
    assert abs(telemetry["voltage"] - 13.8) < 1e-4


def test_get_telemetry_with_failing_queries():
    client = OBDClient(connection=FailingTelemetryConnection())
    telemetry = client.get_telemetry()
    # Fallback default values
    assert telemetry["rpm"] == 0
    assert telemetry["speed"] == 0
    assert telemetry["coolant_temp"] == 0
    assert telemetry["voltage"] == 12.6
