"""
server/itens.py
Power-ups no mapa: geração aleatória, coleta automática ao pisar e efeitos.
"""
import random
import threading

from server import bases as Bases
from server.projeteis import HP_INICIAL

TIPOS_ITEM    = ["cura", "escudo"]
QTDE_POR_TIPO = 3

def gerar_itens(mapa_linhas: int, mapa_colunas: int) -> dict:
    """
    Posiciona itens aleatoriamente no campo neutro (fora das bases, dentro das bordas).
    Retorna dict: item_id → {tipo, x, y, disponivel, lock}
    """
    itens    = {}
    contador = 1

    x_min = Bases.BASE_A_X_MAX + 1
    x_max = Bases.BASE_B_X_MIN - 1
    y_min = 1
    y_max = mapa_linhas - 2

    if x_min > x_max:
        x_min, x_max = 1, mapa_colunas - 2

    celulas = [
        (x, y)
        for x in range(x_min, x_max + 1)
        for y in range(y_min, y_max + 1)
    ]
    random.shuffle(celulas)

    tipos_lista = TIPOS_ITEM * QTDE_POR_TIPO
    random.shuffle(tipos_lista)

    for tipo in tipos_lista:
        if not celulas:
            break
        x, y    = celulas.pop()
        item_id = f"ITEM_{contador:03d}"
        itens[item_id] = {
            "tipo":       tipo,
            "x":          x,
            "y":          y,
            "disponivel": True,
            "lock":       threading.Lock(),
        }
        contador += 1

    return itens

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
            if not item["disponivel"]:
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