# Streamlit Cloud Web Branch

This branch keeps the same Streamlit dashboard UI and points the web app at the
Oracle FastAPI backend by IP.

Default backend:

```text
http://138.2.49.114:8000
```

Streamlit Cloud app settings:

- Repository: `eljja/ai-stock-arena`
- Branch: `codex/streamlit-cloud-web`
- Main file path: `src/app/dashboard/main.py`
- Optional secret override:

```toml
API_BASE_URL = "http://138.2.49.114:8000"
```

The Oracle server must allow external HTTP access to that API address. This
branch does not change the Oracle server configuration.
