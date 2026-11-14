import obd


def test_get_dtc_without_hardware():
    class Response:
        value = [("P0300", "Random misfire")]
    class Connection:
        def is_connected(self): return True
        def query(self, _): return Response()
    from core.obd_client import OBDClient
    assert OBDClient(connection=Connection()).get_dtc() == [("P0300", "Random misfire")]
