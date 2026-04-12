"""
server/itens.py
Power-ups no mapa: geração, coleta automática ao pisar e efeitos.

Design:
  - Servidor é autoridade total. Sem criptografia — não é necessária.
  - Ao processar um movimento, conexoes.py chama `verificar_coleta(addr)`.
  - Se o jogador estiver na mesma célula que um item disponível, o efeito
    é aplicado imediatamente no estado do servidor e o item some do mapa.
  - O snapshot público dos itens (posições, sem dados internos) é incluído
    em cada msg_estado, para o cliente renderizar os ícones no mapa.

Tipos de item (efeito aplicado pelo servidor):
  - "cura"    → +1 HP, limitado ao HP_INICIAL
  - "escudo"  → próximo hit não causa dano (flag no estado do jogador)
"""

import threading
from server import bases as Bases
from server.projeteis import HP_INICIAL

# ── Tipos e seus efeitos ──────────────────────────────────────────────────────
TIPOS_ITEM = ["cura", "escudo"]

# Quantos itens de cada tipo gerar no início
QTDE_POR_TIPO = 3


# ── Geração ───────────────────────────────────────────────────────────────────
def gerar_itens(mapa_linhas: int, mapa_colunas: int) -> dict:
    """
    Posiciona itens no campo neutro (fora das bases, dentro das bordas).
    Retorna dict:  item_id → { tipo, x, y, disponivel, lock }
    """
    itens   = {}
    ocupadas = set()
    contador = 1

    # Limites do campo neutro (entre as duas bases)
    x_min = Bases.BASE_A_X_MAX + 1
    x_max = Bases.BASE_B_X_MIN - 1
    y_min = 1
    y_max = mapa_linhas - 2

    if x_min > x_max:
        # Mapa pequeno demais — coloca nos extremos mesmo
        x_min, x_max = 1, mapa_colunas - 2

    tipos_ciclo = TIPOS_ITEM * QTDE_POR_TIPO

    for tipo in tipos_ciclo:
        for y in range(y_min, y_max + 1):
            for x in range(x_min, x_max + 1):
                if (x, y) not in ocupadas:
                    item_id = f"ITEM_{contador:03d}"
                    itens[item_id] = {
                        "tipo":       tipo,
                        "x":          x,
                        "y":          y,
                        "disponivel": True,
                        "lock":       threading.Lock(),
                    }
                    ocupadas.add((x, y))
                    contador += 1
                    break   # próximo tipo
            else:
                continue
            break

    return itens


# ── Coleta ────────────────────────────────────────────────────────────────────
def verificar_coleta(jogador: dict, itens: dict, log_fn=None) -> str | None:
    """
    Chamado após cada movimento bem-sucedido.
    Verifica se o jogador está na mesma célula que algum item disponível.
    Se sim, aplica o efeito no dicionário `jogador` e marca o item como coletado.

    Retorna o item_id coletado (para broadcast de notificação) ou None.
    """
    px, py = jogador["x"], jogador["y"]

    for item_id, item in itens.items():
        if not item["disponivel"]:
            continue
        if item["x"] != px or item["y"] != py:
            continue

        # Lock por item — movimento de dois jogadores simultâneos na mesma célula
        with item["lock"]:
            if not item["disponivel"]:
                continue  # outro jogador pegou no mesmo instante
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


# ── Snapshot público ──────────────────────────────────────────────────────────
def snapshot_itens(itens: dict) -> list[dict]:
    """
    Apenas posição e tipo dos itens disponíveis.
    Incluído em cada msg_estado — o cliente usa para renderizar no mapa.
    Itens coletados simplesmente não aparecem.
    """
    return [
        {"id": iid, "tipo": info["tipo"], "x": info["x"], "y": info["y"]}
        for iid, info in itens.items()
        if info["disponivel"]
    ]