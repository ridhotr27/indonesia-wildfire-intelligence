import json
import logging
import re
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    """Small dependency-free JSON formatter for service logs."""

    _standard_fields = frozenset(logging.makeLogRecord({}).__dict__)
    _sensitive_keys = frozenset(
        {
            "authorization",
            "cookie",
            "password",
            "secret",
            "token",
            "api_key",
            "message_content",
        }
    )
    _secret_pattern = re.compile(
        r"(?i)(bearer\s+)[^\s,;]+|((?:password|secret|api[_-]?key|token)\s*[=:]\s*)[^\s,;]+"
    )

    @classmethod
    def _redact(cls, key: str, value: Any) -> Any:
        normalized = key.casefold()
        credential_suffixes = (
            "_password",
            "_secret",
            "_api_key",
            "_access_token",
            "_refresh_token",
        )
        if normalized in cls._sensitive_keys or normalized.endswith(credential_suffixes):
            return "[REDACTED]"
        if isinstance(value, str):
            return cls._secret_pattern.sub(
                lambda match: (match.group(1) or match.group(2)) + "[REDACTED]", value
            )
        if isinstance(value, dict):
            return {
                child_key: cls._redact(str(child_key), child) for child_key, child in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [cls._redact(key, child) for child in value]
        return value

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self._redact("log_message", record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in self._standard_fields and key not in {"message", "asctime"}:
                payload[key] = self._redact(key, value)
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())
