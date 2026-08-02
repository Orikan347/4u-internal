"""No-network helper bundled only with the Windows functional-test channel.

It deliberately preserves the logger interface consumed by the UI while
recording no customer data and opening no network connection.  Production OAuth
and release identity code must never be imported into a functional-test EXE.
"""


class GSheetLogger:
    """Compatibility no-op: functional tests never send logs externally."""

    connected = False

    def __init__(self, _webapp_url=""):
        self.error_msg = "功能測試版不連接外部記錄服務。"

    def connect(self):
        return False

    def log_send(self, *_args, **_kwargs):
        return False

    def log_send_detail(self, *_args, **_kwargs):
        return False

    def log_batch_summary(self, *_args, **_kwargs):
        return False

    def log_summary(self, *_args, **_kwargs):
        return False

    def log_survey(self, *_args, **_kwargs):
        return False


def load_gsheet_config():
    return {"webapp_url": "", "enabled": False, "channel": "functional-test"}


def save_gsheet_config(_config):
    return False
