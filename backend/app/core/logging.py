import logging
import sys

from app.core.config import settings


_LOGGING_CONFIGURED = False


def _level() -> int:
    return logging.DEBUG if settings.ENVIRONMENT == "development" else logging.INFO


def configure_application_logging() -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        root.addHandler(handler)
    root.setLevel(_level())
    _LOGGING_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_application_logging()
    logger = logging.getLogger(name)
    logger.setLevel(_level())
    logger.propagate = True
    return logger
