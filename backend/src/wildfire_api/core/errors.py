from dataclasses import dataclass


@dataclass(slots=True)
class AppError(Exception):
    code: str
    message: str
    status_code: int
    retry_after_seconds: int | None = None


def invalid_filter(message: str) -> AppError:
    return AppError(code="INVALID_FILTER", message=message, status_code=400)


def dependency_unavailable(message: str) -> AppError:
    return AppError(code="DEPENDENCY_UNAVAILABLE", message=message, status_code=503)


def request_timeout(message: str) -> AppError:
    return AppError(code="REQUEST_TIMEOUT", message=message, status_code=504)
