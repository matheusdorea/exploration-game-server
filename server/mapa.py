"""
server/mapa.py
Matriz do mapa, validações de movimento e snapshots.

Para alterar o tamanho do mapa basta mudar MAPA_LINHAS e MAPA_COLUNAS.
As bases se ajustam automaticamente via server/bases.py.
"""
from shared.protocolo import DIRECOES
from server import bases as Bases

# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  CONFIGURAÇÃO DO MAPA — altere aqui para redimensionar                      │
MAPA_LINHAS  = 17
MAPA_COLUNAS = 60
# └─────────────────────────────────────────────────────────────────────────────┘

# Inicializa as bases com as dimensões escolhidas
Bases.configurar(MAPA_LINHAS, MAPA_COLUNAS)

# ── Tipos de célula ───────────────────────────────────────────────────────────
CELULA_LIVRE  = 0
CELULA_PAREDE = 1
CELULA_BASE_A = 2
CELULA_BASE_B = 3

def _criar_mapa() -> list[list[int]]:
    mapa = []
    centro_y = (Bases.BASE_Y_MIN + Bases.BASE_Y_MAX) // 2
    for r in range(MAPA_LINHAS):
        linha = []
        for c in range(MAPA_COLUNAS):
            eh_borda = (r == 0 or r == MAPA_LINHAS - 1 or
                        c == 0 or c == MAPA_COLUNAS - 1)
            
            eh_parede_base_a = (c == Bases.BASE_A_X_MAX) and not (centro_y - 2 <= r <= centro_y + 2)
            eh_parede_base_b = (c == Bases.BASE_B_X_MIN) and not (centro_y - 2 <= r <= centro_y + 2)
            
            if eh_borda or eh_parede_base_a or eh_parede_base_b:
                linha.append(CELULA_PAREDE)
            elif Bases.eh_base(c, r) == "A":
                linha.append(CELULA_BASE_A)
            elif Bases.eh_base(c, r) == "B":
                linha.append(CELULA_BASE_B)
            else:
                linha.append(CELULA_LIVRE)
        mapa.append(linha)
    return mapa

_mapa: list[list[int]] = _criar_mapa()

# ── Consultas ─────────────────────────────────────────────────────────────────
def eh_parede(x: int, y: int) -> bool:
    if x < 0 or x >= MAPA_COLUNAS or y < 0 or y >= MAPA_LINHAS:
        return True
    return _mapa[y][x] == CELULA_PAREDE

def celula_livre(x: int, y: int, clientes: dict, time_jogador: str = None) -> bool:
    if eh_parede(x, y):
        return False
    for dados in clientes.values():
        if dados.get("time") is None:
            continue
        if dados["x"] == x and dados["y"] == y:
            return False
    return True

def posicao_inicial(clientes: dict, time: str) -> tuple[int | None, int | None]:
    return Bases.spawn_time(time, clientes)

# ── Movimento ─────────────────────────────────────────────────────────────────
def mover_jogador(addr, direcao: str, clientes: dict) -> bool:
    if direcao not in DIRECOES:
        return False
    dados    = clientes[addr]
    time_jog = dados.get("time")
    dx, dy   = DIRECOES[direcao]
    nx, ny   = dados["x"] + dx, dados["y"] + dy

    if not celula_livre(nx, ny, clientes, time_jog):
        return False

    dados["x"] = nx
    dados["y"] = ny
    return True

# ── Snapshots ─────────────────────────────────────────────────────────────────
def snapshot_estatico() -> dict:
    """
    Retorna a matriz do mapa.
    Enviado UMA VEZ para cada cliente ao conectar.
    """
    return {
        "linhas":  MAPA_LINHAS,
        "colunas": MAPA_COLUNAS,
        "mapa":    _mapa,
    }

def snapshot_estado(clientes: dict, projeteis: list = None) -> tuple[dict, list]:
    """
    Retorna apenas o estado dinâmico: posições + HP dos jogadores e projéteis.
    Enviado a cada tick/movimento — tamanho fixo, independente do mapa.
    """
    jogadores = {
        dados["apelido"]: {
            "x":    dados["x"],
            "y":    dados["y"],
            "time": dados.get("time"),
            "hp":   dados.get("hp", 3),
        }
        for dados in clientes.values()
        if dados.get("time") is not None
    }
    return jogadores, projeteis or []