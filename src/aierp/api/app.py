from fastapi import FastAPI

from aierp.stage1_ingest.router import router as ingest_router


def create_app() -> FastAPI:
    app = FastAPI(title="aierp invoice intake")
    app.include_router(ingest_router)
    return app


app = create_app()
