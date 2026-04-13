"""
shared/protocolo.py
"""
import json

BUFFERSIZE        = 65507
BUFFERSIZE_ESTADO = 8192

TIPO_BV            = "bv"
TIPO_MAPA_ESTATICO = "mapa_est"
TIPO_ESTADO        = "estado"
TIPO_MSG           = "msg"
TIPO_ERRO          = "erro"
TIPO_ESCOLHA       = "escolha"
TIPO_ATINGIDO      = "atingido"
TIPO_MUNICAO       = "municao"
TIPO_BANDEIRA      = "bandeira"
TIPO_PING          = "ping"
TIPO_PONG          = "pong"
TIPO_MAPA          = TIPO_ESTADO

CMD_SAIR   = "/sair"
CMD_MOVER  = "/mover"
CMD_ATIRAR = "/atirar"
CMD_TIME   = "/time"
CMD_PONG   = "/pong"

TIME_A = "A"
TIME_B = "B"

DIRECOES = {
    "cima":  (0, -1),
    "baixo": (0,  1),
    "esq":   (-1, 0),
    "dir":   (1,  0),
}

def encode(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()

def decode(data: bytes) -> dict:
    return json.loads(data.decode())

def msg_mapa_estatico(linhas: int, colunas: int, mapa: list) -> bytes:
    return encode({"tipo": TIPO_MAPA_ESTATICO, "linhas": linhas,
                   "colunas": colunas, "mapa": mapa})

def msg_bv(texto: str) -> bytes:
    return encode({"tipo": TIPO_BV, "texto": texto})

def msg_estado(jogadores: dict, projeteis: list,
               itens: list = None, bandeiras: list = None) -> bytes:
    return encode({
        "tipo":      TIPO_ESTADO,
        "jogadores": jogadores,
        "projeteis": projeteis,
        "itens":     itens or [],
        "bandeiras": bandeiras or [],
    })

def msg_chat(texto: str) -> bytes:
    return encode({"tipo": TIPO_MSG, "texto": texto})

def msg_erro(texto: str) -> bytes:
    return encode({"tipo": TIPO_ERRO, "texto": texto})

def msg_escolha_time() -> bytes:
    return encode({"tipo": TIPO_ESCOLHA,
                   "texto": "Escolha seu time: A (esquerda) ou B (direita)"})

def msg_atingido(hp: int, atirador: str) -> bytes:
    return encode({"tipo": TIPO_ATINGIDO, "hp": hp, "atirador": atirador})

def msg_municao(qtd: int) -> bytes:
    return encode({"tipo": TIPO_MUNICAO, "qtd": qtd})

def msg_ping() -> bytes:
    return encode({"tipo": TIPO_PING})

def msg_pong() -> bytes:
    return encode({"tipo": TIPO_PONG})