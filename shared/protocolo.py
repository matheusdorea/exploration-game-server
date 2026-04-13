"""
shared/protocolo.py
Tipos de mensagem e helpers de serialização.
"""
import json

BUFFERSIZE        = 65507   # máximo UDP (usado no recvfrom)
BUFFERSIZE_ESTADO = 8192    # limite esperado do payload dinâmico

# ── Tipos de payload ──────────────────────────────────────────────────────────
TIPO_BV            = "bv"        # boas-vindas
TIPO_MAPA_ESTATICO = "mapa_est"  # matriz do mapa (enviado uma só vez)
TIPO_ESTADO        = "estado"    # estado dinâmico completo (a cada tick)
TIPO_MSG           = "msg"       # chat / notificações textuais
TIPO_ERRO          = "erro"      # erro de operação
TIPO_ESCOLHA       = "escolha"   # servidor pede escolha de time
TIPO_PING          = "ping"      # keepalive servidor → cliente
TIPO_PONG          = "pong"      # keepalive cliente → servidor

# Alias para compatibilidade com código existente
TIPO_MAPA = TIPO_ESTADO

# ── Comandos do cliente (apenas intenções, sem valores) ───────────────────────
CMD_SAIR   = "/sair"
CMD_MOVER  = "/mover"    # /mover cima|baixo|esq|dir
CMD_ATIRAR = "/atirar"   # /atirar cima|baixo|esq|dir
CMD_TIME   = "/time"     # /time A|B
CMD_PONG   = "/pong"     # resposta ao ping

# ── Times ─────────────────────────────────────────────────────────────────────
TIME_A = "A"
TIME_B = "B"

# ── Direções ──────────────────────────────────────────────────────────────────
DIRECOES = {
    "cima":  (0, -1),
    "baixo": (0,  1),
    "esq":   (-1, 0),
    "dir":   (1,  0),
}

# ── Serialização ──────────────────────────────────────────────────────────────
def encode(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()

def decode(data: bytes) -> dict:
    return json.loads(data.decode())

# ── Construtores de payload ───────────────────────────────────────────────────
def msg_mapa_estatico(linhas: int, colunas: int, mapa: list) -> bytes:
    return encode({
        "tipo":    TIPO_MAPA_ESTATICO,
        "linhas":  linhas,
        "colunas": colunas,
        "mapa":    mapa,
    })

def msg_bv(texto: str) -> bytes:
    return encode({"tipo": TIPO_BV, "texto": texto})

def msg_estado(jogadores: dict, projeteis: list,
               itens: list = None, bandeiras: list = None,
               meu_estado: dict = None) -> bytes:
    """
    Payload dinâmico enviado a cada tick/movimento.

    meu_estado — campo personalizado por destinatário, inserido pelo servidor
                 antes de enviar para cada cliente individualmente:
                 { hp, balas, escudo, bandeira, time }
    """
    payload = {
        "tipo":      TIPO_ESTADO,
        "jogadores": jogadores,
        "projeteis": projeteis,
        "itens":     itens or [],
        "bandeiras": bandeiras or [],
    }
    if meu_estado is not None:
        payload["meu_estado"] = meu_estado
    return encode(payload)

def msg_chat(texto: str) -> bytes:
    return encode({"tipo": TIPO_MSG, "texto": texto})

def msg_erro(texto: str) -> bytes:
    return encode({"tipo": TIPO_ERRO, "texto": texto})

def msg_escolha_time() -> bytes:
    return encode({
        "tipo":  TIPO_ESCOLHA,
        "texto": "Escolha seu time: A (esquerda) ou B (direita)",
    })

def msg_ping() -> bytes:
    return encode({"tipo": TIPO_PING})