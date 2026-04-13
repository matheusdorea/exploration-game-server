"""
server/itens.py
Power-ups no mapa: geração aleatória, coleta automática ao pisar e efeitos.

Respawn automático:
  - Máximo de QTDE_POR_TIPO itens por tipo no campo simultaneamente
  - A cada INTERVALO_RESPAWN segundos verifica se algum tipo está abaixo do limite
  - Se sim, spawna um novo item desse tipo em célula livre do campo neutro
"""
import random
import threading
import time

from server import bases as Bases
from server.projeteis import HP_INICIAL

TIPOS_ITEM       = ["cura", "escudo"]
QTDE_POR_TIPO    = 3
INTERVALO_RESPAWN = 10.0   # segundos entre cada verificação de respawn

# Contador global para IDs únicos mesmo após respawns
_contador_lock = threading.Lock()
_contador      = 0

def _novo_id() -> str:
    global _contador
    with _contador_lock:
        _contador += 1
        return f"ITEM_{_contador:03d}"


# ── Geração inicial ───────────────────────────────────────────────────────────
def gerar_itens(mapa_linhas: int, mapa_colunas: int) -> dict:
    """
    Posiciona itens aleatoriamente no campo neutro na abertura do servidor.
    Retorna dict: item_id → {tipo, x, y, disponivel, lock}
    """
    itens = {}

    x_min = Bases.BASE_A_X_MAX + 1
    x_max = Bases.BASE_B_X_MIN - 1
    y_min = 1
    y_max = mapa_linhas - 2

    if x_min > x_max:   # mapa pequeno demais para ter campo neutro
        x_min, x_max = 1, mapa_colunas - 2

    celulas = _celulas_disponiveis(x_min, x_max, y_min, y_max, ocupadas=set())
    tipos_lista = TIPOS_ITEM * QTDE_POR_TIPO
    random.shuffle(tipos_lista)

    for tipo in tipos_lista:
        if not celulas:
            break
        x, y = celulas.pop()
        item_id = _novo_id()
        itens[item_id] = _criar_entrada(tipo, x, y)

    return itens


def iniciar_respawn(itens: dict, mapa_linhas: int, mapa_colunas: int,
                    clientes_ref: dict, lock_clientes: threading.Lock,
                    on_respawn=None, log_fn=None):

    x_min = Bases.BASE_A_X_MAX + 1
    x_max = Bases.BASE_B_X_MIN - 1
    y_min = 1
    y_max = mapa_linhas - 2

    if x_min > x_max:
        x_min, x_max = 1, mapa_colunas - 2

    t = threading.Thread(
        target=_loop_respawn,
        args=(itens, x_min, x_max, y_min, y_max,
              clientes_ref, lock_clientes, on_respawn, log_fn),
        daemon=True,
    )
    t.start()


def _loop_respawn(itens, x_min, x_max, y_min, y_max,
                  clientes_ref, lock_clientes, on_respawn, log_fn):
    while True:
        time.sleep(INTERVALO_RESPAWN)
        novos = _verificar_e_spawnar(
            itens, x_min, x_max, y_min, y_max,
            clientes_ref, lock_clientes, log_fn,
        )
        if novos and on_respawn:
            on_respawn()


def _verificar_e_spawnar(itens, x_min, x_max, y_min, y_max,
                          clientes_ref, lock_clientes, log_fn) -> bool:
    """
    Para cada tipo, conta quantos estão disponíveis.
    Se estiver abaixo de QTDE_POR_TIPO, spawna UM novo item desse tipo.
    Retorna True se pelo menos um item foi criado.
    """
    # Contagem de itens disponíveis por tipo
    contagem = {tipo: 0 for tipo in TIPOS_ITEM}
    for item in itens.values():
        if item["disponivel"]:
            contagem[item["tipo"]] = contagem.get(item["tipo"], 0) + 1

    # Posições já ocupadas por itens disponíveis e por jogadores
    ocupadas = {
        (item["x"], item["y"])
        for item in itens.values()
        if item["disponivel"]
    }
    with lock_clientes:
        for dados in clientes_ref.values():
            if dados.get("time") is not None:
                ocupadas.add((dados["x"], dados["y"]))

    celulas = _celulas_disponiveis(x_min, x_max, y_min, y_max, ocupadas)

    criou_algum = False
    for tipo in TIPOS_ITEM:
        faltam = QTDE_POR_TIPO - contagem[tipo]
        for _ in range(faltam):
            if not celulas:
                break
            x, y    = celulas.pop()
            item_id = _novo_id()
            itens[item_id] = _criar_entrada(tipo, x, y)
            criou_algum = True
            if log_fn:
                log_fn(f"[ITEM] Respawn: {item_id} ({tipo}) em ({x},{y})")

    return criou_algum


# ── Coleta ────────────────────────────────────────────────────────────────────
def verificar_coleta(jogador: dict, itens: dict, log_fn=None) -> str | None:
    """
    Chamado após cada movimento. Retorna item_id coletado ou None.
    """
    px, py = jogador["x"], jogador["y"]

    for item_id, item in itens.items():
        if not item["disponivel"]:
            continue
        if item["x"] != px or item["y"] != py:
            continue

        with item["lock"]:
            if not item["disponivel"]:   # double-check dentro do lock
                continue
            item["disponivel"] = False

        _aplicar_efeito(jogador, item["tipo"])

        if log_fn:
            log_fn(
                f"[ITEM] {jogador['apelido']} coletou {item_id} "
                f"({item['tipo']}) em ({px},{py})"
            )
        return item_id

    return None


# ── Helpers internos ──────────────────────────────────────────────────────────
def _criar_entrada(tipo: str, x: int, y: int) -> dict:
    return {
        "tipo":       tipo,
        "x":          x,
        "y":          y,
        "disponivel": True,
        "lock":       threading.Lock(),
    }

def _celulas_disponiveis(x_min, x_max, y_min, y_max, ocupadas: set) -> list:
    """Retorna lista embaralhada de células livres no campo neutro."""
    celulas = [
        (x, y)
        for x in range(x_min, x_max + 1)
        for y in range(y_min, y_max + 1)
        if (x, y) not in ocupadas
    ]
    random.shuffle(celulas)
    return celulas

def _aplicar_efeito(jogador: dict, tipo: str):
    if tipo == "cura":
        jogador["hp"] = min(jogador.get("hp", HP_INICIAL) + 1, HP_INICIAL)
    elif tipo == "escudo":
        jogador["escudo"] = True

def snapshot_itens(itens: dict) -> list[dict]:
    return [
        {"id": iid, "tipo": info["tipo"], "x": info["x"], "y": info["y"]}
        for iid, info in itens.items()
        if info["disponivel"]
    ]