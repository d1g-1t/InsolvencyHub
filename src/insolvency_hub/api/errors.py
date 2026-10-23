from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from insolvency_hub.domain.errors import DomainError, NotFound, TransitionNotAllowed, VersionConflict
from insolvency_hub.domain.legal import NORMS

STATUS = {NotFound: 404, TransitionNotAllowed: 409, VersionConflict: 412}


def _status(exc: DomainError) -> int:
    for kind, code in STATUS.items():
        if isinstance(exc, kind):
            return code
    return 422


async def domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):
        raise exc
    body: dict[str, object] = {"error": exc.code, "message": exc.message}
    if exc.basis and exc.basis in NORMS:
        norm = NORMS[exc.basis]
        body["basis"] = {"code": norm.code, "reference": norm.reference, "act": norm.act}
    if isinstance(exc, VersionConflict):
        body["current_version"] = exc.actual
    return JSONResponse(status_code=_status(exc), content=body)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
