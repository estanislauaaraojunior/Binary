"""
firebase_client.py — singleton de conexão Firebase.

Gerencia a inicialização única do SDK firebase-admin e expõe
helpers para Realtime Database, Firestore e Storage.

Ativado apenas quando USE_FIREBASE=True em config.py.
As escritas de ticks e operações são feitas em threads daemon para
não bloquear o loop principal do bot.

Pré-requisitos:
  1. pip install firebase-admin
  2. Criar projeto no Firebase Console (console.firebase.google.com)
  3. Gerar chave de service account e salvar como serviceAccountKey.json
     (Project Settings → Service Accounts → Generate new private key)
  4. Habilitar Realtime Database, Firestore e Storage no Console
  5. Preencher FIREBASE_DB_URL e FIREBASE_BUCKET em config.py
"""

import threading
from typing import Optional

_lock = threading.Lock()
_initialized: bool = False
_available: bool = False   # True somente se o SDK inicializou sem erro


def _init() -> bool:
    """Inicializa o Firebase SDK uma única vez (thread-safe). Retorna True se OK."""
    global _initialized, _available

    if _initialized:
        return _available

    with _lock:
        if _initialized:          # double-checked locking
            return _available
        try:
            import firebase_admin
            from firebase_admin import credentials
            from config import FIREBASE_CRED_PATH, FIREBASE_DB_URL, FIREBASE_BUCKET

            cred = credentials.Certificate(FIREBASE_CRED_PATH)
            firebase_admin.initialize_app(cred, {
                "databaseURL":  FIREBASE_DB_URL,
                "storageBucket": FIREBASE_BUCKET,
            })
            _available = True
            print("[FIREBASE] SDK inicializado com sucesso.")
        except FileNotFoundError:
            print(
                "[FIREBASE] serviceAccountKey.json não encontrado — "
                "Firebase desativado. Verifique FIREBASE_CRED_PATH em config.py."
            )
        except Exception as exc:
            print(f"[FIREBASE] Falha na inicialização: {exc} — Firebase desativado.")
        finally:
            _initialized = True

    return _available


# ─────────────────────────────────────────────────────────────────
#  Acessores internos
# ─────────────────────────────────────────────────────────────────

def _rtdb_ref(path: str = "/"):
    """Retorna referência do Realtime Database ou None se indisponível."""
    if not _init():
        return None
    try:
        from firebase_admin import db
        return db.reference(path)
    except Exception as exc:
        print(f"[FIREBASE] Erro ao acessar Realtime DB: {exc}")
        return None


def _firestore_client():
    """Retorna cliente Firestore ou None se indisponível."""
    if not _init():
        return None
    try:
        from firebase_admin import firestore
        return firestore.client()
    except Exception as exc:
        print(f"[FIREBASE] Erro ao acessar Firestore: {exc}")
        return None


def _storage_bucket():
    """Retorna bucket do Storage ou None se indisponível."""
    if not _init():
        return None
    try:
        from firebase_admin import storage
        return storage.bucket()
    except Exception as exc:
        print(f"[FIREBASE] Erro ao acessar Storage: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────
#  API pública — escritas assíncronas (não bloqueiam o bot)
# ─────────────────────────────────────────────────────────────────

def push_tick_async(symbol: str, epoch: int, price: float, dt_str: str) -> None:
    """
    Sobrescreve o tick ao vivo no Realtime Database em thread daemon (não bloqueia o coletor).

    Mantém apenas o tick mais recente por símbolo — evita acúmulo ilimitado
    de nós e preserva a cota gratuita do Firebase.

    Estrutura no DB:
        live_tick/<SYMBOL>/
            epoch    : int
            price    : float
            datetime : str  (ISO-8601)
    """
    def _set() -> None:
        ref = _rtdb_ref(f"live_tick/{symbol}")
        if ref is None:
            return
        try:
            ref.set({"epoch": epoch, "price": price, "datetime": dt_str})
        except Exception as exc:
            print(f"\n[FIREBASE] Erro ao salvar tick: {exc}")

    threading.Thread(target=_set, daemon=True).start()


def add_operation_async(data: dict) -> None:
    """
    Salva registro de operação na coleção 'operacoes' do Firestore.

    A escrita é feita em thread separada mas aguarda confirmação (até 8s)
    para evitar perda de dados quando o processo é encerrado (threads daemon
    seriam mortas antes de completar a escrita no Firestore).
    """
    done = threading.Event()

    def _add() -> None:
        fs = _firestore_client()
        if fs is None:
            done.set()
            return
        try:
            fs.collection("operacoes").add(data)
        except Exception as exc:
            print(f"\n[FIREBASE] Erro ao salvar operação: {exc}")
        finally:
            done.set()

    threading.Thread(target=_add, daemon=True).start()
    done.wait(timeout=8.0)


def upload_model(local_path: str, remote_name: str) -> None:
    """
    Faz upload de um modelo (.pkl) ao Firebase Storage (síncrono).

    Chamado apenas no final do treinamento — não há impacto de latência
    no bot de trading.

    Caminho remoto: models/<remote_name>
    """
    bucket = _storage_bucket()
    if bucket is None:
        return
    try:
        blob = bucket.blob(f"models/{remote_name}")
        blob.upload_from_filename(local_path)
        print(f"[FIREBASE] Modelo enviado: models/{remote_name}")
    except Exception as exc:
        print(f"[FIREBASE] Erro no upload do modelo '{remote_name}': {exc}")


def write_train_meta_async(train_count: int, ticks_count: int) -> None:
    """
    Atualiza metadados de treino no RTDB em thread daemon (não bloqueia o pipeline).

    Estrutura no DB:
        bot_control/train_meta/
            train_count : int   — número total de treinos realizados
            last_train  : str   — timestamp ISO-8601 UTC do último treino
            ticks_count : int   — ticks disponíveis no momento do treino
    """
    import datetime as _dt

    def _write() -> None:
        ref = _rtdb_ref("bot_control/train_meta")
        if ref is None:
            return
        try:
            ref.update({
                "train_count": train_count,
                "last_train":  _dt.datetime.utcnow().isoformat() + "Z",
                "ticks_count": ticks_count,
            })
        except Exception as exc:
            print(f"\n[FIREBASE] Erro ao salvar meta de treino: {exc}")

    threading.Thread(target=_write, daemon=True).start()
