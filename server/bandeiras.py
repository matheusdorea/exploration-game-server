"""
server/bandeiras.py
Captura de bandeira (CTF).

Regras:
  - Cada time tem uma bandeira no centro da sua base.
  - Inimigo pisa na bandeira → captura (vira portador).
  - Portador chega à própria base → ponto marcado, tudo reseta.
  - Portador toma tiro → dropa a bandeira na posição atual.
  - Bandeira dropada pode ser recapturada por inimigo
    ou devolvida pelo próprio time pisando nela.
"""
import threading
from shared.protocolo import TIME_A, TIME_B
from server import bases as Bases

_lock = threading.Lock()
_bandeiras: dict = {}
_on_evento = None   # callable(texto) → broadcast chat


def configurar(on_evento=None):
    global _bandeiras, _on_evento
    _on_evento = on_evento
    _bandeiras = {
        TIME_A: _estado_inicial(TIME_A),
        TIME_B: _estado_inicial(TIME_B),
    }


def _estado_inicial(time: str) -> dict:
    if time == TIME_A:
        x = (Bases.BASE_A_X_MIN + Bases.BASE_A_X_MAX) // 2
    else:
        x = (Bases.BASE_B_X_MIN + Bases.BASE_B_X_MAX) // 2
    y = (Bases.BASE_Y_MIN + Bases.BASE_Y_MAX) // 2
    return {"portador": None, "x": x, "y": y, "no_lar": True}


def resetar():
    with _lock:
        _bandeiras[TIME_A] = _estado_inicial(TIME_A)
        _bandeiras[TIME_B] = _estado_inicial(TIME_B)


def snapshot() -> list[dict]:
    with _lock:
        return [
            {
                "time":    t,
                "portador": b["portador"],
                "x":        b["x"],
                "y":        b["y"],
                "no_lar":   b["no_lar"],
            }
            for t, b in _bandeiras.items()
        ]


def verificar_interacao(jogador: dict, clientes: dict) -> str | None:
    """
    Chame após cada movimento.
    Retorna 'ponto' | 'capturou' | 'devolveu' | None.
    """
    px, py    = jogador["x"], jogador["y"]
    time_jog  = jogador["time"]
    apelido   = jogador["apelido"]
    time_inim = TIME_B if time_jog == TIME_A else TIME_A

    with _lock:
        band_inim = _bandeiras[time_inim]
        band_prop = _bandeiras[time_jog]

        # portador chega à própria base → ponto
        if band_inim["portador"] == apelido:
            if Bases.eh_base(px, py) == time_jog:
                _bandeiras[TIME_A] = _estado_inicial(TIME_A)
                _bandeiras[TIME_B] = _estado_inicial(TIME_B)
                if _on_evento:
                    _on_evento(
                        f"[CTF] 🚩 Time {time_jog} marcou ponto! ({apelido})"
                    )
                return "ponto"

        # pisa na bandeira inimiga disponível → captura
        if (band_inim["portador"] is None
                and band_inim["x"] == px and band_inim["y"] == py):
            band_inim["portador"] = apelido
            band_inim["no_lar"]   = False
            if _on_evento:
                _on_evento(
                    f"[CTF] {apelido} pegou a bandeira do Time {time_inim}!"
                )
            return "capturou"

        # pisa na própria bandeira dropada → devolve
        if (band_prop["portador"] is None
                and not band_prop["no_lar"]
                and band_prop["x"] == px and band_prop["y"] == py):
            _bandeiras[time_jog] = _estado_inicial(time_jog)
            if _on_evento:
                _on_evento(
                    f"[CTF] {apelido} devolveu a bandeira do Time {time_jog}!"
                )
            return "devolveu"

    return None


def dropar_bandeira(apelido: str, x: int, y: int):
    """Chamado quando portador toma tiro."""
    with _lock:
        for time, band in _bandeiras.items():
            if band["portador"] == apelido:
                band["portador"] = None
                band["x"]        = x
                band["y"]        = y
                band["no_lar"]   = False
                if _on_evento:
                    _on_evento(
                        f"[CTF] 💥 {apelido} dropou a bandeira do Time {time}!"
                    )
                return


def atualizar_posicao_portador(apelido: str, x: int, y: int):
    """Mantém posição da bandeira sincronizada com o portador enquanto se move."""
    with _lock:
        for band in _bandeiras.values():
            if band["portador"] == apelido:
                band["x"] = x
                band["y"] = y