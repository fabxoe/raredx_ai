from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.graph import router as graph_router
from app.api.hpo_mappers import router as hpo_mappers_router
from app.api.retrieval import router as retrieval_router


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
        host = request.headers.get("host", "").split(":", maxsplit=1)[0].lower()
        if host == "api.cromtind.uk":
            return RedirectResponse(url="/docs")
        return FileResponse(static_dir / "index.html")

    return app


app = create_app()
