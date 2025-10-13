"""
Configuration Loader for Gambiarra.

Loads configuration from:
1. YAML file (config.yaml)
2. Environment variables (override YAML)
3. Default values (fallback)

Features:
- Environment variable substitution in YAML
- Type validation
- Nested configuration access
- Hot reload support
"""

import os
import yaml
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SessionConfig:
    """Session management configuration."""
    timeout_seconds: int = 3600
    cleanup_interval: int = 300
    max_concurrent: int = 100
    persistence_enabled: bool = True
    persistence_dir: str = "~/.cache/gambiarra/sessions"
    auto_save_interval: float = 30.0
    max_session_age_days: int = 7


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    session_requests_per_minute: Optional[int] = 60
    session_tokens_per_hour: Optional[int] = 100000
    session_daily_budget: Optional[float] = 50.0

    user_requests_per_minute: Optional[int] = 300
    user_tokens_per_hour: Optional[int] = 500000
    user_daily_budget: Optional[float] = 200.0

    global_requests_per_minute: Optional[int] = 1000
    global_tokens_per_hour: Optional[int] = 10000000
    global_daily_budget: Optional[float] = 5000.0

    warning_threshold: float = 0.8


@dataclass
class AIProviderConfig:
    """AI provider configuration."""
    type: str = "openai"
    model: str = "gpt-4"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout_seconds: float = 60.0


@dataclass
class ErrorRecoveryConfig:
    """Error recovery configuration."""
    max_error_history: int = 1000
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)


@dataclass
class TransactionConfig:
    """Transaction system configuration."""
    enabled: bool = True
    backup_dir: str = "~/.cache/gambiarra/transactions"
    log_dir: str = "~/.cache/gambiarra/transaction_logs"
    auto_cleanup_hours: int = 24


@dataclass
class ServerConfig:
    """Server configuration."""
    host: str = "0.0.0.0"
    port: int = 8765
    log_level: str = "INFO"
    log_file: Optional[str] = None

    session: SessionConfig = field(default_factory=SessionConfig)
    ai_provider: AIProviderConfig = field(default_factory=AIProviderConfig)
    error_recovery: ErrorRecoveryConfig = field(default_factory=ErrorRecoveryConfig)
    transactions: TransactionConfig = field(default_factory=TransactionConfig)


@dataclass
class SecurityConfig:
    """Security configuration."""
    workspace_root: str = "."
    ignore_file: str = ".gambiarraignore"
    permissive_mode: bool = False


@dataclass
class CommandFilterConfig:
    """Command filter configuration."""
    enabled: bool = True
    allow_sudo: bool = False
    allow_destructive: bool = False


@dataclass
class ApprovalConfig:
    """Approval configuration."""
    auto_approve_reads: bool = True
    auto_approve_low_risk: bool = True
    require_approval_for_writes: bool = True
    mistake_limit: int = 3
    max_consecutive_auto_approvals: int = 10


@dataclass
class ExecutionConfig:
    """Command execution configuration."""
    default_timeout: int = 60
    inactivity_timeout: int = 30
    max_output_lines: int = 10000


@dataclass
class ContextConfig:
    """Context management configuration."""
    max_tracked_files: int = 200
    max_tokens: int = 100000
    semantic_selection: bool = True
    embedding_backend: str = "simple"


@dataclass
class ClientConfig:
    """Client configuration."""
    server_url: str = "ws://localhost:8765"
    reconnect_attempts: int = 3
    reconnect_delay: int = 5

    security: SecurityConfig = field(default_factory=SecurityConfig)
    command_filter: CommandFilterConfig = field(default_factory=CommandFilterConfig)
    approval: ApprovalConfig = field(default_factory=ApprovalConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    transactions: TransactionConfig = field(default_factory=TransactionConfig)


@dataclass
class Config:
    """Root configuration."""
    server: ServerConfig = field(default_factory=ServerConfig)
    client: ClientConfig = field(default_factory=ClientConfig)


def substitute_env_vars(text: str) -> str:
    """
    Substitute environment variables in text.

    Supports ${VAR_NAME} syntax.

    Args:
        text: Text with potential env var references

    Returns:
        Text with env vars substituted
    """
    if not isinstance(text, str):
        return text

    # Find all ${VAR_NAME} patterns
    pattern = r'\$\{([A-Z_][A-Z0-9_]*)\}'

    def replace_var(match):
        var_name = match.group(1)
        value = os.environ.get(var_name)

        if value is None:
            logger.warning(f"Environment variable {var_name} not set")
            return match.group(0)  # Keep original

        return value

    return re.sub(pattern, replace_var, text)


def substitute_env_vars_recursive(data: Any) -> Any:
    """
    Recursively substitute environment variables in nested structure.

    Args:
        data: Dict, list, or primitive value

    Returns:
        Data with env vars substituted
    """
    if isinstance(data, dict):
        return {k: substitute_env_vars_recursive(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [substitute_env_vars_recursive(item) for item in data]
    elif isinstance(data, str):
        return substitute_env_vars(data)
    else:
        return data


def load_yaml_config(config_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Load YAML configuration file.

    Args:
        config_path: Path to config.yaml

    Returns:
        Dict with configuration

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML is invalid
    """
    config_path = Path(config_path).expanduser()

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)

    # Substitute environment variables
    data = substitute_env_vars_recursive(data)

    return data


def apply_env_overrides(config_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply environment variable overrides.

    Environment variables override YAML config using pattern:
    GAMBIARRA_<SECTION>_<KEY>=value

    Example: GAMBIARRA_SERVER_PORT=9000

    Args:
        config_dict: Configuration dict from YAML

    Returns:
        Dict with env overrides applied
    """
    # Server overrides
    if 'GAMBIARRA_SERVER_HOST' in os.environ:
        config_dict.setdefault('server', {})['host'] = os.environ['GAMBIARRA_SERVER_HOST']

    if 'GAMBIARRA_SERVER_PORT' in os.environ:
        config_dict.setdefault('server', {})['port'] = int(os.environ['GAMBIARRA_SERVER_PORT'])

    if 'GAMBIARRA_LOG_LEVEL' in os.environ:
        config_dict.setdefault('server', {})['log_level'] = os.environ['GAMBIARRA_LOG_LEVEL']

    # Session overrides
    if 'GAMBIARRA_SESSION_STORAGE_DIR' in os.environ:
        config_dict.setdefault('server', {}).setdefault('session', {})['persistence_dir'] = \
            os.environ['GAMBIARRA_SESSION_STORAGE_DIR']

    # Rate limit overrides
    if 'GAMBIARRA_SESSION_REQUESTS_PER_MINUTE' in os.environ:
        config_dict.setdefault('server', {}) \
            .setdefault('ai_provider', {}) \
            .setdefault('rate_limit', {})['session_requests_per_minute'] = \
            int(os.environ['GAMBIARRA_SESSION_REQUESTS_PER_MINUTE'])

    if 'GAMBIARRA_SESSION_DAILY_BUDGET' in os.environ:
        config_dict.setdefault('server', {}) \
            .setdefault('ai_provider', {}) \
            .setdefault('rate_limit', {})['session_daily_budget'] = \
            float(os.environ['GAMBIARRA_SESSION_DAILY_BUDGET'])

    # Transaction overrides
    if 'GAMBIARRA_TRANSACTION_BACKUP_DIR' in os.environ:
        config_dict.setdefault('server', {}) \
            .setdefault('transactions', {})['backup_dir'] = \
            os.environ['GAMBIARRA_TRANSACTION_BACKUP_DIR']

    # Client overrides
    if 'GAMBIARRA_SERVER_URL' in os.environ:
        config_dict.setdefault('client', {})['server_url'] = os.environ['GAMBIARRA_SERVER_URL']

    return config_dict


def dict_to_dataclass(data_dict: Dict[str, Any], dataclass_type: type) -> Any:
    """
    Convert dict to dataclass recursively.

    Args:
        data_dict: Dictionary with configuration
        dataclass_type: Dataclass type to create

    Returns:
        Instance of dataclass_type
    """
    if data_dict is None:
        return dataclass_type()

    # Get field types
    field_types = {f.name: f.type for f in dataclass_type.__dataclass_fields__.values()}

    # Convert nested dicts to dataclasses
    kwargs = {}
    for key, value in data_dict.items():
        if key not in field_types:
            logger.warning(f"Unknown config key: {key}")
            continue

        field_type = field_types[key]

        # Check if field type is a dataclass
        if hasattr(field_type, '__dataclass_fields__'):
            kwargs[key] = dict_to_dataclass(value, field_type)
        else:
            kwargs[key] = value

    return dataclass_type(**kwargs)


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from file and environment.

    Args:
        config_path: Path to config.yaml (default: ./config.yaml or env GAMBIARRA_CONFIG_FILE)

    Returns:
        Config object

    Raises:
        FileNotFoundError: If config file doesn't exist
    """
    # Determine config file path
    if config_path is None:
        config_path = os.environ.get('GAMBIARRA_CONFIG_FILE', './config.yaml')

    config_path = Path(config_path).expanduser()

    logger.info(f"Loading configuration from {config_path}")

    # Load YAML
    try:
        config_dict = load_yaml_config(config_path)
    except FileNotFoundError:
        logger.warning(f"Config file not found: {config_path}, using defaults")
        config_dict = {}

    # Apply environment overrides
    config_dict = apply_env_overrides(config_dict)

    # Convert to dataclasses
    server_config = dict_to_dataclass(
        config_dict.get('server', {}),
        ServerConfig
    )

    client_config = dict_to_dataclass(
        config_dict.get('client', {}),
        ClientConfig
    )

    config = Config(server=server_config, client=client_config)

    logger.info(f"Configuration loaded successfully")
    logger.debug(f"Server host: {config.server.host}:{config.server.port}")
    logger.debug(f"Session persistence: {config.server.session.persistence_enabled}")

    return config


# Global config instance
_config_instance: Optional[Config] = None


def get_config() -> Config:
    """
    Get global configuration instance.

    Loads config on first call.

    Returns:
        Config object
    """
    global _config_instance

    if _config_instance is None:
        _config_instance = load_config()

    return _config_instance


def set_config(config: Config) -> None:
    """
    Set global configuration instance.

    Args:
        config: Config object to set
    """
    global _config_instance
    _config_instance = config


def reload_config(config_path: Optional[str] = None) -> Config:
    """
    Reload configuration from file.

    Args:
        config_path: Path to config.yaml

    Returns:
        New Config object
    """
    global _config_instance
    _config_instance = load_config(config_path)
    return _config_instance
