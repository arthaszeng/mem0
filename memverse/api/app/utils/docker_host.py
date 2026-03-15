"""
Docker host resolution utility with process-level caching.

Determines the appropriate host URL to reach the host machine from inside
a Docker container. Used by both mem0 LLM client and categorization module.

Resolution order:
1. OLLAMA_HOST environment variable (if set)
2. host.docker.internal (Docker Desktop for Mac/Windows)
3. Docker bridge gateway IP (typically 172.17.0.1 on Linux)
4. Fallback to 172.17.0.1
"""

import logging
import os
import socket

logger = logging.getLogger(__name__)

_cached_host: str | None = None


def get_docker_host_url() -> str:
    global _cached_host
    if _cached_host is not None:
        return _cached_host

    custom_host = os.environ.get('OLLAMA_HOST')
    if custom_host:
        _cached_host = custom_host.replace('http://', '').replace('https://', '').split(':')[0]
        logger.info(f"Ollama host from OLLAMA_HOST: {_cached_host}")
        return _cached_host

    if not os.path.exists('/.dockerenv'):
        _cached_host = "localhost"
        return _cached_host

    logger.info("Detected Docker environment, resolving host for Ollama...")

    host_candidates = []

    try:
        socket.gethostbyname('host.docker.internal')
        host_candidates.append('host.docker.internal')
        logger.info("Found host.docker.internal")
    except socket.gaierror:
        pass

    try:
        with open('/proc/net/route', 'r') as f:
            for line in f:
                fields = line.strip().split()
                if fields[1] == '00000000':
                    gateway_hex = fields[2]
                    gateway_ip = socket.inet_ntoa(bytes.fromhex(gateway_hex)[::-1])
                    host_candidates.append(gateway_ip)
                    logger.info(f"Found Docker gateway: {gateway_ip}")
                    break
    except (FileNotFoundError, IndexError, ValueError):
        pass

    if not host_candidates:
        host_candidates.append('172.17.0.1')
        logger.info("Using fallback Docker bridge IP: 172.17.0.1")

    _cached_host = host_candidates[0]
    return _cached_host
