import threading
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import sessionmaker

from app.config import Settings, load_settings
from app.db import make_engine, run_migrations
from app.mailer import build_mailer
from app.routers import auth, data
from app.security import LoginThrottle

CSP = (
    "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; manifest-src 'self'; object-src 'none'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    run_migrations(settings.db_url)
    settings.db_path.chmod(0o600)

    # API docs stay off: nothing is exposed that the app itself doesn't use.
    app = FastAPI(title="Habit Helper", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.sessionmaker = sessionmaker(
        make_engine(settings.db_url), expire_on_commit=False, autoflush=False
    )
    app.state.login_throttle = LoginThrottle()
    app.state.signup_lock = threading.Lock()
    app.state.mailer = build_mailer(settings)
    app.state.email_address_throttle = LoginThrottle(limit=3, window=3600)
    app.state.email_flow_throttle = LoginThrottle(limit=100, window=3600)

    @app.exception_handler(UnicodeEncodeError)
    async def bad_text(_request: Request, _exc: UnicodeEncodeError) -> JSONResponse:
        return JSONResponse({"detail": "That text contains invalid characters."}, status_code=422)

    @app.middleware("http")
    async def protect(request: Request, call_next):
        # Backstop to SameSite=Strict: refuse state changes that come from another site.
        origin = request.headers.get("origin")
        if (
            request.method in UNSAFE_METHODS
            and origin
            and urlsplit(origin).netloc != request.headers.get("host")
        ):
            return JSONResponse({"detail": "Cross-site request refused."}, status_code=403)

        response = await call_next(request)
        headers = response.headers
        headers["Content-Security-Policy"] = CSP
        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        headers["Referrer-Policy"] = "no-referrer"
        headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        headers["X-Robots-Tag"] = "noindex, nofollow"
        if settings.secure_cookies:
            headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/api/"):
            headers["Cache-Control"] = "no-store"
        return response

    app.include_router(auth.router)
    app.include_router(data.router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    dist = settings.frontend_dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found.")
        if path and "\0" not in path:
            candidate = (dist / path).resolve()
            if candidate.is_relative_to(dist) and candidate.is_file():
                return FileResponse(candidate)
        index = dist / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=503, detail="Frontend not built: run scripts/dev.sh")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


def get_app() -> FastAPI:
    """Entry point for `uvicorn --factory app.main:get_app`."""
    return create_app()
