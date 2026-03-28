# AI Stock Arena Oracle Deployment

This step turns the current local benchmark into an always-on Oracle Cloud VM deployment with three services:

- FastAPI on `127.0.0.1:8000`
- Streamlit on `127.0.0.1:8501`
- Runtime scheduler loop

Nginx proxies external traffic to FastAPI and Streamlit.

## 1. VM Baseline

Use an Ubuntu VM on Oracle Cloud Free Tier and ensure these inbound ports are open:

- `22` for SSH
- `80` for HTTP
- `443` for HTTPS if TLS will be added later

## 2. Bootstrap The Server

SSH into the VM and run:

```bash
cd /tmp
git clone https://github.com/eljja/ai-stock-arena.git
cd ai-stock-arena
bash deploy/oracle/bootstrap-server.sh
```

This installs system packages, clones or updates the repo into `/opt/ai-stock-arena/current`, builds `.venv`, installs Python dependencies, and creates `/etc/ai-stock-arena/ai-stock-arena.env` if it does not exist.

## 3. Fill In Secrets

Edit the environment file:

```bash
sudo nano /etc/ai-stock-arena/ai-stock-arena.env
```

Minimum required values:

- `OPENROUTER_API_KEY`
- `DATABASE_URL`
- `ADMIN_TOKEN`
- optionally `API_BASE_URL`

For production, prefer PostgreSQL instead of SQLite.

Example:

```env
OPENROUTER_API_KEY=sk-or-v1-...
DATABASE_URL=postgresql+psycopg://trading_user:change-me@localhost:5432/llm_trading
DEFAULT_MODEL_IDS=
CONFIG_FILE=config/defaults.toml
API_BASE_URL=http://127.0.0.1:8000
ADMIN_TOKEN=change-me
```

## 4. Install Systemd Units

Copy the service units:

```bash
sudo cp deploy/oracle/systemd/ai-stock-arena-api.service /etc/systemd/system/
sudo cp deploy/oracle/systemd/ai-stock-arena-dashboard.service /etc/systemd/system/
sudo cp deploy/oracle/systemd/ai-stock-arena-scheduler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ai-stock-arena-api.service
sudo systemctl enable ai-stock-arena-dashboard.service
sudo systemctl enable ai-stock-arena-scheduler.service
```

## 5. Install Nginx Config

```bash
sudo cp deploy/oracle/nginx/ai-stock-arena.conf /etc/nginx/sites-available/ai-stock-arena
sudo ln -sf /etc/nginx/sites-available/ai-stock-arena /etc/nginx/sites-enabled/ai-stock-arena
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

## 6. Start Services

```bash
cd /opt/ai-stock-arena/current
./.venv/bin/python -m app.cli.bootstrap --skip-openrouter-sync
sudo systemctl start ai-stock-arena-api.service
sudo systemctl start ai-stock-arena-dashboard.service
sudo systemctl start ai-stock-arena-scheduler.service
```

## 7. Verify

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/runtime-settings
curl http://127.0.0.1:8000/scheduler-status
sudo systemctl status ai-stock-arena-api.service
sudo systemctl status ai-stock-arena-dashboard.service
sudo systemctl status ai-stock-arena-scheduler.service
```

From your browser, open the VM public IP. Nginx will route `/` to Streamlit and `/api/` to FastAPI.

Examples:

- `http://YOUR_SERVER_IP/`
- `http://YOUR_SERVER_IP/api/health`
- `http://YOUR_SERVER_IP/api/scheduler-status`

## 8. Update After New Commits

```bash
cd /opt/ai-stock-arena/current
bash deploy/oracle/deploy-update.sh
```

## 9. Notes

- Scheduler behavior is controlled from the admin panel and stored in the database.
- News is disabled by default in the pure benchmark configuration.
- Search-on model variants should be added as separate model profiles.
- If Oracle rotates the VM or disk, GitHub remains the source of truth for code and deployment scripts.
