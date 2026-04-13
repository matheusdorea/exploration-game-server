"""
cliente.py — Entry point do cliente UDP.

Responsabilidade do cliente: enviar intenções e renderizar o estado
que o servidor manda. Nenhum valor de jogo (HP, balas, bandeira) é
calculado ou guardado aqui — tudo vem do campo "meu_estado" do servidor.
"""
import socket
import threading
import curses
import time

from shared import protocolo as proto
from client.ui   import UI
from client.rede import Receptor

HOST = "localhost"
PORT = 12345
ADDR = (HOST, PORT)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

_lock      = threading.Lock()
_rodando   = True
_ui: UI    = None
_apelido   = ""
_meu_time  = ""
_aguardando = threading.Event()

_ping_ms      = -1
_ping_enviado = 0.0
_lock_ping    = threading.Lock()


# ── Callbacks da thread de rede ───────────────────────────────────────────────
def _on_mapa_estatico(payload: dict):
    if _ui:
        _ui.atualizar_mapa_estatico(payload)

def _on_estado(payload: dict):
    if not _ui:
        return
    meu      = payload.get("meu_estado", {})
    hp       = meu.get("hp",       "?")
    balas    = meu.get("balas",    "?")
    bandeira = meu.get("bandeira", False)
    time_j   = meu.get("time",     _meu_time)
    _ui.renderizar_estado(payload)
    _ui.status_jogo(time_j, hp, balas, bandeira, _ping_ms)

def _on_msg(texto: str):
    if _ui:
        with _lock:
            _ui.adicionar_mensagem(texto)
    _aguardando.set()

def _on_erro(texto: str):
    if _ui:
        with _lock:
            _ui.adicionar_mensagem(f"[!] {texto}")

def _on_desligar():
    global _rodando
    if _ui:
        with _lock:
            _ui.adicionar_mensagem("[Servidor encerrado]")
    _rodando = False
    _aguardando.set()

def _on_escolha_time(texto: str):
    if _ui:
        with _lock:
            _ui.adicionar_mensagem(f"\n[Servidor] {texto}")
    _aguardando.set()

def _on_ping():
    global _ping_ms
    sock.sendto(proto.CMD_PONG.encode(), ADDR)
    with _lock_ping:
        if _ping_enviado > 0:
            _ping_ms = int((time.time() - _ping_enviado) * 1000)

def _on_versao_ok():
    """Servidor aceitou a versão — desbloqueia o fluxo de login."""
    if _ui:
        with _lock:
            _ui.adicionar_mensagem(f"[✓] Versão {proto.VERSAO} aceita pelo servidor.")
    _aguardando.set()

def _on_versao_invalida(versao_servidor: str, texto: str):
    """Servidor rejeitou a versão — exibe erro e encerra."""
    global _rodando
    mensagem = (
        texto or
        f"Versão incompatível. "
        f"Seu cliente: {proto.VERSAO} | Servidor: {versao_servidor}. "
        f"Atualize seu cliente."
    )
    if _ui:
        with _lock:
            _ui.adicionar_mensagem(f"[ERRO DE VERSÃO] {mensagem}")
    _rodando = False
    _aguardando.set()


# ── Main ──────────────────────────────────────────────────────────────────────
def main(stdscr):
    global _rodando, _ui, _meu_time, _apelido

    try:
        ui = UI(stdscr)
    except RuntimeError as e:
        stdscr.addstr(0, 0, str(e))
        stdscr.addstr(1, 0, "Pressione qualquer tecla para sair.")
        stdscr.refresh()
        stdscr.getch()
        return

    _ui = ui

    # ── Apelido ───────────────────────────────────────────────────────────────
    apelido = ui.ler_texto("Apelido: ")
    _apelido = apelido

    # ── Handshake com versão ──────────────────────────────────────────────────
    sock.sendto(proto.encode_handshake(apelido), ADDR)

    # ── Receptor ──────────────────────────────────────────────────────────────
    receptor = Receptor(
        sock,
        on_mapa_estatico   = _on_mapa_estatico,
        on_estado          = _on_estado,
        on_msg             = _on_msg,
        on_erro            = _on_erro,
        on_desligar        = _on_desligar,
        on_escolha_time    = _on_escolha_time,
        on_ping            = _on_ping,
        on_versao_ok       = _on_versao_ok,
        on_versao_invalida = _on_versao_invalida,
    )
    receptor.iniciar()

    # ── Aguarda resposta de versão ────────────────────────────────────────────
    ui.adicionar_mensagem(f"Verificando versão do servidor (v{proto.VERSAO})...")
    _aguardando.wait(timeout=10)
    _aguardando.clear()

    if not _rodando:
        ui.adicionar_mensagem("Pressione qualquer tecla para sair.")
        ui.ler_tecla()
        receptor.parar()
        sock.close()
        return

    # ── Escolha de time ───────────────────────────────────────────────────────
    _aguardando.wait(timeout=10)
    _aguardando.clear()
    if not _rodando:
        receptor.parar(); sock.close(); return

    while _rodando:
        escolha = ui.ler_texto("Seu time (A ou B): ").strip().upper()
        if escolha in ("A", "B"):
            sock.sendto(f"{proto.CMD_TIME} {escolha}".encode(), ADDR)
            _meu_time = escolha
            break
        ui.adicionar_mensagem("[!] Digite A ou B.")

    # ── Aguarda boas-vindas + 1º estado ──────────────────────────────────────
    _aguardando.wait(timeout=10)
    _aguardando.clear()
    if not _rodando:
        receptor.parar(); sock.close(); return

    ui.adicionar_mensagem("Pronto! Setas=mover  │  WASD=atirar  │  Enter=chat  │  /sair=sair")

    # ── Loop de input ─────────────────────────────────────────────────────────
    TECLAS_MOVER = {
        "KEY_UP": "cima", "KEY_DOWN": "baixo",
        "KEY_LEFT": "esq", "KEY_RIGHT": "dir",
    }
    TECLAS_ATIRAR = {
        "w": "cima", "W": "cima",
        "s": "baixo", "S": "baixo",
        "a": "esq",   "A": "esq",
        "d": "dir",   "D": "dir",
    }

    while _rodando:
        try:
            tecla = ui.ler_tecla()
        except KeyboardInterrupt:
            break

        if tecla in TECLAS_MOVER:
            sock.sendto(f"{proto.CMD_MOVER} {TECLAS_MOVER[tecla]}".encode(), ADDR)
            continue

        if tecla in TECLAS_ATIRAR:
            sock.sendto(f"{proto.CMD_ATIRAR} {TECLAS_ATIRAR[tecla]}".encode(), ADDR)
            continue

        # Enter ativa o modo chat — WASD e setas ficam desativados até confirmar
        if tecla in ("\n", "\r", "KEY_ENTER"):
            texto = ui.ler_chat("> ")
            if not texto:
                continue
            if texto.strip() == proto.CMD_SAIR:
                sock.sendto(proto.CMD_SAIR.encode(), ADDR)
                _rodando = False
                break
            sock.sendto(texto.encode(), ADDR)
            with _lock:
                ui.adicionar_mensagem(f"Você ({apelido}): {texto}")
            continue

    receptor.parar()
    sock.close()


curses.wrapper(main)
print("Cliente encerrado.")