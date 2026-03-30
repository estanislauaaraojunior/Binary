# ============================================================
#  config.py — configurações centralizadas do bot Deriv
#  Edite APENAS este arquivo para ajustar o comportamento.
# ============================================================

import os
from dotenv import load_dotenv

load_dotenv()  # carrega variáveis de .env (ignorado se não existir)

# ----- Conta -----
# True  → opera na conta DEMO (seguro — dinheiro virtual)
# False → opera na conta REAL (requer TOKEN de conta real + confirmação no terminal)
DEMO_MODE = True

# ----- Conexão -----
APP_ID = os.environ.get("DERIV_APP_ID", "1089")
TOKEN  = os.environ["DERIV_TOKEN"]    # defina em .env — crie em: developers.deriv.com

# ----- Instrumento -----
SYMBOL        = "R_100"  # índice sintético 24/7 (sem impacto de notícias)
DURATION      = 5        # duração de fallback (usada quando o modelo ainda não existe)
DURATION_UNIT = "t"      # "t" = ticks | "s" = segundos | "m" = minutos
BASIS         = "stake"  # base do contrato
CURRENCY      = "USD"

# ----- Duração dinâmica (escolhida pela IA) -----
# Durações candidatas (em ticks) que o modelo de duração pode prever.
# Adicione ou remova valores para ampliar/restringir o leque de opções.
CANDIDATE_DURATIONS = [3, 5, 10]
DURATION_MODEL_PATH = "duration_model.pkl"

# ----- Parâmetros dos indicadores -----
EMA_FAST     = 9
EMA_SLOW     = 21
EMA_TREND    = 50   # EMA lenta de tendência de médio prazo (filtro direcional)
RSI_PERIOD   = 14
MACD_FAST    = 12
MACD_SLOW    = 26
MACD_SIGNAL  = 9
ADX_PERIOD   = 14
BB_PERIOD    = 20
BB_STD       = 2.0
ATR_PERIOD        = 14   # Average True Range (volatilidade absoluta)
STOCH_K_PERIOD    = 14   # Stochastic %K
STOCH_D_PERIOD    = 3    # Stochastic %D (sinal)

# ----- Filtros de entrada -----
RSI_OVERSOLD    = 30   # abaixo → sobrevendido (não abre SELL aqui)
RSI_OVERBOUGHT  = 70   # acima → sobrecomprado (não abre BUY aqui)
ADX_MIN         = 20   # abaixo → mercado lateral → sem entrada

# True  → BUY só se EMA9 > EMA21 > EMA50; SELL só se EMA9 < EMA21 < EMA50
# False → usa apenas o cruzamento EMA9/EMA21 (comportamento anterior)
USE_EMA_TREND_FILTER = True

# ----- ADX adaptativo (P10) -----
# True  → ADX_MIN ajustado ao percentil do histórico recente (mais preciso por símbolo)
# False → usa ADX_MIN fixo acima
ADX_ADAPTIVE            = True
ADX_ADAPTIVE_PERCENTILE = 40   # percentil do histórico de ADX; piso = 15

# ----- Gestão de risco -----
STAKE_PCT         = 0.01   # 1% do saldo por operação
STOP_LOSS_PCT     = 0.25   # -25% do saldo diário → para o dia
TAKE_PROFIT_PCT   = 0.50   # +50% do saldo diário → para o dia
MAX_CONSEC_LOSSES = 3      # losses consecutivos antes de pausar

# Sizing dinâmico por volatilidade (ATR)
# True  → stake = ATR_RISK_USD / atr_atual (menor stake quando mercado volátil)
# False → usa STAKE_PCT fixo acima
USE_ATR_SIZING = True
ATR_RISK_USD   = 5.0   # risco máximo em USD por trade quando USE_ATR_SIZING=True

# Pausa escalável: base * scale_factor^(losses_extras) — cap de 2h (P8)
PAUSE_BASE_SEC     = 600   # 10 min de pausa base (1º gatilho)
PAUSE_SCALE_FACTOR = 2     # dobra a pausa a cada loss além do limite
RESUME_ON_WIN      = True  # retoma pausa imediatamente após 1 win

# ----- Aquecimento -----
MIN_TICKS = 50  # ticks mínimos antes de operar (garante indicadores estáveis)

# ----- Buffer de preços (P12) -----
PRICE_BUFFER_SIZE = 500  # ticks mantidos em memória para indicadores e IA

# ----- Cadência de entradas -----
# Primeira entrada: imediata após MIN_TICKS (modelo já treinado com histórico).
# Entradas seguintes: somente após acumular ENTRY_TICK_INTERVAL novos ticks.
ENTRY_TICK_INTERVAL = 100  # ticks entre entradas

# ----- Timeout de operações (P1, P7) -----
PROPOSAL_TIMEOUT_SEC = 10   # segundos sem resposta da API antes de cancelar proposal

# ----- Heartbeat / watchdog (P9) -----
HEARTBEAT_TIMEOUT_SEC = 30  # segundos sem tick antes de alertar

# ----- Coletor — qualidade de dados (P2) -----
TICK_SPIKE_THRESHOLD = 0.05  # rejeitar ticks com variação > 5% em relação ao anterior

# ----- Inteligência Artificial -----
# USE_AI_MODEL = False  → bot funciona exatamente como antes (só indicadores)
# USE_AI_MODEL = True   → IA pondera o sinal dos indicadores antes de operar
USE_AI_MODEL       = True
AI_MODEL_PATH      = "model.pkl"
AI_CONFIDENCE_MIN  = 0.58   # mantido para compatibilidade; usado internamente

# Ponderação IA vs técnico (P4) — substitui gate duro por score suavizado
AI_TECH_WEIGHT  = 0.60   # peso do sinal técnico no score final
AI_MODEL_WEIGHT = 0.40   # peso do sinal da IA no score final
AI_SCORE_MIN    = 0.55   # score mínimo ponderado para aceitar a operação

# ----- Sinal ponderado (P14) -----
# False = comportamento original (AND rígido — menos entradas, mais seletivo)
# True  = score ponderado por indicador (mais entradas, requer ajuste fino)
USE_WEIGHTED_SIGNAL = False
SIGNAL_SCORE_MIN    = 0.65  # limiar mínimo do score técnico ponderado

# ----- Detecção de drift (P13) -----
DRIFT_WINDOW       = 20    # janela de trades para calcular win rate recente
DRIFT_WIN_RATE_MIN = 0.40  # alerta se win rate dos últimos N trades < 40%

# ----- Arquivos de log -----
TICKS_CSV        = "ticks.csv"
OPERATIONS_LOG   = "operacoes_log.csv"
DATASET_CSV      = "dataset.csv"

# ─────────────────────────────────────────────────────────────────
#  Temporal Fusion Transformer (TFT) — nível hedge fund
# ─────────────────────────────────────────────────────────────────

# True  → treina e usa TFT em ensemble com RF/XGB (requer torch)
# False → comportamento idêntico ao anterior (sem torch necessário)
USE_TRANSFORMER          = True
TRANSFORMER_MODEL_PATH   = "transformer_model.pkl"

# Blend do ensemble: conf_final = TFT*BLEND + classical*(1-BLEND)
# 0.55 → TFT tem peso levemente maior; ajuste conforme performance observada
TRANSFORMER_BLEND_WEIGHT = 0.55

# Janela temporal: número de vetores de features passados ao TFT como sequência.
# Valores maiores capturam padrões de longo prazo, mas requerem mais dados.
# Requer PRICE_BUFFER_SIZE >= TRANSFORMER_SEQ_LEN + 100 (padrão: 500 > 150 ✓)
TRANSFORMER_SEQ_LEN = 50

# Arquitetura interna do TFT
# Valores reduzidos para CPU (i3-3220). Se tiver GPU com CUDA/ROCm, use d_model=64, n_layers=2.
TRANSFORMER_D_MODEL  = 32    # dimensão dos embeddings internos (era 64 — 4× mais rápido em CPU)
TRANSFORMER_N_HEADS  = 4     # cabeças de atenção (d_model deve ser divisível por n_heads)
TRANSFORMER_N_LAYERS = 1     # camadas do Transformer Encoder (era 2)
TRANSFORMER_DROPOUT  = 0.15  # dropout (maior = mais regularização)

# Treinamento
TRANSFORMER_EPOCHS     = 30    # épocas máximas (era 80 — early stopping para antes se convergir)
TRANSFORMER_BATCH_SIZE = 256   # batch size maior → menos passos por época (era 128)
TRANSFORMER_LR         = 3e-4  # learning rate inicial (AdamW + cosine decay)
TRANSFORMER_PATIENCE   = 7     # épocas sem melhoria antes do early stopping (era 10)
