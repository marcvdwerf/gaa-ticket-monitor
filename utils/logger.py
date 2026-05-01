from __future__ import annotations

import logging
import sys

from config import LOG_LEVEL


def setup_logger(name: str = "gaa-ticket-monitor") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(LOG_LEVEL)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    formatter.converter = __import__("time").gmtime
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger
