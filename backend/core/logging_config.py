"""Structured logging configuration with redacted Admin error-log capture."""

import logging
import sys
import threading
import traceback as tb_mod


_LOCAL_GUARD = threading.local()


class AdminErrorLogHandler(logging.Handler):
    """
    Non-blocking handler that captures WARNING / ERROR / CRITICAL logs into the bounded
    Admin Alerts ring buffer (and escalates ERROR / CRITICAL records to `admin_alert_events`)
    with strict recursion protection and secret redaction.
    """

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(_LOCAL_GUARD, "active", False):
            return
        if record.levelno < logging.WARNING:
            return
        # Never recursively process alerts hub internals
        if record.name.startswith("backend.services.admin_alerts_service"):
            return
        # Ignore transient per-symbol third-party Yahoo probes (rate limits / delisted fallbacks)
        if record.name.startswith("yfinance"):
            try:
                raw_msg = record.getMessage().lower()
            except Exception:
                raw_msg = ""
            if any(
                noise in raw_msg
                for noise in (
                    "possibly delisted",
                    "symbol may be delisted",
                    "429 client error",
                    "expecting value",
                    "failed to get ticker",
                    "no data found",
                    "no price data found",
                    "no timezone found",
                )
            ):
                return
        # Ignore transient third-party websocket-client transport drops (managed cleanly by FyersStreamService)
        if record.name == "websocket" or record.name.startswith("websocket."):
            try:
                ws_msg = record.getMessage().lower()
            except Exception:
                ws_msg = ""
            if any(
                noise in ws_msg
                for noise in (
                    "connection to remote host was lost",
                    "socket is already closed",
                    "goodbye",
                )
            ):
                return

        _LOCAL_GUARD.active = True
        try:
            from backend.services.admin_alerts_service import (
                record_captured_log,
                schedule_admin_alert_nonblocking,
            )

            msg = record.getMessage()
            tb_text = None
            if record.exc_info:
                tb_text = "".join(tb_mod.format_exception(*record.exc_info))

            captured = record_captured_log(
                level=record.levelname,
                logger_name=record.name,
                message=msg,
                traceback_text=tb_text,
                module_func=f"{record.module}.{record.funcName}:{record.lineno}",
            )

            if record.levelno >= logging.ERROR:
                first_line = (captured.get("message") or msg).splitlines()[0][:140]
                is_crit = record.levelno >= logging.CRITICAL
                schedule_admin_alert_nonblocking(
                    category="ERROR_LOG",
                    subsystem=record.name.split(".")[-1].upper()[:50],
                    severity="CRITICAL" if is_crit else "WARNING",
                    title=f"[{record.levelname}] {record.name}: {first_line}",
                    detail=f"{captured.get('message')}\n{tb_text or ''}".strip(),
                    suggested_action="Inspect stack trace and subsystem telemetry in Admin Alerts Hub.",
                    metadata={
                        "logger": record.name,
                        "location": captured.get("location"),
                        "level": record.levelname,
                    },
                )
        except Exception:
            pass
        finally:
            _LOCAL_GUARD.active = False


def setup_logging(level: str = "INFO") -> None:
    """Configure application-wide structured logging and Admin error log capture."""
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    admin_handler = AdminErrorLogHandler(level=logging.WARNING)

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            admin_handler,
        ],
    )

    root_logger = logging.getLogger()
    if not any(isinstance(h, AdminErrorLogHandler) for h in root_logger.handlers):
        root_logger.addHandler(admin_handler)

    # Quiet noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
