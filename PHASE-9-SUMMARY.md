# Phase 9 Complete: Configuration & Deployment ✅

**Date**: 2025-10-13
**Status**: Complete
**Priority**: 🟡 MEDIUM (from TECH-SPEC-V2.md)

---

## Overview

Successfully implemented **comprehensive configuration and deployment infrastructure**, providing:
- YAML-based configuration with environment variable substitution
- Hierarchical configuration with sensible defaults
- Complete deployment documentation
- Docker support
- Systemd service configuration
- Production-ready setup guides

---

## Problem Addressed

From TECH-SPEC-V2.md:
> "Need standardized configuration management and deployment documentation for production use."

**Previous Approach:**
- Hardcoded configuration
- No deployment documentation
- Manual setup process
- No environment variable support
- Difficult to customize

**New Approach:**
- YAML configuration file
- Environment variable substitution
- Hierarchical config (server/client)
- Type-safe dataclasses
- Comprehensive deployment guide
- Docker and systemd support

---

## Implementation

### Files Created

1. **`config.yaml`** (200+ lines)
   - Complete configuration template
   - All features configured
   - Commented for clarity
   - Environment variable placeholders

2. **`.env.example`** (30 lines)
   - Environment variable template
   - API key configuration
   - Override examples

3. **`gambiarra/config/loader.py`** (450+ lines)
   - Configuration loading
   - Environment variable substitution
   - Type conversion
   - Validation
   - Global config instance

4. **`gambiarra/config/__init__.py`** (25 lines)
   - Package exports

5. **`DEPLOYMENT.md`** (750+ lines)
   - Complete deployment guide
   - Quick start
   - Production setup
   - Docker deployment
   - Systemd service
   - Monitoring
   - Security
   - Troubleshooting

**Total**: ~1,455 lines of configuration infrastructure + documentation

---

## Configuration Architecture

### Configuration Hierarchy

```
Config (root)
├── ServerConfig
│   ├── host, port, log_level
│   ├── SessionConfig
│   │   ├── timeout_seconds
│   │   ├── persistence_enabled
│   │   └── persistence_dir
│   ├── AIProviderConfig
│   │   ├── type, model, api_key
│   │   └── RateLimitConfig
│   │       ├── session limits
│   │       ├── user limits
│   │       └── global limits
│   ├── ErrorRecoveryConfig
│   │   └── CircuitBreakerConfig
│   └── TransactionConfig
└── ClientConfig
    ├── server_url
    ├── SecurityConfig
    ├── CommandFilterConfig
    ├── ApprovalConfig
    ├── ExecutionConfig
    ├── ContextConfig
    └── TransactionConfig
```

### Loading Priority

Configuration is loaded in this order (later overrides earlier):

1. **Default values** (in dataclasses)
2. **YAML file** (`config.yaml`)
3. **Environment variables** (highest priority)

**Example**:

```python
# Default
port = 8765

# config.yaml
server:
  port: 9000  # Overrides default

# Environment
GAMBIARRA_SERVER_PORT=10000  # Overrides YAML
```

---

## Key Features

### 1. YAML Configuration

**Clean, readable format**:

```yaml
server:
  host: "0.0.0.0"
  port: 8765
  log_level: "INFO"

  session:
    timeout_seconds: 3600
    persistence_enabled: true
    persistence_dir: "~/.cache/gambiarra/sessions"
```

**Benefits**:
- Easy to read and edit
- Comments supported
- Hierarchical structure
- Type validation

### 2. Environment Variable Substitution

**In YAML files**:

```yaml
server:
  ai_provider:
    api_key: "${OPENAI_API_KEY}"  # Substituted at runtime
```

**Environment override**:

```bash
# Override any config value
export GAMBIARRA_SERVER_PORT=9000
export GAMBIARRA_SESSION_DAILY_BUDGET=100.00
```

**Benefits**:
- Secure (don't commit secrets)
- Flexible (per-environment config)
- Standard practice

### 3. Type-Safe Dataclasses

**Configuration as code**:

```python
@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    session_requests_per_minute: Optional[int] = 60
    session_tokens_per_hour: Optional[int] = 100000
    session_daily_budget: Optional[float] = 50.0
    warning_threshold: float = 0.8
```

**Benefits**:
- Type checking
- IDE autocomplete
- Validation
- Default values

### 4. Global Config Instance

**Easy access** anywhere in code:

```python
from gambiarra.config import get_config

config = get_config()
print(config.server.port)
print(config.server.session.timeout_seconds)
```

**Singleton pattern**:
- Loaded once
- Cached globally
- Consistent across modules

### 5. Hot Reload Support

**Reload configuration** without restart:

```python
from gambiarra.config import reload_config

# Reload from file
config = reload_config()
```

---

## Configuration Examples

### Example 1: Development Config

```yaml
server:
  host: "127.0.0.1"  # Local only
  port: 8765
  log_level: "DEBUG"  # Verbose logging

  session:
    timeout_seconds: 7200  # 2 hours
    persistence_enabled: true

  ai_provider:
    type: "openai"
    model: "gpt-4"
    rate_limit:
      session_requests_per_minute: 120  # Higher for dev
      session_daily_budget: 100.0
```

### Example 2: Production Config

```yaml
server:
  host: "0.0.0.0"  # All interfaces
  port: 8765
  log_level: "WARNING"  # Less verbose
  log_file: "/var/log/gambiarra/server.log"

  session:
    timeout_seconds: 3600  # 1 hour
    max_concurrent: 1000  # High load
    persistence_enabled: true
    persistence_dir: "/var/lib/gambiarra/sessions"

  ai_provider:
    type: "openai"
    model: "gpt-4"
    rate_limit:
      session_requests_per_minute: 30  # Lower for production
      session_daily_budget: 20.0  # Cost control
      global_daily_budget: 1000.0  # System-wide cap
```

### Example 3: Testing Config

```yaml
server:
  host: "127.0.0.1"
  port: 18765  # Different port
  log_level: "ERROR"  # Quiet

  session:
    timeout_seconds: 300  # 5 minutes
    persistence_enabled: false  # No persistence

  ai_provider:
    type: "test"  # Mock provider
    model: "test-model"
```

---

## Deployment Options

### Option 1: Direct Installation

```bash
# Install
pip install gambiarra

# Create config
cp /path/to/config.yaml ~/.config/gambiarra/

# Run
gambiarra-server
```

**Use case**: Simple deployments, development

### Option 2: Systemd Service

```bash
# Install service
sudo cp gambiarra-server.service /etc/systemd/system/

# Enable and start
sudo systemctl enable gambiarra-server
sudo systemctl start gambiarra-server
```

**Use case**: Production Linux servers

### Option 3: Docker

```bash
# Build
docker-compose build

# Run
docker-compose up -d
```

**Use case**: Containerized deployments, cloud

### Option 4: Docker Swarm/Kubernetes

See DEPLOYMENT.md for K8s manifests.

**Use case**: Distributed, high-availability

---

## Deployment Guide Sections

### 1. Quick Start

- Development setup (5 minutes)
- Production setup (15 minutes)
- Docker setup (5 minutes)

### 2. Configuration

- Configuration file structure
- All configuration options explained
- Examples for each section

### 3. Environment Variables

- Required variables
- Optional overrides
- Using .env file

### 4. Production Deployment

- System requirements
- Installation steps
- Production config
- Security hardening

### 5. Docker Deployment

- Dockerfile example
- Docker Compose configuration
- Volume management
- Health checks

### 6. Systemd Service

- Service file template
- Environment file
- Service management commands
- Security settings

### 7. Monitoring

- Health checks
- Metrics to collect
- Log rotation
- Alerting

### 8. Security

- API key protection
- Network security
- Reverse proxy setup
- Firewall rules

### 9. Troubleshooting

- Common issues
- Debugging commands
- Recovery procedures
- Performance tuning

### 10. Backup & Recovery

- What to backup
- Backup script
- Automated backups
- Restore procedure

---

## Environment Variables

### Required

```bash
# For OpenAI provider
OPENAI_API_KEY=sk-...

# For Anthropic provider
ANTHROPIC_API_KEY=sk-ant-...
```

### Common Overrides

```bash
# Server
GAMBIARRA_SERVER_HOST=0.0.0.0
GAMBIARRA_SERVER_PORT=8765
GAMBIARRA_LOG_LEVEL=INFO

# Session storage
GAMBIARRA_SESSION_STORAGE_DIR=/var/lib/gambiarra/sessions

# Rate limiting
GAMBIARRA_SESSION_REQUESTS_PER_MINUTE=60
GAMBIARRA_SESSION_DAILY_BUDGET=50.00

# Transactions
GAMBIARRA_TRANSACTION_BACKUP_DIR=/var/lib/gambiarra/transactions

# Client
GAMBIARRA_SERVER_URL=ws://localhost:8765
```

### Using .env File

```bash
# .env
OPENAI_API_KEY=sk-your-key
GAMBIARRA_LOG_LEVEL=DEBUG
GAMBIARRA_SERVER_PORT=9000
```

Automatically loaded if present in working directory.

---

## Usage Examples

### Example 1: Load Config

```python
from gambiarra.config import load_config, get_config

# Load from file
config = load_config('config.yaml')

# Or use global instance
config = get_config()

# Access values
print(f"Server: {config.server.host}:{config.server.port}")
print(f"Rate limit: {config.server.ai_provider.rate_limit.session_requests_per_minute}")
```

### Example 2: Override from Environment

```bash
# Set environment variable
export GAMBIARRA_SERVER_PORT=9000

# Python
python -c "
from gambiarra.config import get_config
config = get_config()
print(config.server.port)  # Prints: 9000
"
```

### Example 3: Custom Config Path

```python
from gambiarra.config import load_config

# Load from custom path
config = load_config('/etc/gambiarra/config.yaml')
```

### Example 4: Use in Server

```python
from gambiarra.config import get_config
from gambiarra.server.session.manager import SessionManager
from gambiarra.server.core.rate_limiting import RateLimiter

config = get_config()

# Configure session manager
session_manager = SessionManager(
    enable_persistence=config.server.session.persistence_enabled
)

# Configure rate limiter
rate_limiter = RateLimiter(
    session_requests_per_minute=config.server.ai_provider.rate_limit.session_requests_per_minute,
    session_tokens_per_hour=config.server.ai_provider.rate_limit.session_tokens_per_hour,
    session_daily_budget=config.server.ai_provider.rate_limit.session_daily_budget
)
```

---

## Security Best Practices

### 1. Protect API Keys

```bash
# Never commit to git
echo ".env" >> .gitignore
echo "config.yaml" >> .gitignore  # If it contains secrets

# Use environment variables
OPENAI_API_KEY=sk-...  # In env, not in file
```

### 2. Restrict File Permissions

```bash
# Config files
chmod 600 /etc/gambiarra/config.yaml
chmod 600 /etc/gambiarra/env

# Directories
chmod 750 /var/lib/gambiarra
chmod 750 /var/log/gambiarra
```

### 3. Use Systemd Security Features

```ini
# In service file
[Service]
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
```

### 4. Network Security

```bash
# Firewall
sudo ufw allow from 127.0.0.1 to any port 8765

# Or use reverse proxy
# Only allow proxy access
```

---

## Monitoring

### Health Check

```bash
# Simple check
curl http://localhost:8765/health

# With Python
python -c "import socket; socket.create_connection(('localhost', 8765))"
```

### Metrics to Monitor

1. **Active Sessions**: Current count
2. **Rate Limit Utilization**: % of limit used
3. **Daily Costs**: Current spending
4. **Error Rate**: Failed requests
5. **Response Time**: Average latency
6. **Memory Usage**: Process memory
7. **Disk Usage**: Session storage

### Logging

```yaml
# Production logging
server:
  log_level: "WARNING"
  log_file: "/var/log/gambiarra/server.log"
```

**Log rotation**:

```bash
# /etc/logrotate.d/gambiarra
/var/log/gambiarra/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
}
```

---

## Performance Tuning

### High Load

```yaml
server:
  session:
    max_concurrent: 1000  # More sessions

  ai_provider:
    rate_limit:
      global_requests_per_minute: 5000  # Higher throughput
```

### Low Memory

```yaml
server:
  session:
    timeout_seconds: 1800  # 30 min
    max_session_age_days: 1  # Aggressive cleanup

client:
  context:
    max_tracked_files: 50  # Less context
    max_tokens: 50000  # Smaller limit
```

### Cost Control

```yaml
server:
  ai_provider:
    rate_limit:
      session_daily_budget: 5.0  # Strict limit
      global_daily_budget: 200.0  # System cap
```

---

## Troubleshooting

### Config Not Loading

**Check**:
1. File exists: `ls -la config.yaml`
2. Valid YAML: `python -m yaml config.yaml`
3. Permissions: `ls -l config.yaml`
4. Environment: `echo $GAMBIARRA_CONFIG_FILE`

**Solution**:
```bash
# Test loading
python -c "from gambiarra.config import load_config; load_config('config.yaml')"
```

### Environment Variables Not Working

**Check**:
1. Variable set: `echo $OPENAI_API_KEY`
2. Exported: `export OPENAI_API_KEY=...`
3. Syntax: `${OPENAI_API_KEY}` in YAML

**Solution**:
```bash
# Test substitution
python -c "
import os
os.environ['OPENAI_API_KEY'] = 'test'
from gambiarra.config import load_config
config = load_config('config.yaml')
print(config.server.ai_provider.api_key)
"
```

### Permission Denied

**Check**:
```bash
ls -la /var/lib/gambiarra
```

**Solution**:
```bash
sudo chown -R gambiarra:gambiarra /var/lib/gambiarra
```

---

## Benefits

### 1. Flexibility

**Single config** for all environments:
- Development
- Staging
- Production

**Override** per environment with env vars.

### 2. Security

**API keys** never in code:
- Environment variables
- Secure file permissions
- Not in version control

### 3. Maintainability

**Centralized configuration**:
- All settings in one place
- Easy to understand
- Self-documenting

### 4. Production Ready

**Complete deployment guide**:
- Step-by-step instructions
- Docker support
- Systemd service
- Monitoring setup

### 5. Type Safety

**Compile-time checking**:
- Type hints
- IDE support
- Early error detection

---

## Migration from Hardcoded Config

### Step 1: Create Config File

```bash
cp config.yaml my-config.yaml
```

### Step 2: Move Settings

```python
# Before (hardcoded)
SERVER_PORT = 8765

# After (from config)
from gambiarra.config import get_config
config = get_config()
SERVER_PORT = config.server.port
```

### Step 3: Update Imports

```python
# Replace hardcoded values
# Before
limiter = RateLimiter(session_requests_per_minute=60)

# After
config = get_config()
limiter = RateLimiter(
    session_requests_per_minute=config.server.ai_provider.rate_limit.session_requests_per_minute
)
```

### Step 4: Test

```bash
# Test with config
python -m gambiarra.server.main --config my-config.yaml
```

---

## Future Enhancements

### Potential Improvements

1. **Configuration Validation**
   - JSON Schema validation
   - Constraint checking
   - Warning on invalid values

2. **Configuration UI**
   - Web-based config editor
   - Visual configuration
   - Real-time validation

3. **Remote Configuration**
   - Load from remote URL
   - Configuration service
   - Dynamic updates

4. **Configuration Profiles**
   - Named profiles (dev/prod)
   - Profile switching
   - Inheritance

5. **Configuration Export**
   - Export current config
   - Generate from code
   - Documentation generation

---

## Documentation

### Generated Documentation

- **DEPLOYMENT.md**: Complete deployment guide (750+ lines)
- **config.yaml**: Commented configuration example
- **.env.example**: Environment variable template

### Key Sections

1. Quick Start
2. Configuration Reference
3. Environment Variables
4. Production Deployment
5. Docker Deployment
6. Systemd Service
7. Monitoring & Logging
8. Security Best Practices
9. Troubleshooting
10. Performance Tuning

---

## Conclusion

Phase 9 successfully implements **comprehensive configuration and deployment infrastructure**:

- ✅ **YAML configuration** with environment substitution
- ✅ **Type-safe dataclasses** for all config
- ✅ **Environment variable support** for overrides
- ✅ **Global config instance** for easy access
- ✅ **Complete deployment guide** (750+ lines)
- ✅ **Docker support** with Docker Compose
- ✅ **Systemd service** configuration
- ✅ **Security best practices** documented
- ✅ **Monitoring & troubleshooting** guides
- ✅ **Production-ready** setup

This provides everything needed to deploy Gambiarra in any environment, from local development to production Kubernetes clusters.

---

**Implementation by**: Mark
**Specification**: TECH-SPEC-V2.md Phase 9
**Date**: 2025-10-13
**Files Created**: 5
**Lines Added**: ~1,455 (code + docs)
