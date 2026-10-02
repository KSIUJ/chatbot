"""Bledy API zalacznikow: jeden wyjatek z kodem dla frontendu i handler,
ktory zamienia go na odpowiedz {"detail": {"code", "message", ...}}."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

ATTACHMENTS_LIMITED = "attachments_limited"
ATTACHMENTS_DISABLED = "attachments_disabled"
FILE_TOO_LARGE = "file_too_large"
EMPTY_FILE = "empty_file"
UNSUPPORTED_TYPE = "unsupported_type"
UNREADABLE_FILE = "unreadable_file"
ATTACHMENT_NOT_FOUND = "attachment_not_found"
ATTACHMENT_SENT = "attachment_sent"
TOO_MANY_FILES = "too_many_files"
IMAGES_UNSUPPORTED = "images_unsupported"
UPLOADS_BUSY = "uploads_busy"
UPLOAD_TIMEOUT = "upload_timeout"
ATTACHMENTS_STORAGE_FULL = "attachments_storage_full"
STORAGE_UNAVAILABLE = "storage_unavailable"


class AttachmentError(Exception):
    """Odrzucony plik albo zalacznik w pytaniu - odpowiedz HTTP z kodem."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        extra: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.status_code = status_code
        self.code = code
        self.message = message
        self.extra = dict(extra or {})
        self.headers = dict(headers or {})


def attachment_error_response(exc: AttachmentError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": {"code": exc.code, "message": exc.message, **exc.extra}},
        headers={"Cache-Control": "no-store", **exc.headers},
    )


async def attachment_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handler wyjatku AttachmentError dla calej aplikacji."""
    if not isinstance(exc, AttachmentError):
        raise exc
    return attachment_error_response(exc)


def not_found() -> AttachmentError:
    return AttachmentError(404, ATTACHMENT_NOT_FOUND, "Nie znaleziono załącznika. Dołącz plik ponownie.")
