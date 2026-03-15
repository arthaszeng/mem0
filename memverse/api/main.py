import os

from app.database import Base, engine
from app.mcp_server import setup_mcp_server
from app.routers import apps_router, backup_router, config_router, domains_router, entities_router, memories_router, projects_router, stats_router
from app.version import __version__
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_pagination import add_pagination

app = FastAPI(title="Memverse API", version=__version__)


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__}

_cors_origins = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

setup_mcp_server(app)

app.include_router(memories_router)
app.include_router(entities_router)
app.include_router(apps_router)
app.include_router(stats_router)
app.include_router(config_router)
app.include_router(backup_router)
app.include_router(domains_router)
app.include_router(projects_router)

add_pagination(app)
