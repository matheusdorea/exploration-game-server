"""
shared/protocolo.py
Tipos de mensagem e helpers de serialização usados por servidor e cliente.
"""
import json

# UDP seguro até ~8 KB no Windows; estado dinâmico cabe folgado nesse limite.
# O mapa estático é enviado uma única vez na conexão — pode ser maior.
BUFFERSIZE       = 65507   # máximo teórico UDP (usado só para recvfrom)
BUFFERSIZE_ESTADO = 8192   # tamanho máximo esperado do payload dinâmico

# ── Tipos de payload ──────────────────────────────────────────────────────────
TIPO_BV             = "bv"        # boas-vindas + mapa estático
TIPO_MAPA_ESTATICO  = "mapa_est"  # matriz do mapa (enviado uma só vez)
TIPO_ESTADO         = "estado"    # posições de jogadores + projéteis (a cada tick)
TIPO_MSG            = "msg"       # mensagem de texto/chat
TIPO_ERRO           = "erro"      # erro de operação
TIPO_ESCOLHA        = "escolha"   # servidor pede escolha de time
TIPO_ATINGIDO       = "atingido"  # jogador foi atingido

# Alias de compatibilidade (rede.py checa TIPO_MAPA também)
TIPO_MAPA = TIPO_ESTADO

# ── Comandos do cliente ───────────────────────────────────────────────────────
CMD_SAIR    = "/sair"
CMD_MOVER   = "/mover"    # /mover cima|baixo|esq|dir
CMD_ATIRAR  = "/atirar"   # /atirar cima|baixo|esq|dir
CMD_TIME    = "/time"     # /time A|B

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
    """Enviado uma única vez na boas-vindas. Contém a matriz completa."""
    return encode({
        "tipo":    TIPO_MAPA_ESTATICO,
        "linhas":  linhas,
        "colunas": colunas,
        "mapa":    mapa,
    })

def msg_bv(texto: str) -> bytes:
    """Boas-vindas simples — mapa estático é enviado em pacote separado."""
    return encode({"tipo": TIPO_BV, "texto": texto})

def msg_estado(jogadores: dict, projeteis: list) -> bytes:
    """Payload dinâmico: apenas posições + HP + projéteis. Enviado a cada tick."""
    return encode({
        "tipo":      TIPO_ESTADO,
        "jogadores": jogadores,
        "projeteis": projeteis,
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