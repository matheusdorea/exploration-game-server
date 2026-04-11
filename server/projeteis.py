"""
server/projeteis.py
Loop de tick dos projéteis: criação, movimentação e colisões.
"""
import threading
import time
import uuid

from shared.protocolo import DIRECOES
from server import bases as Bases

TICK_SEGUNDOS = 0.15
HP_INICIAL    = 3
DANO_PROJETIL = 1

_projeteis: dict = {}
_lock_proj  = threading.Lock()

_clientes_ref  = None
_lock_clientes = None
_on_tick       = None   # callable() → broadcast estado
_on_atingido   = None   # callable(addr, hp, atirador)
_log_fn        = None
_rodando       = False
_thread        = None


def iniciar(clientes, lock_clientes, on_tick, on_atingido, log_fn):
    global _clientes_ref, _lock_clientes, _on_tick, _on_atingido
    global _log_fn, _rodando, _thread

    _clientes_ref  = clientes
    _lock_clientes = lock_clientes
    _on_tick       = on_tick
    _on_atingido   = on_atingido
    _log_fn        = log_fn
    _rodando       = True
    _thread        = threading.Thread(target=_loop_tick, daemon=True)
    _thread.start()


def parar():
    global _rodando
    _rodando = False


def criar_projetil(x: int, y: int, direcao: str, time_atirador: str, apelido: str):
    if direcao not in DIRECOES:
        return
    dx, dy = DIRECOES[direcao]
    pid = str(uuid.uuid4())[:8]
    with _lock_proj:
        _projeteis[pid] = {
            "x": x, "y": y,
            "dx": dx, "dy": dy,
            "time": time_atirador,
            "atirador": apelido,
        }


def snapshot_projeteis() -> list[dict]:
    with _lock_proj:
        return [{"x": p["x"], "y": p["y"]} for p in _projeteis.values()]


def _loop_tick():
    while _rodando:
        time.sleep(TICK_SEGUNDOS)
        _tick()


def _tick():
    remover = []

    with _lock_proj:
        pids = list(_projeteis.keys())

    for pid in pids:
        with _lock_proj:
            if pid not in _projeteis:
                continue
            proj = _projeteis[pid]
            nx = proj["x"] + proj["dx"]
            ny = proj["y"] + proj["dy"]

        from server.mapa import eh_parede
        if eh_parede(nx, ny):
            remover.append(pid)
            continue

        if not Bases.projetil_pode_entrar(nx, ny):
            remover.append(pid)
            continue

        alvo_addr = None
        with _lock_clientes:
            for addr, dados in _clientes_ref.items():
                if dados.get("time") is None:
                    continue
                if dados["x"] == nx and dados["y"] == ny:
                    if dados["time"] != proj["time"]:
                        alvo_addr = addr
                        break

        if alvo_addr is not None:
            remover.append(pid)
            _aplicar_dano(alvo_addr, proj["atirador"])
            continue

        with _lock_proj:
            if pid in _projeteis:
                _projeteis[pid]["x"] = nx
                _projeteis[pid]["y"] = ny

    with _lock_proj:
        for pid in remover:
            _projeteis.pop(pid, None)

    if _on_tick:
        _on_tick()


def _aplicar_dano(addr, atirador: str):
    with _lock_clientes:
        if addr not in _clientes_ref:
            return
        dados    = _clientes_ref[addr]
        dados["hp"] -= DANO_PROJETIL
        hp_atual = dados["hp"]
        apelido  = dados["apelido"]
        time_jog = dados["time"]

        if hp_atual <= 0:
            dados["hp"] = HP_INICIAL

        sx, sy = Bases.spawn_time(time_jog, _clientes_ref)
        if sx is not None:
            dados["x"] = sx
            dados["y"] = sy

    if _log_fn:
        status = "morreu e voltou à base" if hp_atual <= 0 else f"atingido (HP={max(hp_atual,0)})"
        _log_fn(f"💥 {apelido} {status} por {atirador}")

    if _on_atingido:
        _on_atingido(addr, max(hp_atual, 0), atirador)