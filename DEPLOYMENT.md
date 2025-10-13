# Gambiarra Deployment Guide

Complete guide for deploying and configuring Gambiarra in various environments.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Configuration](#configuration)
3. [Environment Variables](#environment-variables)
4. [Production Deployment](#production-deployment)
5. [Docker Deployment](#docker-deployment)
6. [Systemd Service](#systemd-service)
7. [Monitoring](#monitoring)
8. [Security](#security)
9. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Development Setup

```bash
# Clone repository
git clone https://github.com/trustgraph/gambiarra.git
cd gambiarra

# Install dependencies
pip install -r requirements.txt

# Copy example config
cp .env.example .env

# Edit .env and add your API key
nano .env  # Add OPENAI_API_KEY=sk-...

# Run server
python -m gambiarra.server.main

# In another terminal, run client
python -m gambiarra.client.main
```

### Production Setup

```bash
# Install as package
pip install -e .

# Create config directory
mkdir -p ~/.config/gambiarra

# Copy and edit config
cp config.yaml ~/.config/gambiarra/
nano ~/.config/gambiarra/config.yaml

# Set up systemd service (see below)
sudo systemctl start gambiarra-server
```

---

## Configuration

### Configuration File

Gambiarra uses `config.yaml` for configuration. Create it from the example:

```bash
cp config.yaml my-config.yaml
```

**Location priority** (first found is used):
1. `GAMBIARRA_CONFIG_FILE` environment variable
2. `./config.yaml` (current directory)
3. `~/.config/gambiarra/config.yaml`
4. `/etc/gambiarra/config.yaml`

### Key Configuration Sections

#### Server Settings

```yaml
server:
  host: "0.0.0.0"  # Listen on all interfaces
  port: 8765        # WebSocket port
  log_level: "INFO" # DEBUG, INFO, WARNING, ERROR
```

#### Session Management

```yaml
server:
  session:
    timeout_seconds: 3600     # 1 hour timeout
    max_concurrent: 100       # Max concurrent sessions
    persistence_enabled: true # Save sessions to disk
    persistence_dir: "~/.cache/gambiarra/sessions"
    auto_save_interval: 30    # Auto-save every 30 seconds
```

#### Rate Limiting

```yaml
server:
  ai_provider:
    rate_limit:
      # Per-session limits
      session_requests_per_minute: 60
      session_tokens_per_hour: 100000
      session_daily_budget: 50.0  # USD

      # Per-user limits (across sessions)
      user_requests_per_minute: 300
      user_daily_budget: 200.0

      # Global limits (entire system)
      global_requests_per_minute: 1000
      global_daily_budget: 5000.0
```

#### AI Provider

```yaml
server:
  ai_provider:
    type: "openai"  # openai or anthropic
    model: "gpt-4"
    api_key: "${OPENAI_API_KEY}"  # Use env var
    base_url: null  # Optional custom endpoint
```

#### Security

```yaml
client:
  security:
    workspace_root: "."
    ignore_file: ".gambiarraignore"
    permissive_mode: false  # Strict security

    command_filter:
      enabled: true
      allow_sudo: false
      allow_destructive: false

    approval:
      auto_approve_reads: true
      require_approval_for_writes: true
```

---

## Environment Variables

### Required

```bash
# OpenAI (if using OpenAI provider)
export OPENAI_API_KEY="sk-your-api-key"

# OR Anthropic (if using Anthropic provider)
export ANTHROPIC_API_KEY="sk-ant-your-api-key"
```

### Optional

```bash
# Configuration file location
export GAMBIARRA_CONFIG_FILE="/path/to/config.yaml"

# Log level override
export GAMBIARRA_LOG_LEVEL="DEBUG"

# Server settings
export GAMBIARRA_SERVER_HOST="0.0.0.0"
export GAMBIARRA_SERVER_PORT="8765"

# Session storage
export GAMBIARRA_SESSION_STORAGE_DIR="~/.cache/gambiarra/sessions"

# Rate limiting overrides
export GAMBIARRA_SESSION_REQUESTS_PER_MINUTE="60"
export GAMBIARRA_SESSION_DAILY_BUDGET="50.00"

# Client server URL
export GAMBIARRA_SERVER_URL="ws://localhost:8765"
```

### Using .env File

Create `.env` file:

```bash
cp .env.example .env
nano .env
```

The application automatically loads `.env` if present.

---

## Production Deployment

### System Requirements

**Minimum**:
- CPU: 2 cores
- RAM: 2GB
- Disk: 10GB
- Python: 3.10+

**Recommended**:
- CPU: 4 cores
- RAM: 4GB
- Disk: 50GB (for session storage)
- Python: 3.11+

### Installation

```bash
# Create dedicated user
sudo useradd -r -s /bin/bash -d /opt/gambiarra gambiarra

# Create directories
sudo mkdir -p /opt/gambiarra
sudo mkdir -p /var/log/gambiarra
sudo mkdir -p /var/lib/gambiarra/sessions

# Set ownership
sudo chown -R gambiarra:gambiarra /opt/gambiarra
sudo chown -R gambiarra:gambiarra /var/log/gambiarra
sudo chown -R gambiarra:gambiarra /var/lib/gambiarra

# Install as gambiarra user
sudo -u gambiarra bash
cd /opt/gambiarra
python -m venv venv
source venv/bin/activate
pip install gambiarra

# Copy configuration
cp /path/to/config.yaml /etc/gambiarra/config.yaml
chmod 600 /etc/gambiarra/config.yaml  # Protect API keys
```

### Production Config

```yaml
# /etc/gambiarra/config.yaml

server:
  host: "127.0.0.1"  # Use reverse proxy
  port: 8765
  log_level: "WARNING"  # Less verbose
  log_file: "/var/log/gambiarra/server.log"

  session:
    timeout_seconds: 7200  # 2 hours
    max_concurrent: 1000
    persistence_dir: "/var/lib/gambiarra/sessions"

  ai_provider:
    rate_limit:
      # Production rate limits
      session_requests_per_minute: 30
      session_daily_budget: 20.0
      global_daily_budget: 1000.0
```

---

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY gambiarra/ ./gambiarra/
COPY config.yaml .

# Create volumes for data
VOLUME ["/data/sessions", "/data/transactions", "/logs"]

# Expose port
EXPOSE 8765

# Run server
CMD ["python", "-m", "gambiarra.server.main"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  gambiarra-server:
    build: .
    ports:
      - "8765:8765"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GAMBIARRA_CONFIG_FILE=/app/config.yaml
      - GAMBIARRA_LOG_LEVEL=INFO
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - sessions-data:/data/sessions
      - transactions-data:/data/transactions
      - logs:/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import socket; socket.create_connection(('localhost', 8765), timeout=1)"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  sessions-data:
  transactions-data:
  logs:
```

### Running with Docker

```bash
# Build image
docker-compose build

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

---

## Systemd Service

### Server Service

Create `/etc/systemd/system/gambiarra-server.service`:

```ini
[Unit]
Description=Gambiarra AI Coding Assistant Server
After=network.target

[Service]
Type=simple
User=gambiarra
Group=gambiarra
WorkingDirectory=/opt/gambiarra
Environment="PATH=/opt/gambiarra/venv/bin"
Environment="GAMBIARRA_CONFIG_FILE=/etc/gambiarra/config.yaml"
EnvironmentFile=/etc/gambiarra/env
ExecStart=/opt/gambiarra/venv/bin/python -m gambiarra.server.main
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/gambiarra /var/log/gambiarra

[Install]
WantedBy=multi-user.target
```

### Environment File

Create `/etc/gambiarra/env`:

```bash
OPENAI_API_KEY=sk-your-api-key
GAMBIARRA_LOG_LEVEL=INFO
```

### Service Management

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable gambiarra-server

# Start service
sudo systemctl start gambiarra-server

# Check status
sudo systemctl status gambiarra-server

# View logs
sudo journalctl -u gambiarra-server -f

# Restart service
sudo systemctl restart gambiarra-server

# Stop service
sudo systemctl stop gambiarra-server
```

---

## Monitoring

### Health Check

```bash
# Simple check
curl http://localhost:8765/health

# Or with Python
python -c "import socket; socket.create_connection(('localhost', 8765), timeout=1)"
```

### Metrics Collection

Monitor these metrics:

1. **Active Sessions**
   - Current count
   - Peak count
   - Session duration

2. **Rate Limiting**
   - Requests per minute
   - Token usage per hour
   - Daily cost

3. **Resource Usage**
   - CPU usage
   - Memory usage
   - Disk space (sessions)

4. **Error Rates**
   - Failed requests
   - Circuit breaker state
   - Rollback count

### Logging

```yaml
# config.yaml
server:
  log_level: "INFO"
  log_file: "/var/log/gambiarra/server.log"
```

**Log rotation** (using logrotate):

Create `/etc/logrotate.d/gambiarra`:

```
/var/log/gambiarra/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 gambiarra gambiarra
    sharedscripts
    postrotate
        systemctl reload gambiarra-server > /dev/null 2>&1 || true
    endscript
}
```

---

## Security

### API Key Protection

**Never commit API keys** to version control:

```bash
# Add to .gitignore
echo ".env" >> .gitignore
echo "config.yaml" >> .gitignore
```

**Protect config files**:

```bash
# Restrict permissions
chmod 600 /etc/gambiarra/config.yaml
chmod 600 /etc/gambiarra/env
```

### Network Security

**Use reverse proxy** (Nginx):

```nginx
upstream gambiarra {
    server 127.0.0.1:8765;
}

server {
    listen 443 ssl http2;
    server_name gambiarra.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://gambiarra;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Firewall rules**:

```bash
# Allow only local connections (no reverse proxy)
sudo ufw allow from 127.0.0.1 to any port 8765

# Or allow from specific network (with reverse proxy)
sudo ufw allow from 10.0.0.0/8 to any port 8765
```

### Rate Limiting

Configure appropriate rate limits to prevent abuse:

```yaml
server:
  ai_provider:
    rate_limit:
      session_requests_per_minute: 30  # Lower for production
      session_daily_budget: 20.0       # Protect from runaway costs
      global_daily_budget: 1000.0      # System-wide cap
```

---

## Troubleshooting

### Server Won't Start

**Check logs**:

```bash
sudo journalctl -u gambiarra-server -n 50
```

**Common issues**:

1. **Port already in use**
   ```bash
   # Find process using port
   sudo lsof -i :8765

   # Kill it or change port in config
   ```

2. **Missing API key**
   ```bash
   # Check environment
   echo $OPENAI_API_KEY

   # Set in /etc/gambiarra/env
   ```

3. **Permission denied**
   ```bash
   # Check ownership
   ls -la /var/lib/gambiarra

   # Fix ownership
   sudo chown -R gambiarra:gambiarra /var/lib/gambiarra
   ```

### High Memory Usage

**Check session count**:

```bash
# Count session files
ls -1 ~/.cache/gambiarra/sessions/*.json | wc -l
```

**Clean old sessions**:

```python
from gambiarra.server.session.persistence import SessionPersistence

persistence = SessionPersistence()
deleted = await persistence.cleanup_old_sessions()
print(f"Deleted {deleted} old sessions")
```

**Reduce session timeout**:

```yaml
server:
  session:
    timeout_seconds: 1800  # 30 minutes instead of 1 hour
    max_session_age_days: 3  # Delete after 3 days
```

### Rate Limit Errors

**Check current usage**:

```python
from gambiarra.server.core.rate_limiting import get_rate_limiter

limiter = get_rate_limiter()
status = limiter.get_status(session_id="your-session-id")
print(status)
```

**Increase limits** (if justified):

```yaml
server:
  ai_provider:
    rate_limit:
      session_requests_per_minute: 120  # Double the limit
      session_daily_budget: 100.0       # Increase budget
```

### Connection Issues

**Test WebSocket connection**:

```bash
# Install wscat
npm install -g wscat

# Test connection
wscat -c ws://localhost:8765
```

**Check firewall**:

```bash
# Check firewall status
sudo ufw status

# Allow port if blocked
sudo ufw allow 8765
```

### Database/Session Corruption

**Recover from backup**:

```bash
# Sessions have .backup files
cd ~/.cache/gambiarra/sessions
mv session-id.json session-id.json.bad
mv session-id.json.backup session-id.json
```

**Reset all sessions** (last resort):

```bash
# Backup first!
cp -r ~/.cache/gambiarra/sessions ~/.cache/gambiarra/sessions.backup

# Remove all sessions
rm -rf ~/.cache/gambiarra/sessions/*.json
```

---

## Backup & Recovery

### What to Backup

1. **Configuration**
   - `/etc/gambiarra/config.yaml`
   - `/etc/gambiarra/env`

2. **Session Data**
   - `/var/lib/gambiarra/sessions/`

3. **Transaction Logs**
   - `/var/lib/gambiarra/transactions/`

### Backup Script

```bash
#!/bin/bash
# backup-gambiarra.sh

BACKUP_DIR="/backup/gambiarra/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# Backup config
cp /etc/gambiarra/config.yaml "$BACKUP_DIR/"
cp /etc/gambiarra/env "$BACKUP_DIR/"

# Backup sessions
tar -czf "$BACKUP_DIR/sessions.tar.gz" /var/lib/gambiarra/sessions/

# Backup transactions
tar -czf "$BACKUP_DIR/transactions.tar.gz" /var/lib/gambiarra/transactions/

# Keep only last 7 days
find /backup/gambiarra -type d -mtime +7 -exec rm -rf {} \;
```

### Automated Backups

Add to crontab:

```bash
# Run daily at 2 AM
0 2 * * * /usr/local/bin/backup-gambiarra.sh
```

---

## Performance Tuning

### For High Load

```yaml
server:
  session:
    max_concurrent: 1000  # Increase concurrent sessions

  ai_provider:
    rate_limit:
      global_requests_per_minute: 5000  # Increase throughput
```

### For Low Memory

```yaml
server:
  session:
    timeout_seconds: 1800  # 30 min timeout
    auto_save_interval: 60  # Save less frequently
    max_session_age_days: 1  # Clean up aggressively

client:
  context:
    max_tracked_files: 50  # Reduce context size
    max_tokens: 50000  # Reduce token limit
```

### For Cost Control

```yaml
server:
  ai_provider:
    rate_limit:
      session_daily_budget: 5.0  # Strict per-session limit
      user_daily_budget: 20.0     # Strict per-user limit
      global_daily_budget: 200.0  # System-wide cap
```

---

## Upgrade Procedure

### Minor Version Upgrade

```bash
# Stop service
sudo systemctl stop gambiarra-server

# Backup
/usr/local/bin/backup-gambiarra.sh

# Upgrade package
sudo -u gambiarra bash
source /opt/gambiarra/venv/bin/activate
pip install --upgrade gambiarra

# Restart service
sudo systemctl start gambiarra-server

# Check status
sudo systemctl status gambiarra-server
```

### Major Version Upgrade

1. **Read release notes** for breaking changes
2. **Backup everything**
3. **Test in staging** environment first
4. **Update configuration** if needed
5. **Upgrade** following minor version procedure
6. **Verify** functionality

---

## Support

### Getting Help

- **Documentation**: https://docs.gambiarra.ai
- **Issues**: https://github.com/trustgraph/gambiarra/issues
- **Community**: https://discord.gg/gambiarra

### Reporting Issues

Include:
1. Gambiarra version
2. Python version
3. Operating system
4. Configuration (sanitized)
5. Logs (relevant portions)
6. Steps to reproduce

---

**Last Updated**: 2025-10-13
**Version**: 1.0.0
