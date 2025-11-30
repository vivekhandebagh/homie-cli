"""Configuration handling for Homie Compute."""

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


HOMIE_DIR = Path.home() / ".homie"
CONFIG_FILE = HOMIE_DIR / "config.yaml"


@dataclass
class HomieConfig:
    """Configuration for a Homie node."""

    name: str = field(default_factory=lambda: os.environ.get("USER", "homie"))
    discovery_port: int = 5555
    worker_port: int = 5556
    group_secret: str = field(default_factory=lambda: secrets.token_urlsafe(16))

    # Container settings (for plug)
    container_cpu_limit: float = 2.0
    container_memory_limit: str = "4g"
    container_timeout: int = 600
    container_network: str = "none"

    # Environment settings (for mooch)
    envs: dict = field(default_factory=lambda: {"py": "python:3.11-slim"})
    default_env: str = "py"

    # Broadcast settings
    heartbeat_interval: float = 2.0
    peer_timeout: float = 10.0


def ensure_homie_dir() -> Path:
    """Ensure the .homie directory exists."""
    HOMIE_DIR.mkdir(parents=True, exist_ok=True)
    return HOMIE_DIR


def load_config() -> HomieConfig:
    """Load configuration from file, or create default."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            data = yaml.safe_load(f) or {}
        # Handle migration from old config format
        # Remove deprecated fields
        data.pop("container_image", None)
        return HomieConfig(**data)
    return HomieConfig()


def save_config(config: HomieConfig) -> None:
    """Save configuration to file."""
    ensure_homie_dir()
    data = {
        "name": config.name,
        "discovery_port": config.discovery_port,
        "worker_port": config.worker_port,
        "group_secret": config.group_secret,
        "container_cpu_limit": config.container_cpu_limit,
        "container_memory_limit": config.container_memory_limit,
        "container_timeout": config.container_timeout,
        "container_network": config.container_network,
        "envs": config.envs,
        "default_env": config.default_env,
        "heartbeat_interval": config.heartbeat_interval,
        "peer_timeout": config.peer_timeout,
    }
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(data, f, default_flow_style=False)


def get_or_create_config() -> HomieConfig:
    """Get existing config or create and save a new one."""
    if CONFIG_FILE.exists():
        return load_config()
    config = HomieConfig()
    save_config(config)
    return config
