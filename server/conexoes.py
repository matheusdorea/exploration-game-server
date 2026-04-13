"""
server/conexoes.py
Aceita pacotes UDP, registra jogadores e despacha comandos.

Balanceamento de carga via ThreadPoolExecutor:
  - O loop de recebimento é apenas um dispatcher — recebe, classifica,
    submete. Nunca processa inline.
  - Cada pacote vira uma Future independente na pool.
  - Tarefas lentas (coleta de item, CTF) não bloqueiam pacotes seguintes.
  - Tamanho da pool configurável via POOL_WORKERS (padrão: 4).

Threads que já existiam e continuam separadas:
  - loop_recebimento  → dispatcher UDP (1 thread dedicada)
  - projeteis._thread → tick de física (1 thread dedicada)
  - _loop_ping        → keepalive periódico (1 thread dedicada)
  - ThreadPoolExecutor → workers de lógica de jogo (POOL_WORKERS threads)
"""
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
# Regra prática: 2–4× o número de cores lógicos é um bom ponto de partida
# para workloads mistos (I/O leve + lógica de jogo).
# Pode ser ajustado via variável de ambiente POOL_WORKERS.
import os
POOL_WORKERS = int(os.environ.get("POOL_WORKERS", 4))

lock = threading.Lock()
clientes: dict = {}
_aguardando_time: dict = {}

_socket  = None
_log_fn  = None
_rodando = True
_pool: ThreadPoolExecutor = None

_itens: dict = {}

# ── Ping / timeout ────────────────────────────────────────────────────────────
TIMEOUT_MS    = 5000
PING_INTERVAL = 2

_ultimo_pong: dict = {}
_lock_pong = threading.Lock()

# ── Inicialização ─────────────────────────────────────────────────────────────
def iniciar(sock, log_fn):
    global _socket, _log_fn, _itens, _pool

    _socket = sock
    _log_fn = log_fn

    # Cria a pool antes de qualquer worker precisar dela
    _pool = ThreadPoolExecutor(
        max_workers=POOL_WORKERS,
        thread_name_prefix="game-worker",
    )
    _log(f"[POOL] ThreadPoolExecutor iniciada com {POOL_WORKERS} workers.")

    _itens = Itens.gerar_itens(Mapa.MAPA_LINHAS, Mapa.MAPA_COLUNAS)
    _log(f"[ITENS] {len(_itens)} itens gerados no campo.")

    Bandeiras.configurar(on_evento=_broadcast_chat)
    _log("[CTF] Bandeiras posicionadas.")

    Projeteis.iniciar(
        clientes      = clientes,
        lock_clientes = lock,
        on_tick       = _broadcast_estado_todos,
        on_atingido   = _notificar_atingido,
        log_fn        = log_fn,
        on_municao    = _notificar_municao,
    )

    t = threading.Thread(target=_loop_ping, daemon=True)
    t.start()


def parar():
    global _rodando
    _rodando = False
    Projeteis.parar()
    if _pool:
        # Aguarda tasks em andamento terminarem (até 2 s) antes de fechar
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

def _estado_atual():
    jogs, projs = Mapa.snapshot_estado(clientes, Projeteis.snapshot_projeteis())
    itens_snap  = Itens.snapshot_itens(_itens)
    bands_snap  = Bandeiras.snapshot()
    return proto.msg_estado(jogs, projs, itens_snap, bands_snap)

def _broadcast_estado_todos():
    dados = _estado_atual()
    with lock:
        for addr in list(clientes):
            _enviar(addr, dados)

def _broadcast_estado(exceto=None):
    dados = _estado_atual()
    for addr in list(clientes):
        if addr != exceto:
            _enviar(addr, dados)

def _broadcast_chat(texto: str, exceto=None):
    dados = proto.msg_chat(texto)
    for addr in list(clientes):
        if addr != exceto:
            _enviar(addr, dados)

def _notificar_atingido(addr, hp: int, atirador: str):
    _enviar(addr, proto.msg_atingido(hp, atirador))
    with lock:
        if addr not in clientes:
            return
        jog = clientes[addr]
    Bandeiras.dropar_bandeira(jog["apelido"], jog["x"], jog["y"])
    _broadcast_estado_todos()

def _notificar_municao(addr, qtd: int):
    _enviar(addr, proto.msg_municao(qtd))

def _loop_ping():
    while _rodando:
        agora     = time.time()
        ping_data = proto.msg_ping()

        with lock:
            addrs = list(clientes.keys())

        for addr in addrs:
            _enviar(addr, ping_data)

        time.sleep(PING_INTERVAL)

        agora_verif = time.time()
        expirados   = []
        with _lock_pong:
            for addr in addrs:
                ultimo = _ultimo_pong.get(addr, 0)
                if ultimo > 0 and agora_verif - ultimo > TIMEOUT_MS / 1000:
                    expirados.append(addr)

        for addr in expirados:
            _log(f"[TIMEOUT] {addr} sem resposta — kickando.")
            # Submete o kick na pool para não bloquear o ping thread
            if _pool:
                _pool.submit(_desconectar, addr, "saiu por timeout")

def _registrar_pong(addr):
    with _lock_pong:
        _ultimo_pong[addr] = time.time()


# ── Handlers (executados pelos workers da pool) ───────────────────────────────
def _registrar_jogador(addr, apelido: str):
    _aguardando_time[addr] = apelido
    with _lock_pong:
        _ultimo_pong[addr] = time.time()
    _log(f"[?] {apelido} conectou {addr} — aguardando time")
    _enviar(addr, proto.msg_escolha_time())


def _confirmar_time(addr, time: str):
    time = time.upper()
    if time not in (proto.TIME_A, proto.TIME_B):
        _enviar(addr, proto.msg_erro("Time inválido. Use /time A ou /time B"))
        return

    apelido = _aguardando_time.pop(addr, None)
    if apelido is None:
        return

    with lock:
        x, y = Mapa.posicao_inicial(clientes, time)
        if x is None:
            _enviar(addr, proto.msg_erro("Base cheia! Tente o outro time."))
            _aguardando_time[addr] = apelido
            return

        clientes[addr] = {
            "apelido": apelido,
            "x":       x,
            "y":       y,
            "time":    time,
            "hp":      Projeteis.HP_INICIAL,
            "escudo":  False,
        }

    _log(f"[+] {apelido} → Time {time} em ({x},{y})")

    est = Mapa.snapshot_estatico()
    _enviar(addr, proto.msg_mapa_estatico(est["linhas"], est["colunas"], est["mapa"]))
    _enviar(addr, proto.msg_bv(
        f"Bem-vindo ao Time {time}, {apelido}! HP={Projeteis.HP_INICIAL}"
    ))
    _enviar(addr, _estado_atual())

    _broadcast_chat(f"[Servidor] {apelido} (Time {time}) entrou.", exceto=addr)
    with lock:
        _broadcast_estado(exceto=addr)


def _desconectar(addr, motivo: str = "saiu"):
    _aguardando_time.pop(addr, None)
    with _lock_pong:
        _ultimo_pong.pop(addr, None)
    with lock:
        dados = clientes.pop(addr, None)
    if dados:
        apelido = dados["apelido"]
        Bandeiras.dropar_bandeira(apelido, dados["x"], dados["y"])
        _log(f"[-] {apelido} desconectou ({motivo})")
        _broadcast_chat(f"[Servidor] {apelido} {motivo}.")
        _broadcast_estado_todos()


def _processar_movimento(addr, direcao: str):
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
        _enviar(addr, proto.msg_chat(
            f"[Item] Você coletou {item_coletado} ({efeito})!"
        ))
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


# ── Loop de recebimento — apenas dispatcher ───────────────────────────────────
def loop_recebimento():
    """
    Esta thread NUNCA processa lógica de jogo.
    Só recebe, identifica o tipo de pacote e submete o handler correto
    à ThreadPoolExecutor. Isso garante que um pacote lento não atrase
    os seguintes — o loop volta a escutar imediatamente.
    """
    global _rodando
    while _rodando:
        try:
            data, addr = _socket.recvfrom(proto.BUFFERSIZE)
            msg = data.decode().strip()

            # ── Pong é tratado inline (µs, sem lógica) ────────────────────────
            if msg == proto.CMD_PONG:
                _registrar_pong(addr)
                continue

            # ── Novo cliente ──────────────────────────────────────────────────
            if addr not in clientes and addr not in _aguardando_time:
                _pool.submit(_registrar_jogador, addr, msg)
                continue

            # Atualiza keepalive para clientes registrados
            _registrar_pong(addr)

            # ── Escolha de time (cliente ainda não entrou) ────────────────────
            if addr in _aguardando_time:
                if msg.startswith(proto.CMD_TIME + " "):
                    _pool.submit(
                        _confirmar_time,
                        addr,
                        msg[len(proto.CMD_TIME) + 1:],
                    )
                else:
                    _pool.submit(_enviar, addr, proto.msg_escolha_time())
                continue

            # ── Comandos de jogo ──────────────────────────────────────────────
            if msg == proto.CMD_SAIR:
                _pool.submit(_desconectar, addr, "saiu")

            elif msg.startswith(proto.CMD_MOVER + " "):
                _pool.submit(
                    _processar_movimento,
                    addr,
                    msg[len(proto.CMD_MOVER) + 1:],
                )

            elif msg.startswith(proto.CMD_ATIRAR + " "):
                _pool.submit(
                    _processar_tiro,
                    addr,
                    msg[len(proto.CMD_ATIRAR) + 1:],
                )

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
        workers_ativos = _pool._work_queue.qsize() if _pool else 0
        linhas.append(f"  [Pool] tasks na fila: {workers_ativos}")
        for d in clientes.values():
            escudo = " 🛡" if d.get("escudo") else ""
            linhas.append(
                f"  [{d['time']}] {d['apelido']}  "
                f"pos:({d['x']},{d['y']})  HP:{d['hp']}{escudo}"
            )
        return "\n".join(linhas)


def broadcast_admin(texto: str):
    _broadcast_chat(f"[Servidor]: {texto}")