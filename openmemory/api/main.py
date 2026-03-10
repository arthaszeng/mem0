from app.database import Base, engine
from app.mcp_server import setup_mcp_server
from app.routers import apps_router, backup_router, config_router, domains_router, memories_router, projects_router, stats_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_pagination import add_pagination

app = FastAPI(title="OpenMemory API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

setup_mcp_server(app)

app.include_router(memories_router)
app.include_router(apps_router)
app.include_router(stats_router)
app.include_router(config_router)
app.include_router(backup_router)
app.include_router(domains_router)
app.include_router(projects_router)

add_pagination(app)
