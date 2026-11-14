import obd


class OBDClient:
    def __init__(self, port=None, connection=None):
        self.connection = connection
        if connection is None:
            try:
                self.connection = obd.OBD(port)
            except Exception:
                self.connection = None

    def is_connected(self):
        return self.connection is not None and self.connection.is_connected()

    def get_dtc(self):
        if not self.is_connected():
            return []
        return self.connection.query(obd.commands.GET_DTC).value or []

    def clear_dtc(self):
        if not self.is_connected():
            return False
        return self.connection.query(obd.commands.CLEAR_DTC).was_successful()
