# AI Stock Arena Oracle Deployment

This deployment runs the public benchmark on an Oracle Cloud Ubuntu VM.

Runtime services:

- FastAPI on `127.0.0.1:8000`
- Streamlit on `127.0.0.1:8501`
- scheduler as a long-running systemd service
- nginx proxying `/api/` to FastAPI and `/` to Streamlit

## 1. VM Baseline

Use an Ubuntu Oracle VM and open inbound traffic for:

- `22/tcp` for SSH
- `80/tcp` for HTTP
- `443/tcp` for HTTPS

Oracle images can also have host-level `iptables` rules. Confirm that `80` and `443` are accepted before the default reject rule:

```bash
sudo iptables -L INPUT -n --line-numbers
```

If needed:

```bash
sudo iptables -I INPUT 5 -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

## 2. Add Swap

The Free Tier VM is memory constrained. Use swap to reduce hangs under Streamlit/API/scheduler load.

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

## 3. Bootstrap The Server

```bash
cd /tmp
git clone https://github.com/eljja/ai-stock-arena.git
cd ai-stock-arena
bash deploy/oracle/bootstrap-server.sh
```

The bootstrap script installs system packages, prepares `/opt/ai-stock-arena/current`, creates `.venv`, installs Python dependencies, and creates `/etc/ai-stock-arena/ai-stock-arena.env` if it does not exist.

## 4. Configure Secrets

Edit:

```bash
sudo nano /etc/ai-stock-arena/ai-stock-arena.env
```

Minimum values:

```env
OPENROUTER_API_KEY=sk-or-v1-...
DATABASE_URL=postgresql+psycopg://trading_user:change-me@localhost:5432/llm_trading
CONFIG_FILE=config/defaults.toml
API_BASE_URL=http://127.0.0.1:8000
ADMIN_TOKEN=change-me
```

Provider secrets can also be managed from the admin panel:

- Marketaux API token
- Naver client id
- Naver client secret
- Alpha Vantage API key

## 5. Install Services

```bash
sudo cp deploy/oracle/systemd/ai-stock-arena-api.service /etc/systemd/system/
sudo cp deploy/oracle/systemd/ai-stock-arena-dashboard.service /etc/systemd/system/
sudo cp deploy/oracle/systemd/ai-stock-arena-scheduler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ai-stock-arena-api.service
sudo systemctl enable ai-stock-arena-dashboard.service
sudo systemctl enable ai-stock-arena-scheduler.service
```

Start:

```bash
cd /opt/ai-stock-arena/current
./.venv/bin/python -m app.cli.bootstrap --skip-openrouter-sync
sudo systemctl start ai-stock-arena-api.service
sudo systemctl start ai-stock-arena-dashboard.service
sudo systemctl start ai-stock-arena-scheduler.service
```

## 6. Configure Nginx

Install the provided nginx config:

```bash
sudo cp deploy/oracle/nginx/ai-stock-arena.conf /etc/nginx/sites-available/ai-stock-arena
sudo ln -sf /etc/nginx/sites-available/ai-stock-arena /etc/nginx/sites-enabled/ai-stock-arena
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

The config includes Streamlit websocket forwarding for `/_stcore/`.

For a domain deployment, update `server_name` on the server to include the domain:

```nginx
server_name aistockarena.com www.aistockarena.com;
```

## 7. HTTPS

After DNS points to the VM:

```bash
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d aistockarena.com -d www.aistockarena.com
```

Choose HTTP-to-HTTPS redirect when prompted.

## 8. Verify

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/runtime-settings
curl http://127.0.0.1:8000/scheduler-status
curl -I -H "Host: aistockarena.com" http://127.0.0.1/
sudo systemctl status nginx --no-pager
sudo systemctl status ai-stock-arena-api.service --no-pager
sudo systemctl status ai-stock-arena-dashboard.service --no-pager
sudo systemctl status ai-stock-arena-scheduler.service --no-pager
```

Public checks:

- `https://aistockarena.com`
- `https://aistockarena.com/api/health`
- `https://aistockarena.com/api/scheduler-status`

## 9. Update After New Commits

```bash
cd /opt/ai-stock-arena/current
bash deploy/oracle/deploy-update.sh
```

If the server branch diverged because the remote branch was force-pushed, back up local changes before aligning the server to `origin/main`.

```bash
git status
git diff > ~/ai-stock-arena-server-local-backup.patch
git fetch origin main
git reset --hard origin/main
bash deploy/oracle/deploy-update.sh
```

Use the forced reset only when server-local edits are understood and backed up.

## 10. Free Model Maintenance

Add more successful free models without replacing the selected set:

```bash
cd /opt/ai-stock-arena/current
bash scripts/linux/add-free-models.sh 10 40 popular
```

Run the weekly free/experimental sync manually:

```bash
cd /opt/ai-stock-arena/current
bash scripts/linux/sync-free-models.sh
```

## 11. Logs And Troubleshooting

```bash
free -h
df -h
uptime
sudo tail -n 100 /var/log/ai-stock-arena/api-error.log
sudo tail -n 100 /var/log/ai-stock-arena/dashboard-error.log
sudo tail -n 100 /var/log/ai-stock-arena/scheduler-error.log
```

Common symptoms:

- Streamlit shell loads but content is slow: check API endpoint timeouts and memory.
- `rankings: ReadTimeout`: the dashboard should show last known cached rankings and a stale timestamp.
- public IP HTTP fails while localhost works: check Oracle security rules and host `iptables`.
- gray Streamlit page: confirm nginx websocket proxy for `/_stcore/`.
