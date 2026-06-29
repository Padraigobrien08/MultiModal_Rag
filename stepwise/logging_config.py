"""Logging configuration for the Stepwise API and workers."""

from __future__ import annotations

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with a consistent stdout format."""
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger("stepwise").setLevel(level)
