from typing import Any, Dict, Optional

from app.database import get_db
from app.models import Config as ConfigModel
from app.utils.gateway_auth import AuthenticatedUser, get_authenticated_user
from app.utils.memory import reset_memory_client
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/config", tags=["config"])


def _require_superadmin(auth: AuthenticatedUser = Depends(get_authenticated_user)) -> AuthenticatedUser:
    if not auth.is_superadmin:
        raise HTTPException(403, "Superadmin required for config changes")
    return auth

class LLMConfig(BaseModel):
    model: str = Field(..., description="LLM model name")
    temperature: float = Field(..., description="Temperature setting for the model")
    max_tokens: int = Field(..., description="Maximum tokens to generate")
    api_key: Optional[str] = Field(None, description="API key or 'env:API_KEY' to use environment variable")
    ollama_base_url: Optional[str] = Field(None, description="Base URL for Ollama server (e.g., http://host.docker.internal:11434)")

class LLMProvider(BaseModel):
    provider: str = Field(..., description="LLM provider name")
    config: LLMConfig

class EmbedderConfig(BaseModel):
    model: str = Field(..., description="Embedder model name")
    api_key: Optional[str] = Field(None, description="API key or 'env:API_KEY' to use environment variable")
    ollama_base_url: Optional[str] = Field(None, description="Base URL for Ollama server (e.g., http://host.docker.internal:11434)")

class EmbedderProvider(BaseModel):
    provider: str = Field(..., description="Embedder provider name")
    config: EmbedderConfig

class VectorStoreProvider(BaseModel):
    provider: str = Field(..., description="Vector store provider name")
    # Below config can vary widely based on the vector store used. Refer https://docs.mem0.ai/components/vectordbs/config
    config: Dict[str, Any] = Field(..., description="Vector store-specific configuration")

class MemverseConfig(BaseModel):
    custom_instructions: Optional[str] = Field(None, description="Custom instructions for memory management and fact extraction")
    confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence threshold (0.0-1.0) for fact extraction; facts below this threshold are discarded")

class Mem0Config(BaseModel):
    llm: Optional[LLMProvider] = None
    embedder: Optional[EmbedderProvider] = None
    vector_store: Optional[VectorStoreProvider] = None

class ConfigSchema(BaseModel):
    memverse: Optional[MemverseConfig] = None
    mem0: Optional[Mem0Config] = None

def get_default_configuration():
    """Get the default configuration with sensible defaults for LLM, embedder and vector store."""
    return {
        "memverse": {
            "custom_instructions": None
        },
        "mem0": {
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "gpt-4o-mini",
                    "temperature": 0.1,
                    "max_tokens": 2000,
                    "api_key": "env:OPENAI_API_KEY"
                }
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": "text-embedding-3-small",
                    "api_key": "env:OPENAI_API_KEY"
                }
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "host": "memverse_store",
                    "port": 6333,
                    "collection_name": "openmemory",
                    "embedding_model_dims": 1536
                }
            }
        }
    }

def get_config_from_db(db: Session, key: str = "main"):
    """Get configuration from database."""
    config = db.query(ConfigModel).filter(ConfigModel.key == key).first()
    
    if not config:
        # Create default config with proper provider configurations
        default_config = get_default_configuration()
        db_config = ConfigModel(key=key, value=default_config)
        db.add(db_config)
        db.commit()
        db.refresh(db_config)
        return default_config
    
    # Ensure the config has all required sections with defaults
    config_value = config.value
    default_config = get_default_configuration()
    
    # Merge with defaults to ensure all required fields exist
    if "memverse" not in config_value:
        config_value["memverse"] = config_value.get("openmemory") or default_config["memverse"]
    
    if "mem0" not in config_value:
        config_value["mem0"] = default_config["mem0"]
    else:
        # Ensure LLM config exists with defaults
        if "llm" not in config_value["mem0"] or config_value["mem0"]["llm"] is None:
            config_value["mem0"]["llm"] = default_config["mem0"]["llm"]
        
        # Ensure embedder config exists with defaults
        if "embedder" not in config_value["mem0"] or config_value["mem0"]["embedder"] is None:
            config_value["mem0"]["embedder"] = default_config["mem0"]["embedder"]
        
        # Ensure vector_store config exists with defaults
        if "vector_store" not in config_value["mem0"]:
            config_value["mem0"]["vector_store"] = default_config["mem0"]["vector_store"]

    # Save the updated config back to database if it was modified
    if config_value != config.value:
        config.value = config_value
        db.commit()
        db.refresh(config)
    
    return config_value

def save_config_to_db(db: Session, config: Dict[str, Any], key: str = "main"):
    """Save configuration to database."""
    db_config = db.query(ConfigModel).filter(ConfigModel.key == key).first()
    
    if db_config:
        db_config.value = config
        db_config.updated_at = None  # Will trigger the onupdate to set current time
    else:
        db_config = ConfigModel(key=key, value=config)
        db.add(db_config)
        
    db.commit()
    db.refresh(db_config)
    return db_config.value

def _mask_secrets(config: Dict[str, Any], is_superadmin: bool) -> Dict[str, Any]:
    """Mask api_key fields for non-superadmin users."""
    if is_superadmin:
        return config
    import copy
    masked = copy.deepcopy(config)
    for section in ("llm", "embedder"):
        try:
            if masked.get("mem0", {}).get(section, {}).get("config", {}).get("api_key"):
                masked["mem0"][section]["config"]["api_key"] = "***"
        except (TypeError, KeyError):
            pass
    return masked


@router.get("/", response_model=ConfigSchema)
async def get_configuration(
    db: Session = Depends(get_db),
    auth: AuthenticatedUser = Depends(get_authenticated_user),
):
    """Get the current configuration."""
    config = get_config_from_db(db)
    return _mask_secrets(config, auth.is_superadmin)

@router.put("/", response_model=ConfigSchema)
async def update_configuration(
    config: ConfigSchema,
    db: Session = Depends(get_db),
    admin: AuthenticatedUser = Depends(_require_superadmin),
):
    """Update the configuration."""
    current_config = get_config_from_db(db)
    
    updated_config = current_config.copy()
    
    if config.memverse is not None:
        if "memverse" not in updated_config:
            updated_config["memverse"] = {}
        updated_config["memverse"].update(config.memverse.model_dump(exclude_none=True))
    
    if config.mem0 is not None:
        incoming = config.mem0.model_dump(exclude_none=True)
        if "mem0" not in updated_config:
            updated_config["mem0"] = {}
        for key in ("llm", "embedder"):
            if key in incoming:
                updated_config["mem0"][key] = incoming[key]
        if "vector_store" in incoming:
            updated_config["mem0"]["vector_store"] = incoming["vector_store"]

    save_config_to_db(db, updated_config)
    reset_memory_client()
    return updated_config
    

@router.patch("/", response_model=ConfigSchema)
async def patch_configuration(
    config_update: ConfigSchema,
    db: Session = Depends(get_db),
    admin: AuthenticatedUser = Depends(_require_superadmin),
):
    """Update parts of the configuration."""
    current_config = get_config_from_db(db)

    def deep_update(source, overrides):
        for key, value in overrides.items():
            if isinstance(value, dict) and key in source and isinstance(source[key], dict):
                source[key] = deep_update(source[key], value)
            else:
                source[key] = value
        return source

    update_data = config_update.model_dump(exclude_unset=True)
    updated_config = deep_update(current_config, update_data)

    save_config_to_db(db, updated_config)
    reset_memory_client()
    return updated_config


@router.post("/reset", response_model=ConfigSchema)
async def reset_configuration(
    db: Session = Depends(get_db),
    admin: AuthenticatedUser = Depends(_require_superadmin),
):
    """Reset the configuration to default values."""
    try:
        # Get the default configuration with proper provider setups
        default_config = get_default_configuration()
        
        # Save it as the current configuration in the database
        save_config_to_db(db, default_config)
        reset_memory_client()
        return default_config
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to reset configuration: {str(e)}"
        )

@router.get("/mem0/llm", response_model=LLMProvider)
async def get_llm_configuration(
    db: Session = Depends(get_db),
    auth: AuthenticatedUser = Depends(get_authenticated_user),
):
    """Get only the LLM configuration."""
    config = get_config_from_db(db)
    llm_config = config.get("mem0", {}).get("llm", {})
    if not auth.is_superadmin:
        import copy
        llm_config = copy.deepcopy(llm_config)
        if llm_config.get("config", {}).get("api_key"):
            llm_config["config"]["api_key"] = "***"
    return llm_config

@router.put("/mem0/llm", response_model=LLMProvider)
async def update_llm_configuration(
    llm_config: LLMProvider,
    db: Session = Depends(get_db),
    admin: AuthenticatedUser = Depends(_require_superadmin),
):
    """Update only the LLM configuration."""
    current_config = get_config_from_db(db)
    
    # Ensure mem0 key exists
    if "mem0" not in current_config:
        current_config["mem0"] = {}
    
    # Update the LLM configuration
    current_config["mem0"]["llm"] = llm_config.model_dump(exclude_none=True)
    
    # Save the configuration to database
    save_config_to_db(db, current_config)
    reset_memory_client()
    return current_config["mem0"]["llm"]

@router.get("/mem0/embedder", response_model=EmbedderProvider)
async def get_embedder_configuration(
    db: Session = Depends(get_db),
    auth: AuthenticatedUser = Depends(get_authenticated_user),
):
    """Get only the Embedder configuration."""
    config = get_config_from_db(db)
    embedder_config = config.get("mem0", {}).get("embedder", {})
    if not auth.is_superadmin:
        import copy
        embedder_config = copy.deepcopy(embedder_config)
        if embedder_config.get("config", {}).get("api_key"):
            embedder_config["config"]["api_key"] = "***"
    return embedder_config

@router.put("/mem0/embedder", response_model=EmbedderProvider)
async def update_embedder_configuration(
    embedder_config: EmbedderProvider,
    db: Session = Depends(get_db),
    admin: AuthenticatedUser = Depends(_require_superadmin),
):
    """Update only the Embedder configuration."""
    current_config = get_config_from_db(db)
    
    # Ensure mem0 key exists
    if "mem0" not in current_config:
        current_config["mem0"] = {}
    
    # Update the Embedder configuration
    current_config["mem0"]["embedder"] = embedder_config.model_dump(exclude_none=True)
    
    # Save the configuration to database
    save_config_to_db(db, current_config)
    reset_memory_client()
    return current_config["mem0"]["embedder"]

@router.get("/mem0/vector_store", response_model=Optional[VectorStoreProvider])
async def get_vector_store_configuration(
    db: Session = Depends(get_db),
    auth: AuthenticatedUser = Depends(get_authenticated_user),
):
    """Get only the Vector Store configuration."""
    config = get_config_from_db(db)
    vector_store_config = config.get("mem0", {}).get("vector_store", None)
    return vector_store_config

@router.put("/mem0/vector_store", response_model=VectorStoreProvider)
async def update_vector_store_configuration(
    vector_store_config: VectorStoreProvider,
    db: Session = Depends(get_db),
    admin: AuthenticatedUser = Depends(_require_superadmin),
):
    """Update only the Vector Store configuration."""
    current_config = get_config_from_db(db)
    
    # Ensure mem0 key exists
    if "mem0" not in current_config:
        current_config["mem0"] = {}
    
    # Update the Vector Store configuration
    current_config["mem0"]["vector_store"] = vector_store_config.model_dump(exclude_none=True)
    
    # Save the configuration to database
    save_config_to_db(db, current_config)
    reset_memory_client()
    return current_config["mem0"]["vector_store"]

@router.get("/memverse", response_model=MemverseConfig)
async def get_memverse_configuration(
    db: Session = Depends(get_db),
    auth: AuthenticatedUser = Depends(get_authenticated_user),
):
    """Get only the Memverse configuration."""
    config = get_config_from_db(db)
    memverse_config = config.get("memverse", {})
    return memverse_config

@router.put("/memverse", response_model=MemverseConfig)
async def update_memverse_configuration(
    memverse_config: MemverseConfig,
    db: Session = Depends(get_db),
    admin: AuthenticatedUser = Depends(_require_superadmin),
):
    """Update only the Memverse configuration."""
    current_config = get_config_from_db(db)
    
    # Ensure memverse key exists
    if "memverse" not in current_config:
        current_config["memverse"] = {}
    
    # Update the Memverse configuration
    current_config["memverse"].update(memverse_config.model_dump(exclude_none=True))
    
    # Save the configuration to database
    save_config_to_db(db, current_config)
    reset_memory_client()
    return current_config["memverse"]
