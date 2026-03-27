#!/usr/bin/env python3
"""
server.py — Dashboard HTTP/WebSocket local para o Deriv Bot.

Serve a pasta public/ e expõe:
  GET  /                      → index.html
  GET  /app.js | /style.css   → arquivos estáticos
  GET  /api/operacoes         → operacoes_log.csv como JSON
  GET  /api/ticks?limit=2000  → ticks.csv como JSON
  GET  /api/status            → estado do bot (running, pid, balance …)
  GET  /api/train_meta        → metadados do modelo treinado
  POST /api/command           → {action, args} — start / stop / clear_local_data
  WS   /ws                    → push em tempo real: ops, ticks, status

Modos de operação:
  1. Integrado (thread daemon lançada por pipeline.py) — use set_embedded()
  2. Standalone — python server.py (pode iniciar pipeline.py como subprocess)
"""

import asyncio
import csv
import os
import signal
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import (
    SYMBOL, CURRENCY,
    TICKS_CSV, OPERATIONS_LOG, DATASET_CSV,
    AI_MODEL_PATH, DURATION_MODEL_PATH, TRANSFORMER_MODEL_PATH,
)

_BASE_DIR = Path(__file__).parent
_PUBLIC   = _BASE_DIR / "public"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    asyncio.create_task(_broadcaster())
    yield


app = FastAPI(title="Deriv Bot Dashboard", docs_url=None, redoc_url=None, lifespan=_lifespan)

# ─────────────────────────────────────────────────────────────────
#  Estado global
# ─────────────────────────────────────────────────────────────────

_bot_process:       Optional[subprocess.Popen] = None   # subprocess (modo standalone)
_embedded_mode:     bool = False                         # True quando iniciado por pipeline.py
_stop_callback      = None                               # chamado ao pressionar Stop (embedded)
_active_ws:         Set[WebSocket] = set()               # websockets conectados

# Timestamps dos CSVs para detecção de mudança
_ops_mtime:   float = 0.0
_ticks_mtime: float = 0.0

# ─────────────────────────────────────────────────────────────────
#  API para integração com pipeline.py
# ─────────────────────────────────────────────────────────────────

def set_embedded(stop_callback=None) -> None:
    """Chamado por pipeline.py para indicar modo integrado."""
    global _embedded_mode, _stop_callback
    _embedded_mode = True
    _stop_callback = stop_callback


def start_server(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Inicia o servidor uvicorn (uso em thread ou standalone)."""
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")


# ─────────────────────────────────────────────────────────────────
#  Utilitários CSV
# ─────────────────────────────────────────────────────────────────

def _read_csv(path: str, limit: Optional[int] = None) -> list:
    """Lê um CSV e retorna lista de dicts (strings). Aplica limite às últimas N linhas."""
    p = _BASE_DIR / path
    if not p.exists() or p.stat().st_size == 0:
        return []
    rows = []
    with open(str(p), "r", newline="") as f:
        for row in csv.DictReader(f):
            rows.append(dict(row))
    return rows[-limit:] if limit and len(rows) > limit else rows


def _get_status() -> dict:
    running = False
    pid: Optional[int] = None

    if _embedded_mode:
        running = True
        pid = os.getpid()
    elif _bot_process is not None:
        running = _bot_process.poll() is None
        if running:
            pid = _bot_process.pid

    # Dados da última operação
    balance: Optional[str] = None
    last_action: Optional[str] = None
    symbol = SYMBOL
    currency = CURRENCY

    ops_path = _BASE_DIR / OPERATIONS_LOG
    if ops_path.exists() and ops_path.stat().st_size > 0:
        with open(str(ops_path), "r", newline="") as f:
            rows = list(csv.DictReader(f))
        if rows:
            last = rows[-1]
            balance    = last.get("balance_after")
            last_action = f"{last.get('direction', '')} {last.get('result', '')}"
            symbol     = last.get("symbol", SYMBOL)

    # Última vez que ticks.csv foi escrito ≈ último heartbeat
    ticks_path = _BASE_DIR / TICKS_CSV
    last_heartbeat: Optional[str] = None
    if ticks_path.exists():
        last_heartbeat = datetime.fromtimestamp(ticks_path.stat().st_mtime).isoformat()

    return {
        "running":        running,
        "pid":            pid,
        "balance":        balance,
        "balance_ok":     balance is not None,
        "symbol":         symbol,
        "currency":       currency,
        "last_heartbeat": last_heartbeat,
        "last_action":    last_action,
    }


def _get_train_meta() -> dict:
    meta: dict = {"train_count": None, "ticks_count": 0, "last_train": None}

    ticks_path = _BASE_DIR / TICKS_CSV
    if ticks_path.exists() and ticks_path.stat().st_size > 0:
        with open(str(ticks_path), "r") as f:
            meta["ticks_count"] = max(0, sum(1 for _ in f) - 1)

    model_path = _BASE_DIR / AI_MODEL_PATH
    if model_path.exists():
        meta["last_train"] = datetime.fromtimestamp(model_path.stat().st_mtime).isoformat()
        ops = _read_csv(OPERATIONS_LOG)
        meta["train_count"] = max(1, len(ops) // 50) if ops else 1

    return meta


# ─────────────────────────────────────────────────────────────────
#  Rotas HTTP
# ─────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(_PUBLIC / "index.html")


@app.get("/app.js")
async def serve_js():
    return FileResponse(_PUBLIC / "app.js", media_type="application/javascript")


@app.get("/style.css")
async def serve_css():
    return FileResponse(_PUBLIC / "style.css", media_type="text/css")


@app.get("/api/operacoes")
async def api_operacoes(limit: int = 500):
    return JSONResponse(_read_csv(OPERATIONS_LOG, limit))


@app.get("/api/ticks")
async def api_ticks(limit: int = 2000):
    return JSONResponse(_read_csv(TICKS_CSV, limit))


@app.get("/api/status")
async def api_status():
    return JSONResponse(_get_status())


@app.get("/api/train_meta")
async def api_train_meta():
    return JSONResponse(_get_train_meta())


# ─────────────────────────────────────────────────────────────────
#  Endpoint de comandos
# ─────────────────────────────────────────────────────────────────

class CommandRequest(BaseModel):
    action: str
    args:   dict = {}


@app.post("/api/command")
async def api_command(cmd: CommandRequest):
    global _bot_process

    if cmd.action == "start":
        if _embedded_mode:
            return JSONResponse({"ok": False, "error": "Bot já está rodando (modo integrado)"})
        if _bot_process and _bot_process.poll() is None:
            return JSONResponse({"ok": False, "error": "Bot já está rodando"})

        argv = [sys.executable, str(_BASE_DIR / "pipeline.py")]
        mode = cmd.args.get("mode", "demo")
        argv.append("--real" if mode == "real" else "--demo")

        for cli_flag, key in [
            ("--history-count",    "hist_count"),
            ("--min-ticks",        "min_ticks"),
            ("--retrain-interval", "retrain_min"),
        ]:
            if key in cmd.args:
                argv += [cli_flag, str(cmd.args[key])]
        for cli_flag, key in [
            ("--skip-collect",  "skip_collect"),
            ("--force-retrain", "force_retrain"),
            ("--no-scan",       "no_scan"),
        ]:
            if cmd.args.get(key):
                argv.append(cli_flag)

        # Redireciona saída do processo filho para evitar mistura no terminal
        _bot_process = subprocess.Popen(
            argv,
            cwd=str(_BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return JSONResponse({"ok": True, "pid": _bot_process.pid})

    if cmd.action == "stop":
        if _embedded_mode:
            if _stop_callback:
                _stop_callback()
                return JSONResponse({"ok": True})
            # Fallback: envia SIGINT ao processo pai
            os.kill(os.getpid(), signal.SIGINT)
            return JSONResponse({"ok": True})
        if _bot_process and _bot_process.poll() is None:
            _bot_process.terminate()
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False, "error": "Bot não está rodando"})

    if cmd.action == "clear_local_data":
        targets = [TICKS_CSV, OPERATIONS_LOG, DATASET_CSV,
                   AI_MODEL_PATH, DURATION_MODEL_PATH, TRANSFORMER_MODEL_PATH,
                   DATASET_CSV + ".tmp", AI_MODEL_PATH + ".new"]
        for rel in targets:
            p = _BASE_DIR / rel
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass
        return JSONResponse({"ok": True})

    return JSONResponse({"ok": False, "error": f"Ação desconhecida: {cmd.action}"})


# ─────────────────────────────────────────────────────────────────
#  WebSocket — push em tempo real
# ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    _active_ws.add(ws)
    try:
        # Envia estado inicial completo
        await ws.send_json({"type": "ops",        "data": _read_csv(OPERATIONS_LOG, 500)})
        await ws.send_json({"type": "ticks",       "data": _read_csv(TICKS_CSV, 2000)})
        await ws.send_json({"type": "status",      "data": _get_status()})
        await ws.send_json({"type": "train_meta",  "data": _get_train_meta()})

        # Mantém conexão viva (o broadcaster envia atualizações)
        while True:
            await asyncio.sleep(30)
            await ws.send_json({"type": "ping"})
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _active_ws.discard(ws)


async def _broadcast(msg: dict) -> None:
    """Envia mensagem JSON a todos os clientes WS conectados."""
    dead: Set[WebSocket] = set()
    for ws in list(_active_ws):
        try:
            await ws.send_json(msg)
        except Exception:
            dead.add(ws)
    _active_ws -= dead


async def _broadcaster() -> None:
    """
    Tarefa de background: monitora CSVs por mudança de mtime e envia
    dados atualizados a todos os clientes. Também envia status periódico.
    """
    global _ops_mtime, _ticks_mtime

    status_tick = 0
    while True:
        await asyncio.sleep(2)

        if not _active_ws:
            continue

        # Verifica operacoes_log.csv
        ops_path = _BASE_DIR / OPERATIONS_LOG
        if ops_path.exists():
            mtime = ops_path.stat().st_mtime
            if mtime > _ops_mtime:
                _ops_mtime = mtime
                await _broadcast({"type": "ops", "data": _read_csv(OPERATIONS_LOG, 500)})

        # Verifica ticks.csv
        ticks_path = _BASE_DIR / TICKS_CSV
        if ticks_path.exists():
            mtime = ticks_path.stat().st_mtime
            if mtime > _ticks_mtime:
                _ticks_mtime = mtime
                await _broadcast({"type": "ticks", "data": _read_csv(TICKS_CSV, 2000)})

        # Status a cada 5s (~2s * 2.5 ciclos ≈ 5s)
        status_tick += 1
        if status_tick >= 3:
            status_tick = 0
            await _broadcast({"type": "status", "data": _get_status()})



# ─────────────────────────────────────────────────────────────────
#  Entry point standalone
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    host, port = "0.0.0.0", 8080
    print(f"[DASHBOARD] Servidor em http://localhost:{port}")
    print(f"[DASHBOARD] Ctrl+C para encerrar")
    start_server(host, port)
