from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from app.paths import logs_dir


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("wt_name_relay")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(logs_dir() / "application.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    return logger


def install_exception_hooks(logger: logging.Logger) -> None:
    def handle_exception(exc_type: type[BaseException], value: BaseException, traceback: object) -> None:
        logger.critical("Unhandled exception", exc_info=(exc_type, value, traceback))
    sys.excepthook = handle_exception
    threading.excepthook = lambda args: logger.critical("Unhandled thread exception", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
