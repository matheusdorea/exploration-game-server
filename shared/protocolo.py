"""
shared/protocolo.py
Alteração em relação à versão anterior:
  - msg_estado() aceita parâmetro opcional `itens` (lista de posições públicas)
  - Nenhum tipo novo adicionado — itens chegam embutidos no TIPO_ESTADO
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
TIPO_MAPA          = TIPO_ESTADO   # alias de compatibilidade

CMD_SAIR   = "/sair"
CMD_MOVER  = "/mover"
CMD_ATIRAR = "/atirar"
CMD_TIME   = "/time"

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

def msg_estado(jogadores: dict, projeteis: list, itens: list = None) -> bytes:
    # ITEM — itens incluídos como campo opcional; [] se não houver
    return encode({
        "tipo":      TIPO_ESTADO,
        "jogadores": jogadores,
        "projeteis": projeteis,
        "itens":     itens or [],
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