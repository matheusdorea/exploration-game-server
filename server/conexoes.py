"""
server/conexoes.py
Aceita pacotes UDP, registra jogadores e despacha comandos.

Alterações em relação à versão anterior (marcadas com # ITEM):
  1. iniciar()            → gera itens ao subir o servidor
  2. _estado_atual()      → inclui snapshot de itens no payload
  3. _processar_movimento → chama verificar_coleta após mover
"""
import threading
from shared import protocolo as proto
from server import mapa as Mapa
from server import projeteis as Projeteis
from server import bases as Bases
from server import itens as Itens          # ITEM

lock = threading.Lock()
clientes: dict = {}
_aguardando_time: dict = {}

_socket  = None
_log_fn  = None
_rodando = True

_itens: dict = {}                          # ITEM — estado global dos itens


# ── Inicialização ─────────────────────────────────────────────────────────────
def iniciar(sock, log_fn):
    global _socket, _log_fn, _itens

    _socket = sock
    _log_fn = log_fn

    # ITEM — gera itens no campo neutro
    _itens = Itens.gerar_itens(Mapa.MAPA_LINHAS, Mapa.MAPA_COLUNAS)
    _log(f"[ITENS] {len(_itens)} itens gerados no campo.")

    Projeteis.iniciar(
        clientes      = clientes,
        lock_clientes = lock,
        on_tick       = _broadcast_estado_todos,
        on_atingido   = _notificar_atingido,
        log_fn        = log_fn,
    )


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
    # ITEM — inclui posições dos itens disponíveis no payload dinâmico
    itens_snap = Itens.snapshot_itens(_itens)
    return proto.msg_estado(jogs, projs, itens_snap)

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


# ── Handlers ──────────────────────────────────────────────────────────────────
def _registrar_jogador(addr, apelido: str):
    _aguardando_time[addr] = apelido
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
            "x": x, "y": y,
            "time": time,
            "hp":   Projeteis.HP_INICIAL,
            "escudo": False,               # ITEM — flag de escudo
        }

    _log(f"[+] {apelido} → Time {time} em ({x},{y})")

    est = Mapa.snapshot_estatico()
    _enviar(addr, proto.msg_mapa_estatico(est["linhas"], est["colunas"], est["mapa"]))
    _enviar(addr, proto.msg_bv(f"Bem-vindo ao Time {time}, {apelido}! HP={Projeteis.HP_INICIAL}"))
    _enviar(addr, _estado_atual())

    _broadcast_chat(f"[Servidor] {apelido} (Time {time}) entrou.", exceto=addr)
    with lock:
        _broadcast_estado(exceto=addr)


def _desconectar(addr):
    _aguardando_time.pop(addr, None)
    with lock:
        dados = clientes.pop(addr, None)
    if dados:
        _log(f"[-] {dados['apelido']} desconectou {addr}")
        _broadcast_chat(f"[Servidor] {dados['apelido']} saiu.")
        _broadcast_estado_todos()


def _processar_movimento(addr, direcao: str):
    item_coletado = None

    with lock:
        moveu = Mapa.mover_jogador(addr, direcao, clientes)
        if moveu:
            # ITEM — verifica coleta imediatamente após o movimento (dentro do lock)
            item_coletado = Itens.verificar_coleta(
                clientes[addr], _itens, log_fn=_log
            )

    if not moveu:
        _enviar(addr, proto.msg_erro("Movimento inválido."))
        return

    _broadcast_estado_todos()

    # Notifica o coletor com o efeito aplicado
    if item_coletado:
        tipo  = _itens[item_coletado]["tipo"]
        efeito = "+1 HP" if tipo == "cura" else "escudo ativado"
        _enviar(addr, proto.msg_chat(f"[Item] Você coletou {item_coletado} ({efeito})!"))
        _broadcast_chat(
            f"[Item] {clientes[addr]['apelido']} coletou {item_coletado}!",
            exceto=addr,
        )


def _processar_tiro(addr, direcao: str):
    with lock:
        if addr not in clientes:
            return
        dados  = clientes[addr]
        time_j = dados.get("time")
        if time_j is None:
            return
        x, y   = dados["x"], dados["y"]
        apelido = dados["apelido"]

    Projeteis.criar_projetil(x, y, direcao, time_j, apelido)
    _log(f"🔫 {apelido} atirou para {direcao}")


def _processar_chat(addr, texto: str):
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

            if addr not in clientes and addr not in _aguardando_time:
                _registrar_jogador(addr, apelido=msg)
                continue

            if addr in _aguardando_time:
                if msg.startswith(proto.CMD_TIME + " "):
                    _confirmar_time(addr, msg[len(proto.CMD_TIME) + 1:])
                else:
                    _enviar(addr, proto.msg_escolha_time())
                continue

            if msg == proto.CMD_SAIR:
                _desconectar(addr)
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