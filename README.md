# VoxelVitals

> Production-grade Minecraft server telemetry, latency tracking, and dynamic status badges for Java and Bedrock editions.

[![Python](https://img.shields.io/badge/Python-3.12-blue?style=flat&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/tests-23%20passed-10b981?style=flat)](https://github.com/soroka-ilya/voxelvitals)
[![License](https://img.shields.io/badge/license-MIT-slate?style=flat)](LICENSE)

---

## Overview

VoxelVitals provides real-time health indicators, latency analytics, and 24-hour player telemetry for Minecraft multiplayer networks. It features a dark-themed UI built with FastAPI, Jinja2, HTMX, and Tailwind CSS, plus dynamic vector SVG status badges styled after Shields.io for embedding in repository READMEs and community websites.

### Key Capabilities

- **Dual Edition Support**: Queries both Java Edition (Server List Ping via TCP) and Bedrock Edition (RakNet query via UDP) with automatic DNS SRV record resolution.
- **MOTD Formatting Engine**: Parses legacy color codes (`§0`-`§f`), format styles (`§l`, `§o`, `§n`), and modern hex codes (`&#RRGGBB`, `§#RRGGBB`) with strict HTML XSS escaping.
- **Dynamic SVG Badges**: Generates responsive Shields.io-compatible vector status badges (`/api/badge/{address}.svg`) with HTTP caching headers.
- **Time-Series Telemetry**: Retains 24-hour historical snapshots in SQLite with automated periodic background polling and retention pruning.
- **Clean Interactive UI**: Search without full-page reload powered by HTMX, realistic skeleton loaders, and dark-mode Chart.js graphs.


---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python 3.12), Starlette, Uvicorn |
| Protocol Query | `mcstatus` (async Java & Bedrock networking) |
| Persistence | SQLite via `aiosqlite` (WAL mode enabled) |
| Frontend | Jinja2 templates, Tailwind CSS, HTMX 1.9, Chart.js |
| Testing | Pytest, Pytest-Asyncio, HTTPX AsyncClient |

---

## Architecture

```
[Browser / Webhook / README Badge]
               |
               v
     +-------------------+
     | FastAPI Router    |
     +---------+---------+
               |
     +---------+---------+
     | Services Layer    |
     |  - Pinger Service | <----> [Minecraft Server List Ping / RakNet]
     |  - MOTD Parser    |
     |  - SVG Generator  |
     +---------+---------+
               |
     +---------+---------+
     | Repository Layer  |
     +---------+---------+
               |
     +---------+---------+
     | SQLite (WAL Mode) |
     +-------------------+
```


---

## Quickstart

### 1. Clone & Install Dependencies

```bash
git clone https://github.com/soroka-ilya/voxelvitals.git
cd voxelvitals

python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 2. Run the Application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

### 3. Run the Test Suite

```bash
pytest -v
```

---

## API Endpoints

- `GET /`: Explorer home page with search and tracked nodes.
- `GET /server/{address}`: Detailed telemetry graphs, MOTD, player sample.
- `GET /api/status/{address}`: Full JSON metadata for a server (`?bedrock=true|false`).
- `GET /api/history/{address}`: Time-series telemetry points (`?hours=24`).
- `GET /api/badge/{address}.svg`: Dynamic Shields.io-compatible vector status badge.
- `GET /partials/server-card`: HTMX partial card for instant asynchronous queries.
- `GET /docs`: Interactive OpenAPI documentation (Swagger UI).
