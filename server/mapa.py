"""
server/mapa.py
Matriz do mapa, validações de movimento e snapshot de estado.
"""
from shared.protocolo import DIRECOES

MAPA_LINHAS  = 10
MAPA_COLUNAS = 20

# Células: 0 = livre, 1 = parede
def _criar_mapa() -> list[list[int]]:
    mapa = []
    for r in range(MAPA_LINHAS):
        linha = []
        for c in range(MAPA_COLUNAS):
            eh_borda = (r == 0 or r == MAPA_LINHAS - 1 or
                        c == 0 or c == MAPA_COLUNAS - 1)
            linha.append(1 if eh_borda else 0)
        mapa.append(linha)
    return mapa

_mapa: list[list[int]] = _criar_mapa()


# ── Consultas ─────────────────────────────────────────────────────────────────
def eh_parede(x: int, y: int) -> bool:
    if x < 0 or x >= MAPA_COLUNAS or y < 0 or y >= MAPA_LINHAS:
        return True
    return _mapa[y][x] == 1

def celula_livre(x: int, y: int, clientes: dict) -> bool:
    """
    Retorna True se (x, y) está dentro dos limites, não é parede
    e nenhum jogador já ocupa essa posição.
    """
    if eh_parede(x, y):
        return False
    for dados in clientes.values():
        if dados["x"] == x and dados["y"] == y:
            return False
    return True

def posicao_inicial(clientes: dict) -> tuple[int | None, int | None]:
    """Primeira célula livre do interior do mapa."""
    for r in range(1, MAPA_LINHAS - 1):
        for c in range(1, MAPA_COLUNAS - 1):
            if celula_livre(c, r, clientes):
                return c, r
    return None, None


# ── Movimento ─────────────────────────────────────────────────────────────────
def mover_jogador(addr, direcao: str, clientes: dict) -> bool:
    """
    Tenta mover o jogador em 'addr' na direção indicada.
    Retorna True se o movimento foi aplicado, False se bloqueado.
    """
    if direcao not in DIRECOES:
        return False
    dx, dy = DIRECOES[direcao]
    cx = clientes[addr]["x"]
    cy = clientes[addr]["y"]
    nx, ny = cx + dx, cy + dy

    if not celula_livre(nx, ny, clientes):
        return False

    clientes[addr]["x"] = nx
    clientes[addr]["y"] = ny
    return True


# ── Snapshot ──────────────────────────────────────────────────────────────────
def snapshot(clientes: dict) -> dict:
    """Serializa mapa + posições de todos os jogadores."""
    jogadores = {
        dados["apelido"]: {"x": dados["x"], "y": dados["y"]}
        for dados in clientes.values()
    }
    return {
        "tipo":     "mapa",
        "linhas":   MAPA_LINHAS,
        "colunas":  MAPA_COLUNAS,
        "mapa":     _mapa,
        "jogadores": jogadores,
    }