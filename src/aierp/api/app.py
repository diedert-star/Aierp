from fastapi import FastAPI

from aierp.pipeline.router import router as documents_router


def create_app() -> FastAPI:
    app = FastAPI(title="aierp invoice intake")
    app.include_router(documents_router)
    return app


app = create_app()
