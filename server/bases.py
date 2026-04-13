"""
server/bases.py
Zonas de base proporcionais ao tamanho do mapa.

As bases ocupam:
  - Largura : BASE_LARGURA_FRAC  das colunas internas (padrão 15%)
  - Altura  : 100% das linhas internas (do topo ao fundo, excluindo bordas)

Isso garante que ao mudar MAPA_LINHAS / MAPA_COLUNAS em mapa.py as bases
se reposicionam automaticamente sem precisar ajustar nada aqui.
"""
from shared.protocolo import TIME_A, TIME_B

# Fração das colunas internas reservada para cada base (0.0 – 1.0)
BASE_LARGURA_FRAC = 0.15
# Mínimo de colunas por base (para mapas muito pequenos)
BASE_LARGURA_MIN  = 3

_linhas  = None
_colunas = None

# Limites calculados ao inicializar
BASE_A_X_MIN: int = 0
BASE_A_X_MAX: int = 0
BASE_B_X_MIN: int = 0
BASE_B_X_MAX: int = 0
BASE_Y_MIN:   int = 0
BASE_Y_MAX:   int = 0


def configurar(linhas: int, colunas: int):
    """
    Chamado por mapa.py ao definir as dimensões.
    Recalcula os limites de cada base proporcionalmente.
    """
    global _linhas, _colunas
    global BASE_A_X_MIN, BASE_A_X_MAX
    global BASE_B_X_MIN, BASE_B_X_MAX
    global BASE_Y_MIN, BASE_Y_MAX

    _linhas  = linhas
    _colunas = colunas

    # Colunas internas: 1 .. colunas-2
    colunas_internas = colunas - 2
    larg = max(BASE_LARGURA_MIN, int(colunas_internas * BASE_LARGURA_FRAC))

    BASE_A_X_MIN = 1
    BASE_A_X_MAX = larg                        # ex: col 1-6 num mapa de 40

    BASE_B_X_MAX = colunas - 2                 # última coluna interna
    BASE_B_X_MIN = BASE_B_X_MAX - larg + 1    # ex: col 33-38 num mapa de 40

    BASE_Y_MIN = 1
    BASE_Y_MAX = linhas - 2                    # todas as linhas internas


def eh_base(x: int, y: int) -> str | None:
    """Retorna o time dono da base em (x,y), ou None se não for base."""
    if BASE_Y_MIN <= y <= BASE_Y_MAX:
        if BASE_A_X_MIN <= x <= BASE_A_X_MAX:
            return TIME_A
        if BASE_B_X_MIN <= x <= BASE_B_X_MAX:
            return TIME_B
    return None


def pode_entrar(x: int, y: int, time_jogador: str) -> bool:
    dono = eh_base(x, y)
    if dono is None:
        return True
    return dono == time_jogador


def projetil_pode_entrar(x: int, y: int) -> bool:
    """Nenhum projétil entra em base alguma."""
    return eh_base(x, y) is None


def spawn_time(time: str, clientes: dict) -> tuple[int | None, int | None]:
    """Primeira célula livre dentro da base do time."""
    if time == TIME_A:
        xs = range(BASE_A_X_MIN, BASE_A_X_MAX + 1)
    else:
        xs = range(BASE_B_X_MIN, BASE_B_X_MAX + 1)

    ocupadas = {(d["x"], d["y"]) for d in clientes.values()}

    from server import mapa
    
    for y in range(BASE_Y_MIN, BASE_Y_MAX + 1):
        for x in xs:
            if (x, y) not in ocupadas and not mapa.eh_parede(x, y):
                return x, y

    return None, None