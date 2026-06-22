from fastapi import FastAPI

from app.api.graph import router as graph_router
from app.api.retrieval import router as retrieval_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="RARE_DX_AI",
        version="0.1.0",
        description="Explainable rare disease candidate prioritization research API.",
    )
    app.include_router(retrieval_router, prefix="/api/retrieval", tags=["retrieval"])
    app.include_router(graph_router, prefix="/api/graph", tags=["graph"])
    return app


app = create_app()

