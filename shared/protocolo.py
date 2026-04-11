"""
shared/protocolo.py
Tipos de mensagem e helpers de serialização usados por servidor e cliente.
"""
import json

BUFFERSIZE = 4096

# ── Tipos de payload ──────────────────────────────────────────────────────────
TIPO_BV      = "bv"      # boas-vindas (servidor → cliente recém-conectado)
TIPO_MAPA    = "mapa"    # snapshot do mapa (servidor → todos)
TIPO_MSG     = "msg"     # mensagem de texto/chat
TIPO_ERRO    = "erro"    # erro de operação (movimento inválido, mapa cheio…)

# ── Comandos do cliente ───────────────────────────────────────────────────────
CMD_SAIR     = "/sair"
CMD_MOVER    = "/mover"   # /mover cima|baixo|esq|dir

DIRECOES = {
    "cima":  (0, -1),
    "baixo": (0,  1),
    "esq":   (-1, 0),
    "dir":   (1,  0),
}

# ── Serialização ──────────────────────────────────────────────────────────────
def encode(payload: dict) -> bytes:
    return json.dumps(payload).encode()

def decode(data: bytes) -> dict:
    return json.loads(data.decode())

# ── Construtores de payload ───────────────────────────────────────────────────
def msg_bv(texto: str, snapshot: dict) -> bytes:
    return encode({"tipo": TIPO_BV, "texto": texto, "mapa": snapshot})

def msg_mapa(snapshot: dict) -> bytes:
    return encode({"tipo": TIPO_MAPA, **snapshot})

def msg_chat(texto: str) -> bytes:
    return encode({"tipo": TIPO_MSG, "texto": texto})

def msg_erro(texto: str) -> bytes:
    return encode({"tipo": TIPO_ERRO, "texto": texto})