#!/usr/bin/env bash
# ============================================================
#  agente.sh — gerencia o bot_agent como serviço systemd
#
#  Uso:
#    ./agente.sh status    → mostra estado + últimas linhas do log
#    ./agente.sh start     → inicia o agente
#    ./agente.sh stop      → para o agente
#    ./agente.sh restart   → reinicia o agente
#    ./agente.sh logs      → acompanha o log em tempo real (Ctrl+C para sair)
#    ./agente.sh install   → (re)instala e habilita o serviço systemd
# ============================================================

SERVICE="bot-agent.service"
LOG_FILE="$(dirname "$0")/bot_agent.log"

case "${1:-status}" in

  start)
    systemctl --user start "$SERVICE"
    sleep 1
    systemctl --user is-active "$SERVICE" && echo "✅  Agente iniciado." || echo "❌  Falha ao iniciar. Execute: ./agente.sh logs"
    ;;

  stop)
    systemctl --user stop "$SERVICE"
    echo "⏹  Agente parado."
    ;;

  restart)
    systemctl --user restart "$SERVICE"
    sleep 1
    systemctl --user is-active "$SERVICE" && echo "🔄  Agente reiniciado." || echo "❌  Falha. Execute: ./agente.sh logs"
    ;;

  status)
    echo "══════════════════════════════════════════════"
    systemctl --user status "$SERVICE" --no-pager -l | head -20
    echo "══════════════════════════════════════════════"
    if [ -f "$LOG_FILE" ]; then
      echo "Últimas linhas do log:"
      tail -20 "$LOG_FILE"
    fi
    ;;

  logs)
    echo "Acompanhando log (Ctrl+C para sair)…"
    tail -f "$LOG_FILE"
    ;;

  install)
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"
    AGENT_PY="$SCRIPT_DIR/bot_agent.py"
    ENV_FILE="$SCRIPT_DIR/.env"

    if [ ! -f "$VENV_PYTHON" ]; then
      echo "❌  .venv não encontrado em $SCRIPT_DIR. Rode: python3 -m venv .venv && pip install -r requirements.txt"
      exit 1
    fi

    mkdir -p ~/.config/systemd/user

    cat > ~/.config/systemd/user/bot-agent.service << EOF
[Unit]
Description=Deriv Bot Agent (controle remoto via dashboard)
Documentation=https://standeriv.web.app
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${SCRIPT_DIR}
EnvironmentFile=${ENV_FILE}
Environment=PYTHONUNBUFFERED=1
ExecStart=${VENV_PYTHON} ${AGENT_PY}
Restart=on-failure
RestartSec=15
StandardOutput=append:${SCRIPT_DIR}/bot_agent.log
StandardError=append:${SCRIPT_DIR}/bot_agent.log

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable bot-agent.service
    loginctl enable-linger "$USER"
    systemctl --user start bot-agent.service
    sleep 2
    systemctl --user is-active "$SERVICE" && echo "✅  Serviço instalado e ativo." || echo "❌  Falha. Verifique com: ./agente.sh logs"
    ;;

  *)
    echo "Uso: $0 {start|stop|restart|status|logs|install}"
    exit 1
    ;;
esac
