"""Logging configuration for the Stepwise API and workers."""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

# Correlation ID for the in-flight request; "-" when logging outside a request
# (e.g. background jobs, CLI). Set by RequestIDMiddleware.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDFilter(logging.Filter):
    """Inject the current request ID into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with a consistent stdout format."""
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] [req:%(request_id)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )
    request_filter = RequestIDFilter()
    for handler in root.handlers:
        handler.addFilter(request_filter)
    logging.getLogger("stepwise").setLevel(level)
