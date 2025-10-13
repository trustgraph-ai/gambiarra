"""
Configuration Management for Gambiarra.

Provides:
- YAML configuration file loading
- Environment variable substitution
- Configuration validation
- Default values
- Type checking
"""

from .loader import (
    Config,
    ServerConfig,
    ClientConfig,
    load_config,
    get_config,
    set_config
)

__all__ = [
    'Config',
    'ServerConfig',
    'ClientConfig',
    'load_config',
    'get_config',
    'set_config',
]
