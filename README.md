# 🤖 Binary Bot — Deriv Trading Bot com IA

Bot de trading automatizado para a plataforma **Deriv**, operando em índices sintéticos de volatilidade 24/7. Combina análise técnica clássica com Machine Learning (RandomForest + XGBoost + Stacking + Temporal Fusion Transformer), gerenciamento de risco profissional e um dashboard web em tempo real via Firebase.

---

## 📋 Índice

1. [Visão Geral](#-visão-geral)
2. [Arquitetura](#-arquitetura)
3. [Pré-requisitos](#-pré-requisitos)
4. [Instalação](#-instalação)
5. [Configuração](#-configuração)
6. [Como Executar](#-como-executar)
7. [Dashboard Web](#-dashboard-web)
8. [Módulos do Projeto](#-módulos-do-projeto)
9. [Estratégia de Trading](#-estratégia-de-trading)
10. [Gestão de Risco](#-gestão-de-risco)
11. [Modelos de IA](#-modelos-de-ia)
12. [Símbolos Suportados](#-símbolos-suportados)
13. [Firebase](#-firebase)
14. [Agente de Controle Remoto](#-agente-de-controle-remoto)

---

## 🎯 Visão Geral

O bot opera nas seguintes etapas automáticas:

1. **Scan de mercado** → avalia até 22 símbolos e elege o com maior tendência
2. **Coleta de dados** → histórico via API + streaming de ticks ao vivo
3. **Engenharia de features** → 16 indicadores técnicos calculados em janela deslizante
4. **Treinamento de IA** → RF + XGB + Stacking + TFT (Temporal Fusion Transformer)
5. **Operação ao vivo** → análise técnica + IA combinadas, com execução automática de ordens
6. **Re-treino adaptativo** → o modelo se atualiza em background sem parar o bot

---

## 🏗 Arquitetura

```
┌──────────────────────────────────────────────────────────────────────┐
│                           pipeline.py                                │
│                        (orquestrador)                                │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  PRÉ: Scan de 22 símbolos ──→ elege índice com maior ADX+EMA+MACD   │
│                                                                      │
│  [Thread 1] collector.py ──→ ticks.csv ──→ Firebase RTDB            │
│      ↓ (500+ ticks acumulados)                                       │
│  [Main]     dataset_builder.py ──→ dataset.csv                      │
│      ↓                                                               │
│  [Main]     train_model.py ──→ model.pkl                            │
│                RF + XGB + Stacking + TFT (opcional)                  │
│      ↓                                                               │
│  [Thread 2] executor.py (DerivBot)                                  │
│      ↓ ticks ao vivo via WebSocket                                   │
│      strategy.py → indicators.py → ai_predictor.py                  │
│      ↓ sinal BUY / SELL                                              │
│      API Deriv → proposal → buy → contract → resultado              │
│      ↓                                                               │
│      risk_manager.py → operacoes_log.csv → Firebase Firestore       │
│                                                                      │
│  [Thread 3] Re-treino adaptativo em fundo (bot continua rodando)    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

[bot_agent.py] ←→ Firebase RTDB ←→ Dashboard Web (Firebase Hosting)
                                          ↑
                                    app.js + Plotly.js
                                    Firestore JS SDK
```

---

## 📦 Pré-requisitos

| Requisito | Versão mínima |
|-----------|--------------|
| Python | 3.10+ |
| pip | 23+ |
| Node.js | 18+ (para Firebase CLI) |
| Firebase CLI | `npm i -g firebase-tools` |
| Conta Deriv | Token de API (demo ou real) |
| Projeto Firebase | com Realtime DB, Firestore e Storage habilitados |

---

## 🔧 Instalação

```bash
# 1. Clone o repositório
git clone https://github.com/estanislauaaraojunior/Binary.git
cd Binary

# 2. Crie e ative o ambiente virtual
python3 -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows

# 3. Instale as dependências
pip install -r requirements.txt
```

### Dependências principais

| Pacote | Uso |
|--------|-----|
| `websocket-client` | Conexão WebSocket com a API Deriv |
| `scikit-learn` | RandomForest, Stacking, StandardScaler |
| `xgboost` | XGBClassifier |
| `torch` | Temporal Fusion Transformer (PyTorch) |
| `pandas` / `numpy` | Manipulação de dados e séries temporais |
| `joblib` | Serialização de modelos (`model.pkl`) |
| `firebase-admin` | Realtime DB, Firestore e Storage |
| `python-dotenv` | Carregamento de variáveis de ambiente |

---

## ⚙️ Configuração

### 1. Arquivo `.env`

Crie um arquivo `.env` na raiz do projeto:

```env
DERIV_APP_ID=1089
DERIV_TOKEN=SEU_TOKEN_AQUI

FIREBASE_DB_URL=https://seu-projeto-default-rtdb.firebaseio.com
FIREBASE_BUCKET=seu-projeto.firebasestorage.app
FIREBASE_CRED_PATH=serviceAccountKey.json
```

> ⚠️ **Nunca commite o `.env` ou o `serviceAccountKey.json` no Git!**

### 2. `serviceAccountKey.json`

Baixe a chave de serviço do Firebase:
`Console Firebase → Configurações do Projeto → Contas de serviço → Gerar nova chave privada`

### 3. Parâmetros em `config.py`

Todos os parâmetros do bot são centralizados em `config.py`:

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `DEMO_MODE` | `True` | Conta demo (`True`) ou real (`False`) |
| `SYMBOL` | `"R_100"` | Índice sintético padrão |
| `DURATION` | `5` | Duração de fallback (em ticks) |
| `CANDIDATE_DURATIONS` | `[1, 3, 5, 10]` | Durações que a IA pode escolher |
| `EMA_FAST` / `EMA_SLOW` | `9` / `21` | Períodos das médias móveis |
| `RSI_PERIOD` | `14` | Período do RSI |
| `RSI_OVERSOLD` / `RSI_OVERBOUGHT` | `35` / `65` | Zona neutra do RSI |
| `ADX_MIN` | `20` | Limiar mínimo de tendência |
| `ADX_ADAPTIVE` | `True` | ADX adaptativo por percentil |
| `STAKE_PCT` | `0.01` | 1% do saldo por operação |
| `STOP_LOSS_PCT` | `0.25` | Stop diário em −25% |
| `TAKE_PROFIT_PCT` | `0.50` | Take profit diário em +50% |
| `MAX_CONSEC_LOSSES` | `3` | Losses consecutivos antes de pausar |
| `PAUSE_BASE_SEC` | `600` | Pausa base de 10 min (dobra a cada loss extra) |
| `MIN_TICKS` | `50` | Aquecimento mínimo antes da 1ª entrada |
| `PRICE_BUFFER_SIZE` | `500` | Buffer circular de preços |
| `ENTRY_TICK_INTERVAL` | `100` | Intervalo de ticks entre entradas |
| `USE_AI_MODEL` | `True` | Ativar filtro de IA |
| `AI_TECH_WEIGHT` | `0.60` | Peso da análise técnica no score final |
| `AI_MODEL_WEIGHT` | `0.40` | Peso da IA no score final |
| `AI_SCORE_MIN` | `0.55` | Score mínimo para executar |
| `USE_TRANSFORMER` | `True` | Ativar Temporal Fusion Transformer |
| `TRANSFORMER_BLEND_WEIGHT` | `0.55` | TFT representa 55% do ensemble |
| `TRANSFORMER_SEQ_LEN` | `50` | Janela temporal do TFT |
| `TRANSFORMER_EPOCHS` | `80` | Épocas (com early stopping) |
| `USE_FIREBASE` | `True` | Ativar integração Firebase |
| `FIREBASE_TICK_INTERVAL` | `10` | Envia 1 tick a cada 10 para o RTDB |

---

## 🚀 Como Executar

### Opção 1 — Pipeline completo (recomendado)

```bash
source .venv/bin/activate

# Modo demo (padrão) — faz tudo automaticamente
python pipeline.py

# Modo real (pede confirmação obrigatória)
python pipeline.py --real

# Mais opções
python pipeline.py --history-count 1000   # 1000 ticks históricos no início
python pipeline.py --retrain-interval 10  # re-treina a cada 10 min
python pipeline.py --balance 500          # saldo inicial para o RiskManager
python pipeline.py --skip-collect         # usa ticks.csv já existente
python pipeline.py --force-retrain        # retreina mesmo com model.pkl existente
python pipeline.py --no-scan              # pula o scan automático de símbolo
```

### Opção 2 — Processos separados (debug)

```bash
# Terminal 1 — coletor de ticks
python collector.py

# Terminal 2 — construção do dataset
python dataset_builder.py

# Terminal 3 — treinamento
python train_model.py

# Terminal 4 — bot
python bot.py --demo
```

### Opção 3 — Via agente systemd (controle remoto pelo dashboard)

```bash
./agente.sh install    # instala e habilita o serviço systemd
./agente.sh start      # inicia
./agente.sh stop       # para
./agente.sh restart    # reinicia
./agente.sh status     # status + últimas 20 linhas do log
./agente.sh logs       # tail -f em tempo real
```

---

## 🌐 Dashboard Web

O dashboard está hospedado no **Firebase Hosting**: **https://standeriv.web.app**

### Funcionalidades

| Aba | Conteúdo |
|-----|----------|
| **Overview** | KPIs, curva de saldo, tabela das últimas 20 operações |
| **Histórico** | Filtros por símbolo/direção/resultado/data, gráficos por dia |
| **Análise Técnica** | Preços ao vivo + EMA9, EMA21, Bandas de Bollinger (Plotly.js) |
| **IA & Risco** | Win rate, drawdown, confiança da IA, histórico do modelo |

A sidebar exibe:
- Status de conexão com Firestore e RTDB
- Heartbeat do bot (atualizado a cada 10s)
- Painel de controle (Start/Stop) — requer login com Firebase Auth

### Re-deploy do dashboard

```bash
cd public/
firebase deploy --only hosting
```

---

## 📁 Módulos do Projeto

```
Binary/
├── pipeline.py          # Orquestrador principal — ponto de entrada recomendado
├── bot.py               # Entry point alternativo (CLI direto, sem coletor)
├── executor.py          # Cliente WebSocket e execução de ordens na Deriv
├── collector.py         # Coletor autônomo de ticks via WebSocket
├── strategy.py          # Motor de decisão (análise técnica + filtro de IA)
├── indicators.py        # Funções puras de análise técnica (EMA, RSI, MACD, ADX...)
├── ai_predictor.py      # Inferência em tempo real (singleton thread-safe)
├── dataset_builder.py   # Gerador de dataset com janela deslizante
├── train_model.py       # Treinamento dos modelos ML
├── transformer_model.py # Temporal Fusion Transformer (PyTorch)
├── risk_manager.py      # Gestão de risco e log de operações
├── firebase_client.py   # Integração Firebase (RTDB + Firestore + Storage)
├── bot_agent.py         # Agente de controle remoto via Firebase
├── agente.sh            # Gerenciador systemd do bot_agent
├── config.py            # Todos os parâmetros configuráveis
├── firebase.json        # Configuração do Firebase CLI
├── firestore.rules      # Regras de segurança do Firestore
├── database.rules.json  # Regras de segurança do Realtime DB
├── requirements.txt     # Dependências Python
├── ticks.csv            # Dados coletados pelo collector.py
├── dataset.csv          # Dataset processado para treinamento
├── operacoes_log.csv    # Log completo de todas as operações
├── model.pkl            # Modelo treinado (gerado automaticamente)
└── public/              # Dashboard web
    ├── index.html
    ├── app.js
    └── style.css
```

### Descrição detalhada dos módulos

#### `pipeline.py` — Orquestrador Principal

Executa o bot de ponta a ponta em fases sequenciais:

| Fase | O que faz |
|------|-----------|
| **PRÉ** | Scan de tendência: avalia até 22 símbolos e elege o mais forte |
| **0** | Busca histórico de ticks via API WebSocket da Deriv |
| **1** | Inicia coletor ao vivo em background (salva `ticks.csv`) |
| **2** | Aguarda acúmulo mínimo de ticks |
| **3** | Constrói `dataset.csv` via `dataset_builder.py` |
| **4** | Treina e salva `model.pkl` via `train_model.py` |
| **5** | Inicia o bot (`executor.py`) |
| **6** | Re-treino adaptativo contínuo sem parar o bot |

O **re-treino adaptativo** dispara por 3 gatilhos independentes:
- Acúmulo de 500 novos ticks
- Win rate < 40% nas últimas operações
- Confiança média da IA < 56%

Cooldown mínimo de 5 minutos entre retreinos.

#### `executor.py` — Ciclo de Execução

```
tick recebido
  → aquecimento (MIN_TICKS)
  → cadência (ENTRY_TICK_INTERVAL)
  → can_trade() no RiskManager
  → get_signal() na Strategy
  → send_proposal() → API Deriv
  → handle_proposal() → buy
  → handle_contract_update() → resultado
  → risk_manager.record_result()
```

Proteções automáticas:
- **Timeout de proposal** — 10s sem resposta cancela a operação
- **Timeout de contrato** — 3× a duração (mínimo 60s)
- **Watchdog de heartbeat** — alerta se nenhum tick chegar em 30s
- **ADX adaptativo** — calculado por percentil sobre o histórico de 500 ticks
- **Buffer circular** — 500 preços em `deque` para indicadores estáveis

#### `indicators.py` — Análise Técnica

| Função | Período padrão | Indicador |
|--------|---------------|-----------|
| `ema(prices, period)` | 9 / 21 | Exponential Moving Average |
| `rsi(prices, period)` | 14 | RSI com suavização de Wilder |
| `macd(prices, fast, slow, signal)` | 12/26/9 | MACD: linha, sinal, histograma |
| `adx(prices, period)` | 14 | ADX via +DM/-DM/TR (suavização Wilder) |
| `bollinger(prices, period, std_dev)` | 20 / 2.0 | Bandas de Bollinger |
| `momentum(prices, period)` | 3 | Diferença simples: P_atual − P_{t−N} |

As mesmas funções são usadas no bot e no treinamento — garantindo consistência total entre treino e inferência.

---

## 📊 Estratégia de Trading

### Modo AND rígido (padrão)

Para gerar um sinal, **todos** os critérios abaixo devem ser verdadeiros:

**BUY:**
```
EMA9 > EMA21
preço > EMA9
RSI ∈ [35, 65]     ← zona neutra (evita extremos)
ADX > adx_min      ← tendência presente
MACD_hist > 0
momentum(3) > 0
```

**SELL:**
```
EMA9 < EMA21
preço < EMA9
RSI ∈ [35, 65]
ADX > adx_min
MACD_hist < 0
momentum(3) < 0
```

### Filtro de IA (score final)

Após o sinal técnico, a IA é consultada:

| Situação | Score final |
|----------|-------------|
| IA **concorda** com o sinal | `0.60 + 0.40 × confiança_ia` |
| IA **diverge** do sinal | `0.60 − 0.40 × (1 − confiança_ia)` |
| Score < 0.55 | ❌ Sinal bloqueado |

### Modo ponderado (opcional, `USE_WEIGHTED_SIGNAL=True`)

```
Score = EMA_cross    × 0.30
      + preço_vs_EMA × 0.20
      + MACD         × 0.25
      + momentum     × 0.15
      + ADX_norm     × 0.10
```

---

## 🛡 Gestão de Risco

O `risk_manager.py` aplica as seguintes proteções:

| Regra | Valor | Comportamento |
|-------|-------|---------------|
| **Stake por operação** | 1% do saldo | Mínimo de $0.35 |
| **Stop loss diário** | −25% do saldo do dia | Para o bot pelo resto do dia |
| **Take profit diário** | +50% do saldo do dia | Para o bot pelo resto do dia |
| **Losses consecutivos** | 3 losses | Pausa de 10 min |
| **Escalonamento de pausa** | A cada loss extra | Pausa dobra: 10min → 20min → 40min... |
| **Cap de pausa** | 2 horas | Pausa máxima |
| **Resume automático** | 1 vitória | Retoma imediatamente |
| **Drift detection** | Win rate < 40% (últimos 20) | Alerta + gatilho de re-treino |

O log de operações (`operacoes_log.csv`) registra 27 colunas por operação, incluindo `contract_id`, `entry_spot`, `exit_spot`, `drawdown_pct`, `win_rate_recent` e `market_condition`.

---

## 🧠 Modelos de IA

### Ensemble: RF + XGB + Stacking

| Modelo | Configuração |
|--------|-------------|
| **RandomForestClassifier** | 300 árvores, `max_depth=10`, `class_weight="balanced"` |
| **XGBClassifier** | 300 estimadores, `learning_rate=0.05`, peso balanceado |
| **StackingClassifier** | RF + XGB como base, `LogisticRegression` como meta-learner (`CV=5`) |

Seleção do melhor modelo por **ROC-AUC**.  
Separação treino/teste **estritamente temporal** (sem shuffle) com gap de 2% — sem data leakage.

### Temporal Fusion Transformer (TFT)

Implementação completa em PyTorch com:

| Componente | Função |
|-----------|--------|
| `GatedResidualNetwork` | `gate × h + x` com skip connection e LayerNorm |
| `VariableSelectionNetwork` | Peso softmax por feature — indica quais indicadores importam mais |
| `TFTModel` | VSN → Pos. Embedding → GRN → TransformerEncoder (causal) → AttnPool → Heads |

Multi-task: prevê **direção** (BUY/SELL) e **duração ótima** simultaneamente.

O TFT representa 55% do ensemble final (`TRANSFORMER_BLEND_WEIGHT=0.55`).

### Features do modelo (16 no total)

`ema9`, `ema21`, `ema_cross`, `price_vs_ema9`, `rsi`, `macd_line`, `macd_signal`, `macd_hist`, `adx`, `bb_upper`, `bb_lower`, `bb_width`, `momentum_3`, `momentum_10`, `volume_proxy`, `price_change_pct`

---

## 📈 Símbolos Suportados

O pipeline escaneia automaticamente 22 símbolos e elege o com maior tendência:

### Grupo Primário — Volatility Indices

| Símbolo | Nome |
|---------|------|
| `R_10` | Volatility 10 Index |
| `R_25` | Volatility 25 Index |
| `R_50` | Volatility 50 Index |
| `R_75` | Volatility 75 Index |
| `R_100` | Volatility 100 Index |
| `1HZ10V` | Volatility 10 (1s) Index |
| `1HZ25V` | Volatility 25 (1s) Index |
| `1HZ50V` | Volatility 50 (1s) Index |
| `1HZ75V` | Volatility 75 (1s) Index |
| `1HZ100V` | Volatility 100 (1s) Index |

### Grupo Secundário — Boom / Crash / Jump / Step

| Símbolo | Nome |
|---------|------|
| `BOOM300N` / `BOOM500` / `BOOM1000` | Boom 300 / 500 / 1000 Index |
| `CRASH300N` / `CRASH500` / `CRASH1000` | Crash 300 / 500 / 1000 Index |
| `JD10` / `JD25` / `JD50` / `JD75` / `JD100` | Jump 10 – 100 Index |
| `stpRNG` | Step Index |

> O grupo secundário é avaliado apenas se **todos** os primários estiverem em mercado lateral (score < 15).

---

## 🔥 Firebase

### Estrutura do Realtime Database

```
/
├── live_tick/<SYMBOL>/       ← último tick recebido (atualizado a cada 10 ticks)
└── bot_control/
    ├── status/               ← heartbeat, PID, saldo, moeda, running
    └── commands/             ← comandos start/stop enviados pelo dashboard
```

### Regras de segurança

**Realtime Database:**
- `ticks/<symbol>` — leitura pública, escrita bloqueada
- `bot_control/status` — leitura pública, escrita bloqueada para clientes
- `bot_control/commands` — leitura e escrita apenas para usuários autenticados

**Firestore:**
- `operacoes/<docId>` — leitura pública; criação/atualização apenas via Admin SDK; delete apenas com autenticação

### Estrutura do Firestore

```
operacoes/
└── <doc_id>/
    ├── symbol
    ├── direction       (BUY / SELL)
    ├── result          (WIN / LOSS)
    ├── stake
    ├── profit_loss
    ├── balance_after
    ├── entry_spot
    ├── exit_spot
    ├── drawdown_pct
    ├── win_rate_recent
    ├── ai_confidence
    ├── contract_id
    └── timestamp
```

---

## 🤖 Agente de Controle Remoto

O `bot_agent.py` + `agente.sh` permitem controlar o bot remotamente pelo dashboard:

```
Dashboard Web
     │
     │  (escrita em bot_control/commands via Firestore JS SDK)
     ▼
Firebase RTDB ──→ bot_agent.py ──→ start/stop pipeline.py
                       │
                       └──→ publica status a cada 10s
                            (running, pid, balance, heartbeat)
```

### Instalar como serviço systemd

```bash
./agente.sh install
```

O serviço reinicia automaticamente em caso de crash e persiste entre reinicializações do sistema.

---

## ⚠️ Avisos

- **Risco financeiro**: Trading em opções binárias envolve **alto risco de perda**. Use sempre conta demo antes de operar com dinheiro real.
- **Tokens**: Nunca compartilhe `DERIV_TOKEN` ou `serviceAccountKey.json`.
- **Resultados passados**: A performance histórica do bot não garante resultados futuros.
- **Modo real**: O pipeline exige confirmação explícita (`--real`) para proteger contra execuções acidentais.

---

## 📄 Licença

Projeto pessoal de uso educacional. Não é recomendação de investimento.