"""
server/conexoes.py
Aceita pacotes UDP, registra jogadores e despacha comandos.
"""
import threading
from shared import protocolo as proto
from server import mapa as Mapa

lock = threading.Lock()
clientes: dict = {}   # addr → { apelido, x, y }

_socket     = None
_log_fn     = None   # callable(str) para exibir no painel do servidor
_rodando    = True


# ── Inicialização ─────────────────────────────────────────────────────────────
def iniciar(sock, log_fn):
    global _socket, _log_fn
    _socket  = sock
    _log_fn  = log_fn


def parar():
    global _rodando
    _rodando = False


# ── Helpers internos ──────────────────────────────────────────────────────────
def _log(msg: str):
    if _log_fn:
        _log_fn(msg)

def _enviar(addr, dados: bytes):
    try:
        _socket.sendto(dados, addr)
    except OSError:
        pass

def _broadcast_mapa(exceto=None):
    snap = Mapa.snapshot(clientes)
    dados = proto.msg_mapa(snap)
    for addr in list(clientes):
        if addr != exceto:
            _enviar(addr, dados)

def _broadcast_chat(texto: str, exceto=None):
    dados = proto.msg_chat(texto)
    for addr in list(clientes):
        if addr != exceto:
            _enviar(addr, dados)


# ── Handlers por tipo de evento ───────────────────────────────────────────────
def _registrar_jogador(addr, apelido: str):
    with lock:
        x, y = Mapa.posicao_inicial(clientes)
        if x is None:
            _enviar(addr, proto.msg_erro("Mapa cheio!"))
            return
        clientes[addr] = {"apelido": apelido, "x": x, "y": y}

    _log(f"[+] {apelido} conectou {addr} → ({x},{y})")

    snap = Mapa.snapshot(clientes)
    _enviar(addr, proto.msg_bv(f"Bem-vindo, {apelido}!", snap))
    _broadcast_chat(f"[Servidor] {apelido} entrou.", exceto=addr)
    with lock:
        _broadcast_mapa(exceto=addr)


def _desconectar(addr):
    with lock:
        dados = clientes.pop(addr, None)
    if dados:
        _log(f"[-] {dados['apelido']} desconectou {addr}")
        _broadcast_chat(f"[Servidor] {dados['apelido']} saiu.")
        with lock:
            _broadcast_mapa()


def _processar_movimento(addr, direcao: str):
    with lock:
        moveu = Mapa.mover_jogador(addr, direcao, clientes)
        if moveu:
            snap = Mapa.snapshot(clientes)

    if moveu:
        dados = proto.msg_mapa(snap)
        for a in list(clientes):
            _enviar(a, dados)
        _log(f"↕ {clientes[addr]['apelido']} → {direcao} ({clientes[addr]['x']},{clientes[addr]['y']})")
    else:
        _enviar(addr, proto.msg_erro("Movimento inválido."))


def _processar_chat(addr, texto: str):
    apelido = clientes[addr]["apelido"]
    _log(f"{apelido}: {texto}")
    _broadcast_chat(f"{apelido}: {texto}", exceto=addr)


# ── Loop principal de recebimento ─────────────────────────────────────────────
def loop_recebimento():
    global _rodando
    while _rodando:
        try:
            data, addr = _socket.recvfrom(proto.BUFFERSIZE)
            msg = data.decode().strip()

            if addr not in clientes:
                _registrar_jogador(addr, apelido=msg)
                continue

            if msg == proto.CMD_SAIR:
                _desconectar(addr)

            elif msg.startswith(proto.CMD_MOVER + " "):
                direcao = msg[len(proto.CMD_MOVER) + 1:]
                _processar_movimento(addr, direcao)

            else:
                _processar_chat(addr, msg)

        except OSError:
            break


# ── Comandos administrativos (chamados pela UI do servidor) ───────────────────
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
        return "\n".join(
            f"  {d['apelido']} ({d['x']},{d['y']})"
            for d in clientes.values()
        )

def broadcast_admin(texto: str):
    _broadcast_chat(f"[Servidor]: {texto}")