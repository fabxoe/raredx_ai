from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.graph import router as graph_router
from app.api.hpo_mappers import router as hpo_mappers_router
from app.api.retrieval import router as retrieval_router


ACCESS_PROTECTED_HOSTS = {"www.cromtind.uk"}
ACCESS_USER_HEADER = "cf-access-authenticated-user-email"


def _request_host(request: Request) -> str:
    return request.headers.get("host", "").split(":", maxsplit=1)[0].lower()


def _is_access_authenticated(request: Request) -> bool:
    return bool(request.headers.get(ACCESS_USER_HEADER))


def create_app() -> FastAPI:
    app = FastAPI(
        title="RARE_DX_AI",
        version="0.1.0",
        description="Explainable rare disease candidate prioritization research API.",
    )
    app.include_router(retrieval_router, prefix="/api/retrieval", tags=["retrieval"])
    app.include_router(graph_router, prefix="/api/graph", tags=["graph"])
    app.include_router(hpo_mappers_router, prefix="/api/hpo-mappers", tags=["hpo-mappers"])
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def frontend(request: Request) -> Response:
        host = _request_host(request)
        if host == "api.cromtind.uk":
            return RedirectResponse(url="/docs")
        if host in ACCESS_PROTECTED_HOSTS and not _is_access_authenticated(request):
            return FileResponse(static_dir / "login.html")
        return FileResponse(static_dir / "index.html")

    @app.get("/logout", include_in_schema=False)
    async def logout_page() -> Response:
        return FileResponse(static_dir / "logout.html")

    return app


app = create_app()
