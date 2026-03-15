import logging
import os

from alembic import command as alembic_cmd
from alembic.config import Config as AlembicConfig
from app.database import Base, engine
from app.mcp_server import setup_mcp_server
from app.routers import apps_router, backup_router, config_router, domains_router, entities_router, memories_router, projects_router, stats_router
from app.version import __version__
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_pagination import add_pagination

logger = logging.getLogger(__name__)

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

_alembic_ini = os.path.join(os.path.dirname(__file__), "alembic.ini")
if os.path.exists(_alembic_ini):
    try:
        cfg = AlembicConfig(_alembic_ini)
        cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "alembic"))

        from sqlalchemy import inspect, text
        _inspector = inspect(engine)
        _has_alembic = _inspector.has_table("alembic_version")
        _need_stamp = False
        if _has_alembic:
            with engine.connect() as conn:
                _rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
                _need_stamp = len(_rows) == 0
        else:
            _need_stamp = True

        if _need_stamp and _inspector.has_table("memories"):
            # Existing DB created by create_all() without alembic tracking.
            # Stamp to the last pre-2.1 revision so only new migrations run.
            alembic_cmd.stamp(cfg, "v1_7_drop_memory_type_agent_id")
            logger.info("Stamped alembic to v1_7 (existing DB without migration history)")

        alembic_cmd.upgrade(cfg, "head")
        logger.info("Alembic migrations applied successfully")
    except Exception as e:
        logger.warning("Alembic migration skipped: %s", e)

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
