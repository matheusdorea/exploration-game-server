"""
server/projeteis.py
Loop de tick dos projéteis: criação, movimentação e colisões.

Extras:
  - Cadência por jogador: cooldown de COOLDOWN_TIRO segundos entre tiros
  - Recarga automática: MAX_BALAS por jogador, recarrega quando zera
  - Escudo absorve o hit (sem dano, sem morte)
  - Morte reseta HP mas NÃO manda de volta à base a cada hit
"""
import threading
import time
import uuid

from shared.protocolo import DIRECOES
from server import bases as Bases

TICK_SEGUNDOS = 0.15
HP_INICIAL    = 3
DANO_PROJETIL = 1
MAX_BALAS     = 5
TEMPO_RECARGA = 2.0

_projeteis: dict = {}
_lock_proj  = threading.Lock()

_municao: dict   = {}
_lock_mun = threading.Lock()

_clientes_ref  = None
_lock_clientes = None
_on_tick       = None
_on_atingido   = None
_on_municao    = None
_log_fn        = None
_rodando       = False
_thread        = None


def iniciar(clientes, lock_clientes, on_tick, on_atingido, log_fn, on_municao=None):
    global _clientes_ref, _lock_clientes, _on_tick, _on_atingido
    global _log_fn, _rodando, _thread, _on_municao

    _clientes_ref  = clientes
    _lock_clientes = lock_clientes
    _on_tick       = on_tick
    _on_atingido   = on_atingido
    _on_municao    = on_municao
    _log_fn        = log_fn
    _rodando       = True
    _thread        = threading.Thread(target=_loop_tick, daemon=True)
    _thread.start()


def parar():
    global _rodando
    _rodando = False


# ── Munição ───────────────────────────────────────────────────────────────────
def _get_mun(apelido: str) -> dict:
    with _lock_mun:
        if apelido not in _municao:
            _municao[apelido] = {"balas": MAX_BALAS, "recarregando_ate": 0.0}
        return _municao[apelido]

def pode_atirar(apelido: str) -> bool:
    agora = time.time()
    m = _get_mun(apelido)
    with _lock_mun:
        if agora < m["recarregando_ate"]:
            return False
        return m["balas"] > 0

def _consumir_bala(apelido: str) -> int:
    with _lock_mun:
        m = _municao[apelido]
        m["balas"] -= 1
        if m["balas"] <= 0:
            m["balas"] = 0
            m["recarregando_ate"] = time.time() + TEMPO_RECARGA
        return m["balas"]

def balas_atuais(apelido: str) -> int:
    with _lock_mun:
        return _municao.get(apelido, {}).get("balas", MAX_BALAS)


# ── Criação ───────────────────────────────────────────────────────────────────
def criar_projetil(x: int, y: int, direcao: str,
                   time_atirador: str, apelido: str, addr=None) -> bool:
    if direcao not in DIRECOES:
        return False
    if not pode_atirar(apelido):
        return False

    dx, dy    = DIRECOES[direcao]
    pid       = str(uuid.uuid4())[:8]
    restantes = _consumir_bala(apelido)

    with _lock_proj:
        _projeteis[pid] = {
            "x": x, "y": y,
            "dx": dx, "dy": dy,
            "time": time_atirador,
            "atirador": apelido,
        }

    if _on_municao and addr is not None:
        _on_municao(addr, restantes)

    return True


def snapshot_projeteis() -> list[dict]:
    with _lock_proj:
        return [{"x": p["x"], "y": p["y"]} for p in _projeteis.values()]


# ── Loop ──────────────────────────────────────────────────────────────────────
def _loop_tick():
    while _rodando:
        time.sleep(TICK_SEGUNDOS)
        _verificar_recargas()
        _tick()


def _verificar_recargas():
    agora      = time.time()
    concluidos = []

    with _lock_mun:
        for ap, m in _municao.items():
            if m["balas"] == 0 and agora >= m["recarregando_ate"] > 0:
                m["balas"] = MAX_BALAS
                m["recarregando_ate"] = 0.0
                concluidos.append(ap)

    # Notificação individual só se o callback existir
    if not concluidos or _on_municao is None:
        return

    with _lock_clientes:
        for addr, dados in list(_clientes_ref.items()):
            if dados.get("apelido") in concluidos:
                _on_municao(addr, MAX_BALAS)


def _tick():
    remover = []

    with _lock_proj:
        pids = list(_projeteis.keys())

    for pid in pids:
        with _lock_proj:
            if pid not in _projeteis:
                continue
            proj = _projeteis[pid]
            nx   = proj["x"] + proj["dx"]
            ny   = proj["y"] + proj["dy"]

        from server.mapa import eh_parede
        if eh_parede(nx, ny):
            remover.append(pid)
            continue

        if not Bases.projetil_pode_entrar(nx, ny):
            remover.append(pid)
            continue

        alvo_addr = None
        with _lock_clientes:
            for addr, dados in list(_clientes_ref.items()):
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
    # Coleta os dados necessários dentro do lock
    with _lock_clientes:
        if addr not in _clientes_ref:
            return
        dados    = _clientes_ref[addr]
        apelido  = dados["apelido"]
        time_jog = dados["time"]

        # ── Escudo absorve o hit ──────────────────────────────────────────────
        if dados.get("escudo"):
            dados["escudo"] = False
            hp_atual = dados["hp"]
            escudou  = True
        else:
            escudou  = False
            dados["hp"] -= DANO_PROJETIL
            hp_atual = dados["hp"]
            morreu   = hp_atual <= 0

            if morreu:
                dados["hp"] = HP_INICIAL
                sx, sy = Bases.spawn_time(time_jog, _clientes_ref)
                if sx is not None:
                    dados["x"] = sx
                    dados["y"] = sy

    # ── Callbacks e logs FORA do lock (evita deadlock) ────────────────────────
    if escudou:
        if _log_fn:
            _log_fn(f"🛡 {apelido} bloqueou tiro de {atirador}")
        if _on_atingido:
            _on_atingido(addr, hp_atual, atirador)
        return

    if _log_fn:
        status = "morreu e voltou à base" if morreu else f"atingido (HP={max(hp_atual, 0)})"
        _log_fn(f"💥 {apelido} {status} por {atirador}")

    if _on_atingido:
        _on_atingido(addr, max(hp_atual, 0), atirador)