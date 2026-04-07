from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.routers import assets, chat, documents, export


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "files").mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "tmp_upload").mkdir(parents=True, exist_ok=True)
    init_db(settings.data_dir / "app.db")
    yield


app = FastAPI(title="CorpusLens", lifespan=lifespan)

_settings = get_settings()
_origins = [o.strip() for o in _settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(assets.router)
app.include_router(chat.router)
app.include_router(export.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
