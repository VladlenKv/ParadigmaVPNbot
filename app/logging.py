import logging
import sys

from pythonjsonlogger import jsonlogger

SENSITIVE_KEYS = ("token", "password", "secret")


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for key in SENSITIVE_KEYS:
            if key in message.lower():
                record.msg = "[redacted sensitive log message]"
                record.args = ()
                break
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactingFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
