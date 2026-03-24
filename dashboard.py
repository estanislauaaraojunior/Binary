#!/home/stanis/Repositórios/Binary/.venv/bin/python3
"""
dashboard.py — Dashboard de monitoramento do Bot Deriv.

Uso:
    streamlit run dashboard.py

Lê os CSVs locais em tempo real (operacoes_log.csv e ticks.csv).
Auto-refresh configurável na sidebar (padrão: 30 s).
Somente leitura — não interfere no bot em execução.
"""

import os
import sys
from pathlib import Path

# ── Auto-lançamento: detecta se NÃO está rodando via 'streamlit run' ──────────
# get_script_run_ctx() retorna None fora do runtime do Streamlit (ex: python3 script.py)
# e retorna um contexto válido quando o Streamlit está gerenciando a execução.
try:
    from streamlit.runtime.scriptrunner import get_script_run_ctx as _get_ctx
    if _get_ctx() is None:
        _st = str(Path(sys.executable).parent / "streamlit")
        os.execv(_st, [_st, "run", __file__] + sys.argv[1:])
    del _get_ctx
except ImportError:
    pass  # deixa crashar com mensagem de 'streamlit não instalado'
# ─────────────────────────────────────────────────────────────────────────────

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ─── Caminhos ─────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
OPS_CSV   = BASE_DIR / "operacoes_log.csv"
TICKS_CSV = BASE_DIR / "ticks.csv"

# ─── Constantes de estilo ─────────────────────────────────────────────────────
CLR_WIN   = "#00C9A7"   # verde-teal
CLR_LOSS  = "#FF4B4B"   # vermelho
CLR_NEUT  = "#8B949E"   # cinza
CLR_BG    = "#0D1117"
CLR_CARD  = "#161B22"
CLR_EMA9  = "#F6C90E"
CLR_EMA21 = "#00AAFF"
CLR_BB    = "rgba(255,255,255,0.18)"


# ══════════════════════════════════════════════════════════════════════════════
#  Carregamento de dados
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=15)
def load_ops() -> pd.DataFrame:
    """Carrega e tipifica operacoes_log.csv."""
    if not OPS_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(OPS_CSV, parse_dates=["timestamp"])
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


@st.cache_data(ttl=10)
def load_ticks(n: int = 500) -> pd.DataFrame:
    """Carrega os últimos n ticks."""
    if not TICKS_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(TICKS_CSV, parse_dates=["datetime"])
    return df.tail(n).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers de cálculo
# ══════════════════════════════════════════════════════════════════════════════

def _ema_series(prices: pd.Series, period: int) -> pd.Series:
    return prices.ewm(span=period, adjust=False).mean()


def _bollinger(prices: pd.Series, period: int = 20, std: float = 2.0):
    mid  = prices.rolling(period).mean()
    band = prices.rolling(period).std()
    return mid, mid + std * band, mid - std * band


def _kpi(label: str, value: str, delta: str = "", color: str = CLR_NEUT) -> None:
    st.markdown(
        f"""
        <div style="
            background:{CLR_CARD};border-radius:10px;padding:16px 20px;
            border-left:4px solid {color};margin-bottom:4px;">
          <div style="color:{CLR_NEUT};font-size:0.75rem;text-transform:uppercase;
                      letter-spacing:0.08em;">{label}</div>
          <div style="font-size:1.6rem;font-weight:700;color:#E6EDF3;
                      line-height:1.2;">{value}</div>
          {'<div style="color:' + color + ';font-size:0.82rem;">' + delta + '</div>' if delta else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:#fff;'
        f'padding:2px 10px;border-radius:12px;font-size:0.78rem;'
        f'font-weight:600;">{text}</span>'
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Abas
# ══════════════════════════════════════════════════════════════════════════════

def tab_overview(df: pd.DataFrame) -> None:
    """Aba 1 — Visão Geral."""
    if df.empty:
        st.info("Nenhuma operação registrada ainda. Inicie o bot e aguarde o primeiro trade.")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    df_today = df[df["timestamp"].dt.strftime("%Y-%m-%d") == today_str]

    total_ops   = len(df)
    wins        = (df["result"] == "WIN").sum()
    losses      = (df["result"] == "LOSS").sum()
    win_rate    = wins / total_ops * 100 if total_ops else 0.0
    total_profit= df["profit"].sum()
    last_bal    = df["balance_after"].iloc[-1]
    init_bal    = df["balance_before"].iloc[0]
    drawdown    = df["drawdown_pct"].max() if "drawdown_pct" in df.columns else 0.0
    ops_today   = len(df_today)
    profit_today= df_today["profit"].sum() if not df_today.empty else 0.0

    # ── Status do bot ─────────────────────────────────────────────────────────
    last_ts   = df["timestamp"].iloc[-1].strftime("%d/%m/%Y %H:%M:%S")
    last_sym  = df["symbol"].iloc[-1]
    consec    = int(df["consec_losses"].iloc[-1]) if "consec_losses" in df.columns else 0
    cond      = df["market_condition"].iloc[-1] if "market_condition" in df.columns else "—"
    cond_color= CLR_WIN if cond == "trending" else "#F6C90E"

    st.markdown(
        f"""
        <div style="background:{CLR_CARD};border-radius:10px;padding:14px 22px;
                    display:flex;gap:28px;flex-wrap:wrap;margin-bottom:20px;">
          <span>📡 <b>Símbolo:</b> {last_sym}</span>
          <span>🕐 <b>Última op.:</b> {last_ts}</span>
          <span>📊 <b>Mercado:</b> &nbsp;{_badge(cond, cond_color)}</span>
          <span>🔴 <b>Losses consec.:</b> {consec}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── KPI cards ─────────────────────────────────────────────────────────────
    cols = st.columns(5)
    with cols[0]:
        _kpi("Saldo Atual", f"${last_bal:,.2f}",
             f"Inicial: ${init_bal:,.2f}", CLR_WIN if last_bal >= init_bal else CLR_LOSS)
    with cols[1]:
        clr = CLR_WIN if total_profit >= 0 else CLR_LOSS
        _kpi("P/L Total", f"${total_profit:+,.2f}",
             f"Hoje: ${profit_today:+,.2f}", clr)
    with cols[2]:
        clr = CLR_WIN if win_rate >= 55 else (CLR_LOSS if win_rate < 45 else CLR_NEUT)
        _kpi("Win Rate", f"{win_rate:.1f}%",
             f"{wins}W / {losses}L", clr)
    with cols[3]:
        _kpi("Operações Hoje", str(ops_today),
             f"Total: {total_ops}", CLR_NEUT)
    with cols[4]:
        clr = CLR_LOSS if drawdown > 15 else (CLR_WIN if drawdown < 5 else "#F6C90E")
        _kpi("Drawdown Máx.", f"{drawdown:.1f}%", "", clr)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Curva de saldo ────────────────────────────────────────────────────────
    fig_bal = go.Figure()
    fig_bal.add_trace(go.Scatter(
        x=df["timestamp"], y=df["balance_after"],
        mode="lines", name="Saldo",
        line=dict(color=CLR_WIN, width=2),
        fill="tozeroy",
        fillcolor="rgba(0,201,167,0.08)",
    ))
    fig_bal.add_hline(y=init_bal, line_dash="dot",
                      line_color=CLR_NEUT, annotation_text="Saldo inicial")
    fig_bal.update_layout(
        title="Curva de Saldo", height=300,
        margin=dict(l=0, r=0, t=40, b=0),
        paper_bgcolor=CLR_BG, plot_bgcolor=CLR_BG,
        xaxis=dict(showgrid=False, color=CLR_NEUT),
        yaxis=dict(gridcolor="#21262D", color=CLR_NEUT),
        legend=dict(bgcolor=CLR_CARD),
    )
    st.plotly_chart(fig_bal, use_container_width=True)

    # ── Últimas 10 operações ───────────────────────────────────────────────────
    st.subheader("Últimas Operações")
    last10 = df.tail(10).iloc[::-1].copy()

    def _fmt_row(row):
        badge  = _badge("WIN", CLR_WIN) if row["result"] == "WIN" else _badge("LOSS", CLR_LOSS)
        profit = f'<span style="color:{"#00C9A7" if row["profit"] > 0 else "#FF4B4B"};">' \
                 f'${row["profit"]:+.2f}</span>'
        ts = row["timestamp"].strftime("%d/%m %H:%M") if not pd.isna(row["timestamp"]) else "—"
        return (
            f"<tr style='border-bottom:1px solid #21262D'>"
            f"<td>{ts}</td>"
            f"<td>{row.get('symbol','—')}</td>"
            f"<td>{'🔺' if row['direction']=='BUY' else '🔻'} {row['direction']}</td>"
            f"<td>${row['stake']:.2f}</td>"
            f"<td>{row['duration']}t</td>"
            f"<td>{badge}</td>"
            f"<td>{profit}</td>"
            f"<td>{row.get('ai_confidence',0):.2f}</td>"
            f"</tr>"
        )

    rows_html = "\n".join(_fmt_row(r) for _, r in last10.iterrows())
    st.markdown(
        f"""
        <div style="overflow-x:auto;">
        <table style="width:100%;border-collapse:collapse;font-size:0.85rem;">
          <thead><tr style="color:{CLR_NEUT};text-align:left;border-bottom:2px solid #30363D;">
            <th>Hora</th><th>Símbolo</th><th>Direção</th>
            <th>Stake</th><th>Dur.</th><th>Resultado</th>
            <th>Lucro</th><th>AI Conf.</th>
          </tr></thead>
          <tbody>{rows_html}</tbody>
        </table></div>
        """,
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────

def tab_historico(df: pd.DataFrame) -> None:
    """Aba 2 — Histórico de Trades."""
    if df.empty:
        st.info("Nenhuma operação registrada ainda.")
        return

    # ── Filtros ───────────────────────────────────────────────────────────────
    st.subheader("Filtros")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        symbols = ["Todos"] + sorted(df["symbol"].unique().tolist())
        sym_sel = st.selectbox("Símbolo", symbols)
    with col2:
        dir_sel = st.selectbox("Direção", ["Todas", "BUY", "SELL"])
    with col3:
        res_sel = st.selectbox("Resultado", ["Todos", "WIN", "LOSS"])
    with col4:
        min_dt = df["timestamp"].min().date()
        max_dt = df["timestamp"].max().date()
        date_range = st.date_input("Período", value=(min_dt, max_dt),
                                   min_value=min_dt, max_value=max_dt)

    mask = pd.Series(True, index=df.index)
    if sym_sel != "Todos":
        mask &= df["symbol"] == sym_sel
    if dir_sel != "Todas":
        mask &= df["direction"] == dir_sel
    if res_sel != "Todos":
        mask &= df["result"] == res_sel
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        mask &= df["timestamp"].dt.date >= date_range[0]
        mask &= df["timestamp"].dt.date <= date_range[1]

    dff = df[mask].copy()

    st.caption(f"{len(dff)} operações filtradas de {len(df)} totais")

    # ── Gráficos lado a lado ─────────────────────────────────────────────────
    c1, c2 = st.columns(2)

    with c1:
        by_day = (
            dff.groupby([dff["timestamp"].dt.date, "result"])
               .size().reset_index(name="count")
        )
        if not by_day.empty:
            fig_day = px.bar(
                by_day, x="timestamp", y="count", color="result",
                color_discrete_map={"WIN": CLR_WIN, "LOSS": CLR_LOSS},
                title="Operações por Dia",
                labels={"timestamp": "Data", "count": "Qtd", "result": ""},
            )
            fig_day.update_layout(
                paper_bgcolor=CLR_BG, plot_bgcolor=CLR_BG,
                margin=dict(l=0, r=0, t=40, b=0),
                xaxis=dict(showgrid=False, color=CLR_NEUT),
                yaxis=dict(gridcolor="#21262D", color=CLR_NEUT),
                legend=dict(bgcolor=CLR_CARD),
            )
            st.plotly_chart(fig_day, use_container_width=True)

    with c2:
        if "ai_confidence" in dff.columns:
            fig_sc = px.scatter(
                dff, x="ai_confidence", y="profit",
                color="result",
                color_discrete_map={"WIN": CLR_WIN, "LOSS": CLR_LOSS},
                title="AI Confidence × Lucro",
                labels={"ai_confidence": "Confiança IA", "profit": "Lucro (USD)",
                        "result": ""},
                opacity=0.75,
            )
            fig_sc.add_hline(y=0, line_dash="dot", line_color=CLR_NEUT)
            fig_sc.update_layout(
                paper_bgcolor=CLR_BG, plot_bgcolor=CLR_BG,
                margin=dict(l=0, r=0, t=40, b=0),
                xaxis=dict(showgrid=False, color=CLR_NEUT),
                yaxis=dict(gridcolor="#21262D", color=CLR_NEUT),
                legend=dict(bgcolor=CLR_CARD),
            )
            st.plotly_chart(fig_sc, use_container_width=True)

    # ── Lucro acumulado filtrado ──────────────────────────────────────────────
    dff = dff.sort_values("timestamp")
    dff["profit_cum"] = dff["profit"].cumsum()
    fig_cum = go.Figure()
    fig_cum.add_trace(go.Scatter(
        x=dff["timestamp"], y=dff["profit_cum"],
        mode="lines", name="P/L acum.",
        line=dict(color="#00AAFF", width=2),
        fill="tozeroy",
        fillcolor="rgba(0,170,255,0.07)",
    ))
    fig_cum.add_hline(y=0, line_dash="dot", line_color=CLR_NEUT)
    fig_cum.update_layout(
        title="Lucro/Prejuízo Acumulado (filtrado)", height=260,
        margin=dict(l=0, r=0, t=40, b=0),
        paper_bgcolor=CLR_BG, plot_bgcolor=CLR_BG,
        xaxis=dict(showgrid=False, color=CLR_NEUT),
        yaxis=dict(gridcolor="#21262D", color=CLR_NEUT),
    )
    st.plotly_chart(fig_cum, use_container_width=True)

    # ── Tabela completa ───────────────────────────────────────────────────────
    st.subheader("Tabela Completa")
    show_cols = [
        "timestamp", "symbol", "direction", "stake", "duration",
        "result", "profit", "balance_after",
        "rsi", "adx", "macd_hist",
        "ai_confidence", "ai_score",
        "market_condition",
    ]
    show_cols = [c for c in show_cols if c in dff.columns]
    st.dataframe(
        dff[show_cols].style
            .map(lambda v: f"color:{CLR_WIN}" if v == "WIN" else
                           f"color:{CLR_LOSS}" if v == "LOSS" else "",
                 subset=["result"])
            .format({"profit": "${:+.2f}", "balance_after": "${:,.2f}",
                     "rsi": "{:.1f}", "adx": "{:.1f}",
                     "ai_confidence": "{:.3f}", "ai_score": "{:.3f}",
                     "stake": "${:.2f}", "macd_hist": "{:.5f}"}),
        use_container_width=True,
        height=380,
    )


# ──────────────────────────────────────────────────────────────────────────────

def tab_tecnico(df: pd.DataFrame, ticks: pd.DataFrame) -> None:
    """Aba 3 — Análise Técnica."""
    st.subheader("Gráfico de Preços ao Vivo")

    if ticks.empty:
        st.warning("ticks.csv não encontrado ou vazio.")
    else:
        prices = ticks["price"]
        times  = ticks["datetime"]
        ema9   = _ema_series(prices, 9)
        ema21  = _ema_series(prices, 21)
        bb_mid, bb_up, bb_lo = _bollinger(prices)

        fig_px = go.Figure()

        # Bollinger fill
        fig_px.add_trace(go.Scatter(
            x=pd.concat([times, times.iloc[::-1]]),
            y=pd.concat([bb_up, bb_lo.iloc[::-1]]),
            fill="toself", fillcolor=CLR_BB,
            line=dict(color="rgba(0,0,0,0)"),
            name="Bollinger Band",
        ))
        # Price
        fig_px.add_trace(go.Scatter(
            x=times, y=prices, mode="lines", name="Preço",
            line=dict(color="#E6EDF3", width=1.5),
        ))
        # EMAs
        fig_px.add_trace(go.Scatter(
            x=times, y=ema9, mode="lines", name="EMA 9",
            line=dict(color=CLR_EMA9, width=1.2, dash="solid"),
        ))
        fig_px.add_trace(go.Scatter(
            x=times, y=ema21, mode="lines", name="EMA 21",
            line=dict(color=CLR_EMA21, width=1.2, dash="solid"),
        ))
        # BB mid
        fig_px.add_trace(go.Scatter(
            x=times, y=bb_mid, mode="lines", name="BB Mid",
            line=dict(color=CLR_NEUT, width=1, dash="dot"),
        ))

        # Marcadores de trade sobre o gráfico
        if not df.empty:
            ops_in_range = df[
                (df["timestamp"] >= times.min()) &
                (df["timestamp"] <= times.max())
            ]
            if not ops_in_range.empty:
                wins_  = ops_in_range[ops_in_range["result"] == "WIN"]
                losses_= ops_in_range[ops_in_range["result"] == "LOSS"]
                for subset, color, symbol_mk, name in [
                    (wins_,  CLR_WIN,  "triangle-up",   "WIN"),
                    (losses_,CLR_LOSS, "triangle-down",  "LOSS"),
                ]:
                    if not subset.empty:
                        merge = pd.merge_asof(
                            subset.sort_values("timestamp"),
                            ticks[["datetime","price"]].sort_values("datetime"),
                            left_on="timestamp", right_on="datetime",
                        )
                        if not merge.empty:
                            fig_px.add_trace(go.Scatter(
                                x=merge["timestamp"], y=merge["price"],
                                mode="markers", name=name,
                                marker=dict(color=color, symbol=symbol_mk, size=10),
                            ))

        fig_px.update_layout(
            height=420, margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor=CLR_BG, plot_bgcolor=CLR_BG,
            xaxis=dict(showgrid=False, color=CLR_NEUT),
            yaxis=dict(gridcolor="#21262D", color=CLR_NEUT),
            legend=dict(bgcolor=CLR_CARD, orientation="h", y=-0.22),
        )
        st.plotly_chart(fig_px, use_container_width=True)

    # ── Gauges da última operação ─────────────────────────────────────────────
    if not df.empty:
        st.subheader("Indicadores — Última Operação")
        last = df.iloc[-1]

        rsi_val  = float(last.get("rsi",  50))
        adx_val  = float(last.get("adx",  0))
        macd_val = float(last.get("macd_hist", 0))

        gc1, gc2, gc3 = st.columns(3)

        def _gauge(val, title, mn, mx, thresholds, colors, fmt=".1f"):
            steps = [
                dict(range=[thresholds[i], thresholds[i+1]], color=colors[i])
                for i in range(len(colors))
            ]
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=val,
                number=dict(valueformat=fmt, font=dict(color="#E6EDF3", size=28)),
                title=dict(text=title, font=dict(color=CLR_NEUT, size=13)),
                gauge=dict(
                    axis=dict(range=[mn, mx], tickcolor=CLR_NEUT,
                               tickfont=dict(color=CLR_NEUT)),
                    bar=dict(color="#FFFFFF"),
                    bgcolor=CLR_CARD,
                    bordercolor=CLR_BG,
                    steps=steps,
                ),
            ))
            fig.update_layout(
                height=200, margin=dict(l=20, r=20, t=40, b=10),
                paper_bgcolor=CLR_BG,
            )
            return fig

        with gc1:
            fig_rsi = _gauge(
                rsi_val, "RSI", 0, 100,
                [0, 35, 65, 100],
                ["rgba(255,75,75,0.5)", "rgba(0,201,167,0.45)", "rgba(255,75,75,0.5)"],
            )
            st.plotly_chart(fig_rsi, use_container_width=True)

        with gc2:
            fig_adx = _gauge(
                adx_val, "ADX (Tendência)", 0, 60,
                [0, 20, 40, 60],
                ["rgba(255,75,75,0.4)", "rgba(246,201,14,0.5)", "rgba(0,201,167,0.55)"],
            )
            st.plotly_chart(fig_adx, use_container_width=True)

        with gc3:
            # MACD Histogram como barra simples
            fig_macd = go.Figure(go.Indicator(
                mode="number+delta",
                value=macd_val,
                number=dict(valueformat=".5f", font=dict(color="#E6EDF3", size=22)),
                delta=dict(reference=0, relative=False,
                           increasing=dict(color=CLR_WIN),
                           decreasing=dict(color=CLR_LOSS)),
                title=dict(text="MACD Histogram", font=dict(color=CLR_NEUT, size=13)),
            ))
            fig_macd.update_layout(
                height=200, margin=dict(l=20, r=20, t=40, b=10),
                paper_bgcolor=CLR_BG,
            )
            st.plotly_chart(fig_macd, use_container_width=True)

        # Badge market condition
        cond = last.get("market_condition", "—")
        cond_color = CLR_WIN if cond == "trending" else "#F6C90E"
        st.markdown(
            f"Condição de Mercado: {_badge(str(cond).upper(), cond_color)}",
            unsafe_allow_html=True,
        )


# ──────────────────────────────────────────────────────────────────────────────

def tab_ia_risco(df: pd.DataFrame) -> None:
    """Aba 4 — IA & Risco."""
    if df.empty:
        st.info("Nenhuma operação registrada ainda.")
        return

    # ── Métricas gerais de IA ─────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        avg_conf = df["ai_confidence"].mean() if "ai_confidence" in df else 0.0
        _kpi("AI Confidence Médio", f"{avg_conf:.3f}", "", CLR_WIN if avg_conf >= 0.6 else CLR_NEUT)
    with col2:
        avg_score = df["ai_score"].mean() if "ai_score" in df else 0.0
        _kpi("AI Score Médio", f"{avg_score:.3f}", "", CLR_WIN if avg_score >= 0.6 else CLR_NEUT)
    with col3:
        last_wr = df["win_rate_recent"].iloc[-1] if "win_rate_recent" in df.columns else 0.0
        clr = CLR_WIN if last_wr >= 55 else (CLR_LOSS if last_wr < 40 else "#F6C90E")
        _kpi("Win Rate Recente", f"{last_wr:.1f}%", "(últimas operações)", clr)
    with col4:
        max_dd = df["drawdown_pct"].max() if "drawdown_pct" in df.columns else 0.0
        clr = CLR_LOSS if max_dd > 15 else (CLR_WIN if max_dd < 5 else "#F6C90E")
        _kpi("Drawdown Máximo", f"{max_dd:.1f}%", "", clr)

    st.markdown("<br>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    with c1:
        # Win rate por faixa de AI Confidence
        if "ai_confidence" in df.columns:
            df_ia = df.copy()
            df_ia["conf_bin"] = pd.cut(
                df_ia["ai_confidence"],
                bins=[0.0, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 1.01],
                labels=["≤55%","55-60%","60-65%","65-70%","70-75%","75-80%",">80%"],
                right=False,
            )
            wr_bin = (
                df_ia.groupby("conf_bin", observed=True)
                .apply(lambda g: (g["result"] == "WIN").mean() * 100)
                .reset_index(name="win_rate")
            )
            fig_wr = px.bar(
                wr_bin, x="conf_bin", y="win_rate",
                text_auto=".1f",
                title="Win Rate por Faixa de AI Confidence",
                labels={"conf_bin": "Faixa de Confiança", "win_rate": "Win Rate (%)"},
                color="win_rate",
                color_continuous_scale=[(0,"#FF4B4B"),(0.5,"#F6C90E"),(1,"#00C9A7")],
                range_color=[0, 100],
            )
            fig_wr.update_layout(
                paper_bgcolor=CLR_BG, plot_bgcolor=CLR_BG,
                margin=dict(l=0, r=0, t=40, b=0),
                xaxis=dict(showgrid=False, color=CLR_NEUT),
                yaxis=dict(gridcolor="#21262D", color=CLR_NEUT, range=[0,100]),
                coloraxis_showscale=False,
            )
            st.plotly_chart(fig_wr, use_container_width=True)

    with c2:
        # Distribuição WIN x LOSS por Direção
        fig_dir = px.histogram(
            df, x="direction", color="result",
            color_discrete_map={"WIN": CLR_WIN, "LOSS": CLR_LOSS},
            barmode="group",
            title="WIN / LOSS por Direção",
            labels={"direction": "Direção", "count": "Qtd", "result": ""},
        )
        fig_dir.update_layout(
            paper_bgcolor=CLR_BG, plot_bgcolor=CLR_BG,
            margin=dict(l=0, r=0, t=40, b=0),
            xaxis=dict(showgrid=False, color=CLR_NEUT),
            yaxis=dict(gridcolor="#21262D", color=CLR_NEUT),
            legend=dict(bgcolor=CLR_CARD),
        )
        st.plotly_chart(fig_dir, use_container_width=True)

    # ── Timelines de risco ────────────────────────────────────────────────────
    st.subheader("Evolução de Risco")

    df_sorted = df.sort_values("timestamp")

    fig_risk = go.Figure()
    if "drawdown_pct" in df_sorted.columns:
        fig_risk.add_trace(go.Scatter(
            x=df_sorted["timestamp"], y=df_sorted["drawdown_pct"],
            mode="lines", name="Drawdown (%)",
            line=dict(color=CLR_LOSS, width=2),
            fill="tozeroy", fillcolor="rgba(255,75,75,0.08)",
            yaxis="y1",
        ))
    if "win_rate_recent" in df_sorted.columns:
        fig_risk.add_trace(go.Scatter(
            x=df_sorted["timestamp"], y=df_sorted["win_rate_recent"],
            mode="lines", name="Win Rate Recente (%)",
            line=dict(color=CLR_WIN, width=2, dash="dot"),
            yaxis="y2",
        ))
    if "consec_losses" in df_sorted.columns:
        fig_risk.add_trace(go.Bar(
            x=df_sorted["timestamp"], y=df_sorted["consec_losses"],
            name="Losses Consec.",
            marker_color="#F6C90E",
            opacity=0.6,
            yaxis="y1",
        ))

    fig_risk.add_hline(y=40, line=dict(color=CLR_LOSS, dash="dash", width=1),
                        annotation_text="Win Rate Mín. 40%", annotation_yref="y2",
                        yref="y2")
    fig_risk.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor=CLR_BG, plot_bgcolor=CLR_BG,
        xaxis=dict(showgrid=False, color=CLR_NEUT),
        yaxis=dict(gridcolor="#21262D", color=CLR_NEUT, title="Drawdown / Losses"),
        yaxis2=dict(overlaying="y", side="right", color=CLR_NEUT,
                    title="Win Rate (%)", range=[0, 100]),
        legend=dict(bgcolor=CLR_CARD, orientation="h", y=-0.28),
    )
    st.plotly_chart(fig_risk, use_container_width=True)

    # ── Alertas ───────────────────────────────────────────────────────────────
    st.subheader("Alertas de Risco")
    alerts = []

    if not df.empty:
        last = df.iloc[-1]
        wr   = float(last.get("win_rate_recent", 100))
        dd   = float(last.get("drawdown_pct", 0))
        cl   = int(last.get("consec_losses", 0))

        if wr < 40:
            alerts.append(("🔴 Win rate recente abaixo de 40% — considere retreinar o modelo.", "error"))
        if dd > 15:
            alerts.append((f"🔴 Drawdown atual: {dd:.1f}% — próximo do stop diário.", "error"))
        if cl >= 3:
            alerts.append((f"🟡 {cl} losses consecutivos — bot pode estar em pausa automática.", "warning"))
        if wr < 55 and wr >= 40:
            alerts.append(("🟡 Win rate recente abaixo de 55% — monitorar desempenho.", "warning"))

    if alerts:
        for msg, kind in alerts:
            if kind == "error":
                st.error(msg)
            else:
                st.warning(msg)
    else:
        st.success("✅ Todos os indicadores de risco dentro dos limites normais.")


# ══════════════════════════════════════════════════════════════════════════════
#  App principal
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    st.set_page_config(
        page_title="Deriv Bot Dashboard",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ── CSS global ─────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <style>
          .stApp {{ background-color:{CLR_BG}; }}
          section[data-testid="stSidebar"] {{ background-color:{CLR_CARD}; }}
          div[data-testid="metric-container"] {{ background-color:{CLR_CARD}; }}
          .stTabs [data-baseweb="tab-list"] {{
              gap: 8px;
              background-color:{CLR_CARD};
              border-radius:10px;
              padding:4px;
          }}
          .stTabs [data-baseweb="tab"] {{
              background-color:transparent;
              border-radius:8px;
              color:{CLR_NEUT};
              padding:6px 20px;
              font-weight:600;
          }}
          .stTabs [aria-selected="true"] {{
              background-color:{CLR_WIN}22 !important;
              color:{CLR_WIN} !important;
          }}
          table {{ border-collapse: collapse; width:100%; }}
          td, th {{ padding: 8px 12px; }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar ────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            f"<h2 style='color:{CLR_WIN};margin-bottom:0;'>📈 Deriv Bot</h2>"
            f"<div style='color:{CLR_NEUT};font-size:0.8rem;margin-bottom:20px;'>"
            f"Dashboard v1.0</div>",
            unsafe_allow_html=True,
        )

        auto_refresh = st.toggle("Auto-refresh", value=True)
        refresh_sec  = st.slider("Intervalo (s)", 10, 120, 30, 10,
                                 disabled=not auto_refresh)

        st.divider()
        tick_n = st.slider("Ticks no gráfico", 100, 2000, 500, 100)

        st.divider()
        if st.button("🔄 Atualizar Agora", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.divider()
        # Status dos arquivos
        ops_ok   = OPS_CSV.exists()
        ticks_ok = TICKS_CSV.exists()
        st.markdown(
            f"**Arquivos:**\n\n"
            f"{'🟢' if ops_ok else '🔴'} operacoes_log.csv\n\n"
            f"{'🟢' if ticks_ok else '🔴'} ticks.csv"
        )
        if ops_ok:
            sz = OPS_CSV.stat().st_size / 1024
            mtime = datetime.fromtimestamp(OPS_CSV.stat().st_mtime)
            st.caption(f"Log: {sz:.1f} KB · {mtime.strftime('%H:%M:%S')}")

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    st.markdown(
        "<h1 style='margin-bottom:0;font-size:1.8rem;'>"
        "📊 Deriv Trading Bot — Dashboard"
        "</h1>"
        f"<p style='color:{CLR_NEUT};margin-top:2px;font-size:0.82rem;'>"
        f"Atualizado em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>",
        unsafe_allow_html=True,
    )

    # ── Carregar dados ────────────────────────────────────────────────────────
    df    = load_ops()
    ticks = load_ticks(tick_n)

    # ── Abas ──────────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "🏠 Overview",
        "📋 Histórico",
        "📉 Análise Técnica",
        "🤖 IA & Risco",
    ])

    with tab1:
        tab_overview(df)
    with tab2:
        tab_historico(df)
    with tab3:
        tab_tecnico(df, ticks)
    with tab4:
        tab_ia_risco(df)

    # ── Auto-refresh via meta tag (não bloqueia o WebSocket) ─────────────────
    if auto_refresh:
        st.markdown(
            f'<meta http-equiv="refresh" content="{refresh_sec}">',
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
