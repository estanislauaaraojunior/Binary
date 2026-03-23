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
    Envia tick ao Realtime Database em thread daemon (não bloqueia o coletor).

    Estrutura no DB:
        ticks/<SYMBOL>/<push_id>/
            epoch    : int
            price    : float
            datetime : str  (ISO-8601)
    """
    def _push() -> None:
        ref = _rtdb_ref(f"ticks/{symbol}")
        if ref is None:
            return
        try:
            ref.push({"epoch": epoch, "price": price, "datetime": dt_str})
        except Exception as exc:
            print(f"\n[FIREBASE] Erro ao salvar tick: {exc}")

    threading.Thread(target=_push, daemon=True).start()


def add_operation_async(data: dict) -> None:
    """
    Salva registro de operação na coleção 'operacoes' do Firestore em background.

    O documento inclui todos os campos do CSV de log mais timestamp para
    permitir consultas e dashboards via Firebase Console.
    """
    def _add() -> None:
        fs = _firestore_client()
        if fs is None:
            return
        try:
            fs.collection("operacoes").add(data)
        except Exception as exc:
            print(f"\n[FIREBASE] Erro ao salvar operação: {exc}")

    threading.Thread(target=_add, daemon=True).start()


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
