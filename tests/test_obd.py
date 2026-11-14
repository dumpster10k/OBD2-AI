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


def test_get_dtc_without_hardware():
    assert OBDClient(connection=Connection()).get_dtc() == [("P0300", "Random misfire")]


def test_clear_dtc():
    assert OBDClient(connection=Connection()).clear_dtc() is True


def test_disconnected_client_is_safe():
    client = OBDClient(connection=DisconnectedConnection())
    assert client.is_connected() is False
    assert client.get_dtc() == []
    assert client.clear_dtc() is False
