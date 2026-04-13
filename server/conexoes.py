"""
server/conexoes.py
Aceita pacotes UDP, registra jogadores e despacha comandos.

Extras:
  - Ping periódico: clientes sem pong em TIMEOUT_MS são kickados.
  - Munição/recarga via projeteis.py.
  - CTF via bandeiras.py.
  - Itens aleatórios via itens.py.
"""
import threading
import time

from shared import protocolo as proto
from server import mapa      as Mapa
from server import projeteis as Projeteis
from server import bases     as Bases
from server import itens     as Itens
from server import bandeiras as Bandeiras

lock = threading.Lock()
clientes: dict = {}          # addr → dados do jogador
_aguardando_time: dict = {}  # addr → apelido (ainda escolhendo time)

_socket  = None
_log_fn  = None
_rodando = True

_itens: dict = {}

# ── Ping / timeout ────────────────────────────────────────────────────────────
TIMEOUT_MS    = 5000          # ms sem pong → kick
PING_INTERVAL = 0           # segundos entre pings

# addr → timestamp (segundos) do último pong recebido
_ultimo_pong: dict = {}
_lock_pong = threading.Lock()

# ── Inicialização ─────────────────────────────────────────────────────────────
def iniciar(sock, log_fn):
    global _socket, _log_fn, _itens

    _socket = sock
    _log_fn = log_fn

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

    # thread de ping
    t = threading.Thread(target=_loop_ping, daemon=True)
    t.start()

def parar():
    global _rodando
    _rodando = False
    Projeteis.parar()

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
    # drop de bandeira se for portador
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
        agora = time.time()
        ping_data = proto.msg_ping()

        with lock:
            addrs = list(clientes.keys())

        for addr in addrs:
            _enviar(addr, ping_data)

        time.sleep(PING_INTERVAL)

        agora_verif = time.time()
        expirados = []
        with _lock_pong:
            for addr in addrs:
                ultimo = _ultimo_pong.get(addr, 0)
                if ultimo > 0 and agora_verif - ultimo > TIMEOUT_MS / 1000:
                    expirados.append(addr)

        for addr in expirados:
            _log(f"[TIMEOUT] {addr} sem resposta — kickando.")
            _desconectar(addr, motivo="saiu por timeout")

def _registrar_pong(addr):
    with _lock_pong:
        _ultimo_pong[addr] = time.time()

# ── Handlers ──────────────────────────────────────────────────────────────────
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
    ctf_result    = None

    with lock:
        if addr not in clientes:
            return
        moveu = Mapa.mover_jogador(addr, direcao, clientes)
        if moveu:
            jog = clientes[addr]
            item_coletado = Itens.verificar_coleta(jog, _itens, log_fn=_log)
            Bandeiras.atualizar_posicao_portador(jog["apelido"], jog["x"], jog["y"])
            ctf_result = Bandeiras.verificar_interacao(jog, clientes)

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

# ── Loop de recebimento ────────────────────────────────────────────────────────
def loop_recebimento():
    global _rodando
    while _rodando:
        try:
            data, addr = _socket.recvfrom(proto.BUFFERSIZE)
            msg = data.decode().strip()

            # pong de qualquer addr registrado
            if msg == proto.CMD_PONG:
                _registrar_pong(addr)
                continue

            if addr not in clientes and addr not in _aguardando_time:
                _registrar_jogador(addr, apelido=msg)
                continue

            # atualiza pong para addrs já registrados
            _registrar_pong(addr)

            if addr in _aguardando_time:
                if msg.startswith(proto.CMD_TIME + " "):
                    _confirmar_time(addr, msg[len(proto.CMD_TIME) + 1:])
                else:
                    _enviar(addr, proto.msg_escolha_time())
                continue

            if msg == proto.CMD_SAIR:
                _desconectar(addr, motivo="saiu")
            elif msg.startswith(proto.CMD_MOVER + " "):
                _processar_movimento(addr, msg[len(proto.CMD_MOVER) + 1:])
            elif msg.startswith(proto.CMD_ATIRAR + " "):
                _processar_tiro(addr, msg[len(proto.CMD_ATIRAR) + 1:])
            else:
                _processar_chat(addr, msg)

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
        for d in clientes.values():
            escudo = " 🛡" if d.get("escudo") else ""
            linhas.append(
                f"  [{d['time']}] {d['apelido']}  "
                f"pos:({d['x']},{d['y']})  HP:{d['hp']}{escudo}"
            )
        return "\n".join(linhas)

def broadcast_admin(texto: str):
    _broadcast_chat(f"[Servidor]: {texto}")