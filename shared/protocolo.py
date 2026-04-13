"""
shared/protocolo.py
Tipos de mensagem e helpers de serialização.

Filosofia de segurança:
  - O cliente NUNCA guarda estado de jogo (HP, balas, bandeira).
  - Cada pacote de estado inclui um campo "meu_estado" personalizado
    por destinatário, com os valores autoritativos do servidor.
  - O cliente só renderiza — toda validação é server-side.

Verificação de versão:
  - O primeiro pacote do cliente contém apelido + versão.
  - O servidor responde com TIPO_VERSAO_OK ou TIPO_VERSAO_INVALIDA.
  - Clientes com versão diferente são rejeitados antes de entrar no jogo.
  - Para atualizar o protocolo: incremente VERSAO aqui e redistribua
    shared/protocolo.py para todos os participantes.
"""
import json

BUFFERSIZE        = 65507
BUFFERSIZE_ESTADO = 8192

# ── Versão do protocolo ───────────────────────────────────────────────────────
# Incrementar MAJOR em mudanças incompatíveis, MINOR em adições retrocompatíveis.
VERSAO = "1.2"

# ── Tipos de payload ──────────────────────────────────────────────────────────
TIPO_BV              = "bv"
TIPO_MAPA_ESTATICO   = "mapa_est"
TIPO_ESTADO          = "estado"
TIPO_MSG             = "msg"
TIPO_ERRO            = "erro"
TIPO_ESCOLHA         = "escolha"
TIPO_PING            = "ping"
TIPO_PONG            = "pong"
TIPO_VERSAO_OK       = "versao_ok"   # servidor aceita a versão do cliente
TIPO_VERSAO_INVALIDA = "versao_inv"  # servidor rejeita — cliente deve encerrar

TIPO_MAPA = TIPO_ESTADO  # alias de compatibilidade

# ── Comandos do cliente ───────────────────────────────────────────────────────
CMD_SAIR   = "/sair"
CMD_MOVER  = "/mover"
CMD_ATIRAR = "/atirar"
CMD_TIME   = "/time"
CMD_PONG   = "/pong"

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

# ── Primeiro pacote do cliente ────────────────────────────────────────────────
def encode_handshake(apelido: str) -> bytes:
    """
    Substitui o envio simples de apelido.encode().
    Inclui a versão do protocolo para validação server-side.
    """
    return encode({"apelido": apelido, "versao": VERSAO})

def decode_handshake(data: bytes) -> tuple[str, str]:
    """
    Retorna (apelido, versao). Se o pacote for texto puro (cliente antigo),
    retorna (texto, "") — o servidor rejeitará por versão ausente.
    """
    try:
        payload = decode(data)
        return payload.get("apelido", ""), payload.get("versao", "")
    except Exception:
        return data.decode().strip(), ""

# ── Respostas de versão ───────────────────────────────────────────────────────
def msg_versao_ok() -> bytes:
    return encode({"tipo": TIPO_VERSAO_OK, "versao": VERSAO})

def msg_versao_invalida(versao_servidor: str) -> bytes:
    return encode({
        "tipo":    TIPO_VERSAO_INVALIDA,
        "versao":  versao_servidor,
        "texto":   (
            f"Versão incompatível. "
            f"Servidor: {versao_servidor} | "
            f"Atualize seu cliente para continuar."
        ),
    })

# ── Demais construtores de payload ────────────────────────────────────────────
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