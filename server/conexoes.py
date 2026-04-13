"""
server/conexoes.py
Aceita pacotes UDP, registra jogadores e despacha comandos.

Arquitetura de threads:
  - loop_recebimento  → dispatcher UDP puro (1 thread dedicada)
  - projeteis._thread → tick de física (1 thread dedicada)
  - _loop_ping        → keepalive periódico (1 thread dedicada)
  - ThreadPoolExecutor→ workers de lógica de jogo (POOL_WORKERS threads)

Segurança:
  - Throttle de movimento server-side: rejeita movimentos mais rápidos
    que THROTTLE_MOVIMENTO_MS entre pacotes consecutivos do mesmo addr.
  - Estado autoritativo: HP, balas, escudo e bandeira são lidos do servidor
    e embutidos no campo "meu_estado" de cada pacote enviado individualmente.
  - Cliente não guarda nem valida nenhum desses valores.
"""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from shared import protocolo as proto
from server import mapa      as Mapa
from server import projeteis as Projeteis
from server import bases     as Bases
from server import itens     as Itens
from server import bandeiras as Bandeiras

# ── Configuração da pool ──────────────────────────────────────────────────────
POOL_WORKERS = int(os.environ.get("POOL_WORKERS", 4))

lock = threading.Lock()
clientes: dict         = {}
_aguardando_time: dict = {}

_socket  = None
_log_fn  = None
_rodando = True
_pool: ThreadPoolExecutor = None
_itens: dict = {}

# ── Ping / timeout ────────────────────────────────────────────────────────────
PING_INTERVAL_S = 2
TIMEOUT_S       = 5

_ultimo_pong: dict = {}
_lock_pong = threading.Lock()

# ── Throttle de movimento server-side ─────────────────────────────────────────
THROTTLE_MOVIMENTO_MS = 100
_ultimo_movimento: dict = {}
_lock_throttle = threading.Lock()


# ── Inicialização ─────────────────────────────────────────────────────────────
def iniciar(sock, log_fn):
    global _socket, _log_fn, _itens, _pool

    _socket = sock
    _log_fn = log_fn

    _pool = ThreadPoolExecutor(
        max_workers=POOL_WORKERS,
        thread_name_prefix="game-worker",
    )
    _log(f"[POOL] ThreadPoolExecutor iniciada com {POOL_WORKERS} workers.")

    _itens = Itens.gerar_itens(Mapa.MAPA_LINHAS, Mapa.MAPA_COLUNAS)
    _log(f"[ITENS] {len(_itens)} itens gerados no campo.")

    Itens.iniciar_respawn(
        itens         = _itens,
        mapa_linhas   = Mapa.MAPA_LINHAS,
        mapa_colunas  = Mapa.MAPA_COLUNAS,
        clientes_ref  = clientes,
        lock_clientes = lock,
        on_respawn    = _broadcast_estado_todos,
        log_fn        = _log,
    )
    _log(f"[ITENS] Respawn automático iniciado (intervalo={Itens.INTERVALO_RESPAWN}s).")

    Bandeiras.configurar(on_evento=_broadcast_chat)
    _log("[CTF] Bandeiras posicionadas.")

    Projeteis.iniciar(
        clientes      = clientes,
        lock_clientes = lock,
        on_tick       = _broadcast_estado_todos,
        on_atingido   = _notificar_atingido,
        log_fn        = log_fn,
        on_municao    = None,   # municao vem no meu_estado, não em msg separada
    )

    threading.Thread(target=_loop_ping, daemon=True).start()


def parar():
    global _rodando
    _rodando = False
    Projeteis.parar()
    if _pool:
        _pool.shutdown(wait=True, cancel_futures=False)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _log(msg: str):
    if _log_fn:
        _log_fn(msg)

def _enviar(addr, dados: bytes):
    try:
        _socket.sendto(dados, addr)
    except OSError:
        pass

def _meu_estado_para(addr) -> dict:
    """
    Monta o bloco de estado pessoal do jogador lendo do dict autoritativo
    do servidor. Embutido em cada pacote enviado individualmente ao cliente.
    """
    dados   = clientes.get(addr, {})
    apelido = dados.get("apelido", "")

    snap_bands        = Bandeiras.snapshot()
    portando_bandeira = any(b.get("portador") == apelido for b in snap_bands)

    return {
        "hp":       dados.get("hp",     Projeteis.HP_INICIAL),
        "balas":    Projeteis.balas_atuais(apelido),
        "escudo":   dados.get("escudo", False),
        "bandeira": portando_bandeira,
        "time":     dados.get("time",   ""),
    }

def _estado_payload() -> tuple:
    """Retorna os componentes do estado global (sem meu_estado)."""
    jogs, projs = Mapa.snapshot_estado(clientes, Projeteis.snapshot_projeteis())
    itens_snap  = Itens.snapshot_itens(_itens)
    bands_snap  = Bandeiras.snapshot()
    return jogs, projs, itens_snap, bands_snap

def _enviar_estado(addr):
    """Envia estado global + meu_estado personalizado para um único cliente."""
    jogs, projs, itens_snap, bands_snap = _estado_payload()
    meu   = _meu_estado_para(addr)
    dados = proto.msg_estado(jogs, projs, itens_snap, bands_snap, meu_estado=meu)
    _enviar(addr, dados)

def _broadcast_estado_todos():
    """Envia estado personalizado para cada cliente individualmente."""
    jogs, projs, itens_snap, bands_snap = _estado_payload()
    with lock:
        for addr in list(clientes):
            meu   = _meu_estado_para(addr)
            dados = proto.msg_estado(jogs, projs, itens_snap, bands_snap, meu_estado=meu)
            _enviar(addr, dados)

def _broadcast_estado(exceto=None):
    jogs, projs, itens_snap, bands_snap = _estado_payload()
    for addr in list(clientes):
        if addr == exceto:
            continue
        meu   = _meu_estado_para(addr)
        dados = proto.msg_estado(jogs, projs, itens_snap, bands_snap, meu_estado=meu)
        _enviar(addr, dados)

def _broadcast_chat(texto: str, exceto=None):
    dados = proto.msg_chat(texto)
    for addr in list(clientes):
        if addr != exceto:
            _enviar(addr, dados)

def _notificar_atingido(addr, hp: int, atirador: str):
    """
    Ao ser atingido: envia notificação textual + estado atualizado.
    Sem msg_atingido separada — HP autoritativo chega no meu_estado.
    """
    msg = (
        f"☠ Você foi eliminado por {atirador}! Voltando à base..."
        if hp == 0 else
        f"💥 Você foi atingido por {atirador}! HP={hp}"
    )
    _enviar(addr, proto.msg_chat(msg))

    with lock:
        if addr not in clientes:
            return
        jog = clientes[addr]
    Bandeiras.dropar_bandeira(jog["apelido"], jog["x"], jog["y"])
    _broadcast_estado_todos()


# ── Ping / keepalive ──────────────────────────────────────────────────────────
def _loop_ping():
    while _rodando:
        ping_data = proto.msg_ping()
        with lock:
            addrs = list(clientes.keys())

        for addr in addrs:
            _enviar(addr, ping_data)

        time.sleep(PING_INTERVAL_S)

        expirados = []
        with _lock_pong:
            for addr in addrs:
                ultimo = _ultimo_pong.get(addr, 0)
                if ultimo > 0 and time.time() - ultimo > TIMEOUT_S:
                    expirados.append(addr)

        for addr in expirados:
            ap = clientes.get(addr, {}).get("apelido", str(addr))
            _log(f"[TIMEOUT] {ap} sem resposta — kickando.")
            if _pool:
                _pool.submit(_desconectar, addr, "saiu por timeout")

def _registrar_pong(addr):
    with _lock_pong:
        _ultimo_pong[addr] = time.time()


# ── Throttle de movimento ─────────────────────────────────────────────────────
def _pode_mover(addr) -> bool:
    agora = time.time()
    with _lock_throttle:
        ultimo = _ultimo_movimento.get(addr, 0)
        if agora - ultimo < THROTTLE_MOVIMENTO_MS / 1000:
            return False
        _ultimo_movimento[addr] = agora
        return True


# ── Handlers (executados pelos workers da pool) ───────────────────────────────
def _registrar_jogador(addr, data: bytes):
    """
    Valida a versão do cliente antes de qualquer outra coisa.
    Rejeita silenciosamente (com msg_versao_invalida) se a versão divergir.
    """
    apelido, versao_cliente = proto.decode_handshake(data)

    if not apelido:
        return   # pacote malformado — ignora

    if versao_cliente != proto.VERSAO:
        _log(
            f"[VERSAO] {addr} rejeitado — "
            f"cliente={versao_cliente!r} servidor={proto.VERSAO!r}"
        )
        _enviar(addr, proto.msg_versao_invalida(proto.VERSAO))
        return

    _enviar(addr, proto.msg_versao_ok())
    _aguardando_time[addr] = apelido
    with _lock_pong:
        _ultimo_pong[addr] = time.time()
    _log(f"[?] {apelido} conectou {addr} (v{versao_cliente}) — aguardando time")
    _enviar(addr, proto.msg_escolha_time())


def _confirmar_time(addr, time_escolhido: str):
    time_escolhido = time_escolhido.upper()
    if time_escolhido not in (proto.TIME_A, proto.TIME_B):
        _enviar(addr, proto.msg_erro("Time inválido. Use /time A ou /time B"))
        return

    apelido = _aguardando_time.pop(addr, None)
    if apelido is None:
        return

    with lock:
        x, y = Mapa.posicao_inicial(clientes, time_escolhido)
        if x is None:
            _enviar(addr, proto.msg_erro("Base cheia! Tente o outro time."))
            _aguardando_time[addr] = apelido
            return

        clientes[addr] = {
            "apelido": apelido,
            "x":       x,
            "y":       y,
            "time":    time_escolhido,
            "hp":      Projeteis.HP_INICIAL,
            "escudo":  False,
        }

    with _lock_throttle:
        _ultimo_movimento[addr] = 0.0

    _log(f"[+] {apelido} → Time {time_escolhido} em ({x},{y})")

    est = Mapa.snapshot_estatico()
    _enviar(addr, proto.msg_mapa_estatico(est["linhas"], est["colunas"], est["mapa"]))
    _enviar(addr, proto.msg_bv(
        f"Bem-vindo ao Time {time_escolhido}, {apelido}! "
        f"HP={Projeteis.HP_INICIAL} | Balas={Projeteis.MAX_BALAS}"
    ))
    _enviar_estado(addr)

    _broadcast_chat(f"[Servidor] {apelido} (Time {time_escolhido}) entrou.", exceto=addr)
    with lock:
        _broadcast_estado(exceto=addr)


def _desconectar(addr, motivo: str = "saiu"):
    _aguardando_time.pop(addr, None)
    with _lock_pong:
        _ultimo_pong.pop(addr, None)
    with _lock_throttle:
        _ultimo_movimento.pop(addr, None)
    with lock:
        dados = clientes.pop(addr, None)
    if dados:
        apelido = dados["apelido"]
        Bandeiras.dropar_bandeira(apelido, dados["x"], dados["y"])
        _log(f"[-] {apelido} desconectou ({motivo})")
        _broadcast_chat(f"[Servidor] {apelido} {motivo}.")
        _broadcast_estado_todos()


def _processar_movimento(addr, direcao: str):
    # Throttle server-side: ignora silenciosamente se rápido demais
    if not _pode_mover(addr):
        return

    item_coletado = None

    with lock:
        if addr not in clientes:
            return
        moveu = Mapa.mover_jogador(addr, direcao, clientes)
        if moveu:
            jog = clientes[addr]
            item_coletado = Itens.verificar_coleta(jog, _itens, log_fn=_log)
            Bandeiras.atualizar_posicao_portador(jog["apelido"], jog["x"], jog["y"])
            Bandeiras.verificar_interacao(jog, clientes)

    if not moveu:
        _enviar(addr, proto.msg_erro("Movimento inválido."))
        return

    _broadcast_estado_todos()

    if item_coletado:
        tipo   = _itens[item_coletado]["tipo"]
        efeito = "+1 HP" if tipo == "cura" else "escudo ativado"
        _enviar(addr, proto.msg_chat(f"[Item] Você coletou {item_coletado} ({efeito})!"))
        with lock:
            nome = clientes[addr]["apelido"] if addr in clientes else "?"
        _broadcast_chat(f"[Item] {nome} coletou {item_coletado}!", exceto=addr)


def _processar_tiro(addr, direcao: str):
    with lock:
        if addr not in clientes:
            return
        dados   = clientes[addr]
        time_j  = dados.get("time")
        if time_j is None:
            return
        x, y    = dados["x"], dados["y"]
        apelido = dados["apelido"]

    atirou = Projeteis.criar_projetil(x, y, direcao, time_j, apelido, addr=addr)
    if atirou:
        _log(f"🔫 {apelido} atirou para {direcao}")
    else:
        _enviar(addr, proto.msg_erro("Sem balas! Aguarde recarga."))


def _processar_chat(addr, texto: str):
    with lock:
        if addr not in clientes:
            return
        apelido = clientes[addr]["apelido"]
    _log(f"{apelido}: {texto}")
    _broadcast_chat(f"{apelido}: {texto}", exceto=addr)


# ── Loop de recebimento — dispatcher puro ─────────────────────────────────────
def loop_recebimento():
    """
    Esta thread NUNCA processa lógica de jogo.
    Recebe, classifica e submete o handler correto à pool.
    O loop volta a escutar imediatamente após cada submit.
    """
    global _rodando
    while _rodando:
        try:
            data, addr = _socket.recvfrom(proto.BUFFERSIZE)
            msg = data.decode().strip()

            # Pong tratado inline — µs, sem lógica de jogo
            if msg == proto.CMD_PONG:
                _registrar_pong(addr)
                continue

            if addr not in clientes and addr not in _aguardando_time:
                _pool.submit(_registrar_jogador, addr, data)
                continue

            _registrar_pong(addr)

            if addr in _aguardando_time:
                if msg.startswith(proto.CMD_TIME + " "):
                    _pool.submit(_confirmar_time, addr, msg[len(proto.CMD_TIME) + 1:])
                else:
                    _pool.submit(_enviar, addr, proto.msg_escolha_time())
                continue

            if msg == proto.CMD_SAIR:
                _pool.submit(_desconectar, addr, "saiu")
            elif msg.startswith(proto.CMD_MOVER + " "):
                _pool.submit(_processar_movimento, addr, msg[len(proto.CMD_MOVER) + 1:])
            elif msg.startswith(proto.CMD_ATIRAR + " "):
                _pool.submit(_processar_tiro, addr, msg[len(proto.CMD_ATIRAR) + 1:])
            else:
                _pool.submit(_processar_chat, addr, msg)

        except OSError:
            break


# ── Admin ──────────────────────────────────────────────────────────────────────
def desligar():
    dados = proto.msg_chat("/desligar")
    with lock:
        for addr in list(clientes):
            _enviar(addr, dados)
    parar()
    _socket.close()

def listar_online() -> str:
    with lock:
        if not clientes:
            return "  Nenhum jogador conectado."
        linhas = []
        fila = _pool._work_queue.qsize() if _pool else 0
        linhas.append(f"  [Pool] tasks na fila: {fila}")
        for addr, d in clientes.items():
            escudo = " 🛡" if d.get("escudo") else ""
            balas  = Projeteis.balas_atuais(d["apelido"])
            linhas.append(
                f"  [{d['time']}] {d['apelido']}  "
                f"pos:({d['x']},{d['y']})  HP:{d['hp']}  🔫{balas}{escudo}"
            )
        return "\n".join(linhas)

def broadcast_admin(texto: str):
    _broadcast_chat(f"[Servidor]: {texto}")