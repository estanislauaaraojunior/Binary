#!/usr/bin/env python3
"""
bot_agent.py — Agente de controle remoto via Firebase RTDB.

Mantém o status do bot atualizado no RTDB e executa os comandos de
start/stop enviados pelo dashboard web em tempo real.

Além do controle do bot, conecta ao WebSocket da Deriv para obter
o saldo real da conta e publicá-lo no RTDB em tempo real.

RTDB paths utilizados:
    bot_control/status    ← estado atual (running, pid, balance, currency, heartbeat)
    bot_control/commands  ← fila de comandos do dashboard

Pré-requisito Firebase Auth:
    1. Firebase Console → Authentication → Sign-in method → Email/Password (habilitar)
    2. Firebase Console → Authentication → Users → Add user (email + senha)
    3. Use essas credenciais no formulário de login do dashboard.

Uso:
    python bot_agent.py

    # Em segundo plano:
    nohup python bot_agent.py >> bot_agent.log 2>&1 &
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# ─── Caminhos ─────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
PIPELINE_PY = BASE_DIR / "pipeline.py"
PID_FILE    = BASE_DIR / "bot.pid"
LOG_FILE    = BASE_DIR / "pipeline.log"

RTDB_STATUS_PATH   = "bot_control/status"
RTDB_COMMANDS_PATH = "bot_control/commands"
HEARTBEAT_INTERVAL = 10  # segundos entre heartbeats
BALANCE_REFRESH_SEC = 30  # re-conecta ao Deriv WS a cada N seg para atualizar saldo

# Saldo mais recente obtido da Deriv (thread-safe via lock)
_balance_lock    = threading.Lock()
_deriv_balance   = 0.0
_deriv_currency  = "USD"
_balance_fetched = False  # True após a primeira busca bem-sucedida


# ─── Helpers ───────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _bot_pid() -> int:
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return 0


def _bot_running() -> bool:
    pid = _bot_pid()
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)   # sinal 0 = só verifica existência
        return True
    except (ProcessLookupError, PermissionError):
        PID_FILE.unlink(missing_ok=True)
        return False


# ─── Deriv WebSocket (busca de saldo) ──────────────────────────────

def _fetch_deriv_balance() -> None:
    """
    Conecta ao WebSocket da Deriv, autoriza o token, obtém o saldo
    e encerra a conexão. Executa em thread daemon.
    """
    global _deriv_balance, _deriv_currency, _balance_fetched
    try:
        import websocket as ws_module
        from config import APP_ID, TOKEN
    except ImportError as e:
        print(f"[AGENT] Aviso: websocket-client não instalado ({e}). Saldo não será buscado.")
        return

    ws_url = f"wss://ws.derivws.com/websockets/v3?app_id={APP_ID}"
    result = {}

    def on_message(ws, message):
        data = json.loads(message)
        if data.get("msg_type") == "authorize":
            ws.send(json.dumps({"balance": 1}))
        elif data.get("msg_type") == "balance":
            bal = data.get("balance", {})
            result["balance"]  = float(bal.get("balance", 0))
            result["currency"] = bal.get("currency", "USD")
            ws.close()

    def on_error(ws, error):
        print(f"[AGENT] Deriv WS erro: {error}")

    try:
        ws = ws_module.WebSocketApp(
            ws_url,
            on_open=lambda ws: ws.send(json.dumps({"authorize": TOKEN})),
            on_message=on_message,
            on_error=on_error,
        )
        ws.run_forever(ping_interval=20, ping_timeout=10)
    except Exception as e:
        print(f"[AGENT] Falha ao conectar Deriv: {e}")
        return

    if "balance" in result:
        with _balance_lock:
            _deriv_balance  = result["balance"]
            _deriv_currency = result["currency"]
            _balance_fetched = True
        print(f"[AGENT] Saldo Deriv: {_deriv_currency} {_deriv_balance:.2f}")


def _start_balance_thread() -> None:
    """Dispara a busca de saldo em thread daemon (não bloqueia o loop)."""
    t = threading.Thread(target=_fetch_deriv_balance, daemon=True)
    t.start()


# ─── Firebase ────────────────────────────────────────────────────────

def _init_firebase():
    """Inicializa firebase-admin e retorna referência raiz do RTDB."""
    try:
        from config import FIREBASE_CRED_PATH, FIREBASE_DB_URL, USE_FIREBASE
    except ImportError as e:
        print(f"[AGENT] Erro ao importar config.py: {e}")
        sys.exit(1)

    if not USE_FIREBASE:
        print("[AGENT] USE_FIREBASE=False em config.py — agente não pode iniciar.")
        sys.exit(1)

    try:
        import firebase_admin
        from firebase_admin import credentials, db as rtdb

        cred_path = str(BASE_DIR / FIREBASE_CRED_PATH) if not os.path.isabs(FIREBASE_CRED_PATH) \
                    else FIREBASE_CRED_PATH

        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})
        print(f"[AGENT] Firebase conectado: {FIREBASE_DB_URL}")
        return rtdb.reference("/")
    except Exception as e:
        print(f"[AGENT] Falha ao inicializar Firebase: {e}")
        sys.exit(1)


# ─── Ações ───────────────────────────────────────────────────────────

def write_status(root) -> None:
    """Publica estado atual do bot + saldo Deriv no RTDB."""
    running = _bot_running()
    with _balance_lock:
        bal  = _deriv_balance
        cur  = _deriv_currency
        fetched = _balance_fetched
    root.child(RTDB_STATUS_PATH).update({
        "running":        running,
        "pid":            _bot_pid() if running else 0,
        "last_heartbeat": _now_iso(),
        "balance":        round(bal, 2),
        "currency":       cur,
        "balance_ok":     fetched,
    })


def do_start(args: dict) -> dict:
    """Inicia pipeline.py usando o saldo real obtido da Deriv."""
    if _bot_running():
        return {"ok": False, "msg": "Bot já está em execução."}

    with _balance_lock:
        balance  = _deriv_balance if _balance_fetched else 1000.0
        fetched  = _balance_fetched

    if not fetched:
        print("[AGENT] Aviso: saldo Deriv não disponível ainda; usando 1000.0 como fallback.")

    mode        = args.get("mode", "demo")
    hist_count  = args.get("hist_count", 500)
    min_ticks   = args.get("min_ticks", 500)

    cmd = [sys.executable, str(PIPELINE_PY)]
    cmd += ["--demo" if mode == "demo" else "--real"]
    cmd += ["--balance",       str(round(balance, 2))]
    cmd += ["--history-count", str(int(hist_count))]
    cmd += ["--min-ticks",     str(int(min_ticks))]
    if args.get("skip_collect"):  cmd.append("--skip-collect")
    if args.get("force_retrain"): cmd.append("--force-retrain")
    if args.get("no_scan"):       cmd.append("--no-scan")

    try:
        log_fh = open(LOG_FILE, "a")
        proc = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdin=subprocess.PIPE if mode == "real" else subprocess.DEVNULL,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        if mode == "real":
            proc.stdin.write(b"sim\n")
            proc.stdin.flush()
            proc.stdin.close()
        PID_FILE.write_text(str(proc.pid))
        msg = f"Bot iniciado. PID={proc.pid} | Saldo={balance:.2f} {_deriv_currency}"
        print(f"[AGENT] {msg}")
        return {"ok": True, "msg": msg}
    except Exception as e:
        return {"ok": False, "msg": f"Erro ao iniciar: {e}"}


def do_stop() -> dict:
    """Para o pipeline.py via SIGTERM."""
    pid = _bot_pid()
    if pid <= 0 or not _bot_running():
        return {"ok": False, "msg": "Bot não está em execução."}
    try:
        os.kill(pid, signal.SIGTERM)
        PID_FILE.unlink(missing_ok=True)
        msg = f"Bot encerrado. PID={pid}"
        print(f"[AGENT] {msg}")
        return {"ok": True, "msg": msg}
    except Exception as e:
        return {"ok": False, "msg": f"Erro ao parar: {e}"}


# ─── Loop principal ────────────────────────────────────────────────────

def main():
    print("[AGENT] Iniciando bot_agent.py…")
    root = _init_firebase()

    # Busca o saldo imediatamente ao iniciar
    _start_balance_thread()

    write_status(root)
    print("[AGENT] Status publicado. Aguardando comandos (Ctrl+C para encerrar).")

    last_hb       = 0.0
    last_bal_fetch = 0.0

    while True:
        try:
            now = time.time()

            # ── Heartbeat + status ───────────────────────────────────
            if now - last_hb >= HEARTBEAT_INTERVAL:
                write_status(root)
                last_hb = now

            # ── Atualiza saldo periodicamente ───────────────────────
            if now - last_bal_fetch >= BALANCE_REFRESH_SEC:
                _start_balance_thread()
                last_bal_fetch = now

            # ── Processa comandos pendentes ─────────────────────────
            cmds = root.child(RTDB_COMMANDS_PATH).get()
            if cmds and isinstance(cmds, dict):
                for cmd_id, data in cmds.items():
                    if not isinstance(data, dict) or data.get("executed"):
                        continue

                    action = data.get("action", "")
                    sender = data.get("sent_by", "desconhecido")
                    print(f"[AGENT] Comando '{action}' de {sender}")

                    if action == "start":
                        result = do_start(data.get("args", {}))
                    elif action == "stop":
                        result = do_stop()
                    else:
                        result = {"ok": False, "msg": f"Ação desconhecida: {action}"}

                    # Remove o comando processado (não acumula lixo no RTDB)
                    root.child(f"{RTDB_COMMANDS_PATH}/{cmd_id}").delete()

                    # Registra o resultado no status
                    root.child(RTDB_STATUS_PATH).update({
                        "last_action":    f"{action}: {result['msg']}",
                        "last_action_at": _now_iso(),
                    })

                    # Atualiza status após a ação
                    time.sleep(1.5)
                    write_status(root)

            time.sleep(3)

        except KeyboardInterrupt:
            print("\n[AGENT] Encerrado pelo usuário.")
            break
        except Exception as e:
            print(f"[AGENT] Erro no loop: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
