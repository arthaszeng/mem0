"""
Memory client utilities for OpenMemory.

This module provides functionality to initialize and manage the Mem0 memory client
with automatic configuration management and Docker environment support.
"""

import hashlib
import json
import logging
import os
import threading
import time

from app.database import SessionLocal
from app.models import Config as ConfigModel

from mem0 import Memory

logger = logging.getLogger(__name__)

_memory_client = None
_config_hash = None
_last_config_check: float = 0
_CONFIG_CHECK_INTERVAL = 30  # seconds between full config rebuilds
_init_lock = threading.Lock()

COMPACT_UPDATE_MEMORY_PROMPT = """You are a memory manager. Compare new facts against existing memory and decide: ADD, UPDATE, DELETE, or NONE.

Rules:
- ADD: New fact not covered by existing memory.
- UPDATE: New fact contradicts or refines an existing memory. Keep the existing ID, update text.
- DELETE: New fact makes an existing memory obsolete/invalid.
- NONE: Existing memory already covers this fact. No change needed.
- When updating, merge related info into one concise entry rather than keeping duplicates.
- CRITICAL: Every fact starts with a [Domain] prefix like [OSMP会议管理] or [mem0记忆系统]. You MUST preserve the [Domain] prefix in ALL output. Never drop it.
- CRITICAL: If any fact contains #hashtag prefixes, preserve ALL hashtags after the [Domain] prefix.
- When merging facts from different domains, do NOT merge them — keep them as separate entries.
- Only output the JSON object, nothing else.
"""


def _get_config_hash(config_dict):
    config_str = json.dumps(config_dict, sort_keys=True)
    return hashlib.md5(config_str.encode()).hexdigest()


def _get_docker_host_url():
    from app.utils.docker_host import get_docker_host_url
    return get_docker_host_url()


def _fix_ollama_urls(config_section):
    """Fix Ollama URLs for Docker environment."""
    if not config_section or "config" not in config_section:
        return config_section

    ollama_config = config_section["config"]

    if "ollama_base_url" not in ollama_config:
        docker_host = _get_docker_host_url()
        ollama_config["ollama_base_url"] = f"http://{docker_host}:11434"
    else:
        url = ollama_config["ollama_base_url"]
        if "localhost" in url or "127.0.0.1" in url:
            docker_host = _get_docker_host_url()
            if docker_host != "localhost":
                new_url = url.replace("localhost", docker_host).replace("127.0.0.1", docker_host)
                ollama_config["ollama_base_url"] = new_url
                logger.info(f"Adjusted Ollama URL: {url} -> {new_url}")

    return config_section


def _apply_env_vector_store_overrides(vs_config):
    """Let QDRANT_HOST / QDRANT_PORT env vars override DB-stored values so
    the Docker service name is always correct even if the DB has a stale host."""
    if not vs_config or "config" not in vs_config:
        return
    env_host = os.environ.get("QDRANT_HOST")
    env_port = os.environ.get("QDRANT_PORT")
    if env_host:
        old = vs_config["config"].get("host")
        if old != env_host:
            logger.info(f"Overriding vector_store host from env: {old} -> {env_host}")
            vs_config["config"]["host"] = env_host
    if env_port:
        vs_config["config"]["port"] = int(env_port)


def reset_memory_client():
    """Reset the global memory client to force reinitialization with new config."""
    global _memory_client, _config_hash, _last_config_check
    _memory_client = None
    _config_hash = None
    _last_config_check = 0


def get_default_memory_config():
    """Get default memory client configuration with sensible defaults."""
    vector_store_config = {
        "collection_name": "openmemory",
        "host": "mem0_store",
    }

    if os.environ.get('CHROMA_HOST') and os.environ.get('CHROMA_PORT'):
        vector_store_provider = "chroma"
        vector_store_config.update({
            "host": os.environ.get('CHROMA_HOST'),
            "port": int(os.environ.get('CHROMA_PORT'))
        })
    elif os.environ.get('QDRANT_HOST') and os.environ.get('QDRANT_PORT'):
        vector_store_provider = "qdrant"
        vector_store_config.update({
            "host": os.environ.get('QDRANT_HOST'),
            "port": int(os.environ.get('QDRANT_PORT'))
        })
    elif os.environ.get('WEAVIATE_CLUSTER_URL') or (os.environ.get('WEAVIATE_HOST') and os.environ.get('WEAVIATE_PORT')):
        vector_store_provider = "weaviate"
        cluster_url = os.environ.get('WEAVIATE_CLUSTER_URL')
        if not cluster_url:
            weaviate_host = os.environ.get('WEAVIATE_HOST')
            weaviate_port = int(os.environ.get('WEAVIATE_PORT'))
            cluster_url = f"http://{weaviate_host}:{weaviate_port}"
        vector_store_config = {
            "collection_name": "openmemory",
            "cluster_url": cluster_url
        }
    elif os.environ.get('REDIS_URL'):
        vector_store_provider = "redis"
        vector_store_config = {
            "collection_name": "openmemory",
            "redis_url": os.environ.get('REDIS_URL')
        }
    elif os.environ.get('PG_HOST') and os.environ.get('PG_PORT'):
        vector_store_provider = "pgvector"
        vector_store_config.update({
            "host": os.environ.get('PG_HOST'),
            "port": int(os.environ.get('PG_PORT')),
            "dbname": os.environ.get('PG_DB', 'mem0'),
            "user": os.environ.get('PG_USER', 'mem0'),
            "password": os.environ.get('PG_PASSWORD', 'mem0')
        })
    elif os.environ.get('MILVUS_HOST') and os.environ.get('MILVUS_PORT'):
        vector_store_provider = "milvus"
        milvus_host = os.environ.get('MILVUS_HOST')
        milvus_port = int(os.environ.get('MILVUS_PORT'))
        milvus_url = f"http://{milvus_host}:{milvus_port}"
        vector_store_config = {
            "collection_name": "openmemory",
            "url": milvus_url,
            "token": os.environ.get('MILVUS_TOKEN', ''),
            "db_name": os.environ.get('MILVUS_DB_NAME', ''),
            "embedding_model_dims": 1536,
            "metric_type": "COSINE"
        }
    elif os.environ.get('ELASTICSEARCH_HOST') and os.environ.get('ELASTICSEARCH_PORT'):
        vector_store_provider = "elasticsearch"
        elasticsearch_host = os.environ.get('ELASTICSEARCH_HOST')
        elasticsearch_port = int(os.environ.get('ELASTICSEARCH_PORT'))
        full_host = f"http://{elasticsearch_host}"
        vector_store_config.update({
            "host": full_host,
            "port": elasticsearch_port,
            "user": os.environ.get('ELASTICSEARCH_USER', 'elastic'),
            "password": os.environ.get('ELASTICSEARCH_PASSWORD', 'changeme'),
            "verify_certs": False,
            "use_ssl": False,
            "embedding_model_dims": 1536
        })
    elif os.environ.get('OPENSEARCH_HOST') and os.environ.get('OPENSEARCH_PORT'):
        vector_store_provider = "opensearch"
        vector_store_config.update({
            "host": os.environ.get('OPENSEARCH_HOST'),
            "port": int(os.environ.get('OPENSEARCH_PORT'))
        })
    elif os.environ.get('FAISS_PATH'):
        vector_store_provider = "faiss"
        vector_store_config = {
            "collection_name": "openmemory",
            "path": os.environ.get('FAISS_PATH'),
            "embedding_model_dims": 1536,
            "distance_strategy": "cosine"
        }
    else:
        vector_store_provider = "qdrant"
        vector_store_config.update({
            "port": 6333,
        })

    logger.info(f"Vector store: {vector_store_provider}")

    return {
        "vector_store": {
            "provider": vector_store_provider,
            "config": vector_store_config
        },
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
        "version": "v1.1"
    }


def _parse_environment_variables(config_dict):
    """Parse 'env:VARIABLE_NAME' placeholders to actual environment variable values."""
    if isinstance(config_dict, dict):
        parsed_config = {}
        for key, value in config_dict.items():
            if isinstance(value, str) and value.startswith("env:"):
                env_var = value.split(":", 1)[1]
                env_value = os.environ.get(env_var)
                if env_value:
                    parsed_config[key] = env_value
                else:
                    logger.warning(f"Environment variable {env_var} not found for {key}")
                    parsed_config[key] = value
            elif isinstance(value, dict):
                parsed_config[key] = _parse_environment_variables(value)
            else:
                parsed_config[key] = value
        return parsed_config
    return config_dict


def get_memory_client(custom_instructions: str = None):
    """
    Get or initialize the Mem0 client. Uses a singleton pattern with hash-based
    cache invalidation — only reinitializes when the resolved config actually changes.
    Skips full config rebuild if checked within _CONFIG_CHECK_INTERVAL.
    """
    global _memory_client, _config_hash, _last_config_check

    now = time.monotonic()
    if _memory_client is not None and (now - _last_config_check) < _CONFIG_CHECK_INTERVAL:
        return _memory_client

    try:
        config = get_default_memory_config()

        db_custom_instructions = None
        db_json_config = {}

        try:
            db = SessionLocal()
            db_config = db.query(ConfigModel).filter(ConfigModel.key == "main").first()

            if db_config:
                json_config = db_config.value
                db_json_config = json_config

                if "openmemory" in json_config and "custom_instructions" in json_config["openmemory"]:
                    db_custom_instructions = json_config["openmemory"]["custom_instructions"]

                force_openai = os.environ.get("FORCE_OPENAI", "").lower() in ("1", "true", "yes")

                if "mem0" in json_config:
                    mem0_config = json_config["mem0"]

                    if "llm" in mem0_config and mem0_config["llm"] is not None:
                        if force_openai and mem0_config["llm"].get("provider") == "ollama":
                            logger.info("FORCE_OPENAI set — ignoring DB Ollama LLM config, using OpenAI defaults")
                        else:
                            config["llm"] = mem0_config["llm"]
                            if config["llm"].get("provider") == "ollama":
                                config["llm"] = _fix_ollama_urls(config["llm"])

                    if "embedder" in mem0_config and mem0_config["embedder"] is not None:
                        if force_openai and mem0_config["embedder"].get("provider") == "ollama":
                            logger.info("FORCE_OPENAI set — ignoring DB Ollama embedder config, using OpenAI defaults")
                        else:
                            config["embedder"] = mem0_config["embedder"]
                            if config["embedder"].get("provider") == "ollama":
                                config["embedder"] = _fix_ollama_urls(config["embedder"])

                    if "vector_store" in mem0_config and mem0_config["vector_store"] is not None:
                        if force_openai and mem0_config["vector_store"].get("config", {}).get("embedding_model_dims") == 768:
                            logger.info("FORCE_OPENAI set — ignoring DB 768-dim vector_store config, using 1536-dim defaults")
                        else:
                            config["vector_store"] = mem0_config["vector_store"]
                            _apply_env_vector_store_overrides(config["vector_store"])

            db.close()

        except Exception as e:
            logger.warning(f"Error loading config from database: {e}, using defaults")

        from app.utils.prompts import build_fact_extraction_prompt

        confidence_threshold = None
        try:
            ct = db_json_config.get("openmemory", {}).get("confidence_threshold")
            if ct is not None:
                confidence_threshold = float(ct)
        except (TypeError, ValueError):
            pass

        instructions_to_use = custom_instructions or db_custom_instructions
        config["custom_fact_extraction_prompt"] = (
            instructions_to_use
            or build_fact_extraction_prompt(confidence_threshold=confidence_threshold)
        )

        config["custom_update_memory_prompt"] = COMPACT_UPDATE_MEMORY_PROMPT

        if config.get("llm", {}).get("provider") == "ollama":
            llm_cfg = config["llm"]["config"]
            llm_cfg.setdefault("max_tokens", 800)
            if llm_cfg.get("max_tokens", 2000) > 800:
                llm_cfg["max_tokens"] = 800
            llm_cfg["temperature"] = 0
            llm_cfg["top_p"] = 0.9

        config = _parse_environment_variables(config)

        current_config_hash = _get_config_hash(config)

        if _memory_client is None or _config_hash != current_config_hash:
            with _init_lock:
                if _memory_client is None or _config_hash != current_config_hash:
                    logger.info(f"Initializing memory client (hash={current_config_hash})")
                    try:
                        _memory_client = Memory.from_config(config_dict=config)
                        _config_hash = current_config_hash
                        logger.info("Memory client initialized successfully")
                    except Exception as init_error:
                        logger.error(f"Failed to initialize memory client: {init_error}")
                        _memory_client = None
                        _config_hash = None
                        return None

        _last_config_check = now
        return _memory_client

    except Exception as e:
        logger.error(f"Exception in get_memory_client: {e}")
        return None


def get_default_user_id():
    return "default_user"
