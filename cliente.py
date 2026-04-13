"""
cliente.py — Entry point do cliente UDP.
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

_lock         = threading.Lock()
_rodando      = True
_ui: UI       = None
_meu_time     = ""
_meu_hp       = 3
_meu_balas    = 5
_meu_bandeira = False
_meu_apelido  = ""
_meu_ping = -1

_aguardando = threading.Event()

TECLAS_MOVER = {
    "KEY_UP":    "cima",
    "KEY_DOWN":  "baixo",
    "KEY_LEFT":  "esq",
    "KEY_RIGHT": "dir",
}
TECLAS_ATIRAR = {
    "w": "cima",  "W": "cima",
    "s": "baixo", "S": "baixo",
    "a": "esq",   "A": "esq",
    "d": "dir",   "D": "dir",
}


# ── Callbacks ─────────────────────────────────────────────────────────────────
def _on_mapa_estatico(payload: dict):
    if _ui:
        _ui.atualizar_mapa_estatico(payload)

def _on_ping(ms: int):
    global _meu_ping
    _meu_ping = ms
    if _ui:
        _ui.status_jogo(_meu_time, _meu_hp, _meu_balas, _meu_bandeira, _meu_ping)


def _on_estado(payload: dict):
    global _meu_bandeira
    if _ui:
        # verifica se somos portadores de alguma bandeira
        bandeiras = payload.get("bandeiras", [])
        portando  = any(b["portador"] == _meu_apelido for b in bandeiras)
        if portando != _meu_bandeira:
            _meu_bandeira = portando
            _ui.status_jogo(_meu_time, _meu_hp, _meu_balas, _meu_bandeira, _meu_ping)
        _ui.renderizar_estado(payload)


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


def _on_atingido(hp: int, atirador: str):
    global _meu_hp
    _meu_hp = hp
    msg = (
        f"☠ Eliminado por {atirador}! Voltando à base..."
        if hp == 0 else
        f"💥 Atingido por {atirador}! HP={hp}"
    )
    if _ui:
        with _lock:
            _ui.adicionar_mensagem(msg)
            _ui.status_jogo(_meu_time, max(hp, 0), _meu_balas, _meu_bandeira, _meu_ping)


def _on_municao(qtd: int):
    global _meu_balas
    _meu_balas = qtd
    if _ui:
        _ui.status_jogo(_meu_time, _meu_hp, _meu_balas, _meu_bandeira, _meu_ping)


# ── Main ──────────────────────────────────────────────────────────────────────
def main(stdscr):
    global _rodando, _ui, _meu_time, _meu_hp, _meu_apelido
    global _meu_balas, _meu_bandeira

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
    _meu_apelido = apelido
    sock.sendto(apelido.encode(), ADDR)

    # ── Receptor ──────────────────────────────────────────────────────────────
    receptor = Receptor(
        sock,
        on_mapa_estatico = _on_mapa_estatico,
        on_estado        = _on_estado,
        on_msg           = _on_msg,
        on_erro          = _on_erro,
        on_desligar      = _on_desligar,
        on_escolha_time  = _on_escolha_time,
        on_atingido      = _on_atingido,
        on_municao       = _on_municao,
        on_ping          = _on_ping,
    )
    receptor.iniciar()

    # ── Aguarda pedido de time ────────────────────────────────────────────────
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

    # ── Aguarda boas-vindas ───────────────────────────────────────────────────
    _aguardando.wait(timeout=10)
    _aguardando.clear()
    if not _rodando:
        receptor.parar(); sock.close(); return

    _meu_hp    = 3
    _meu_balas = 5
    ui.status_jogo(_meu_time, _meu_hp, _meu_balas, _meu_bandeira, _meu_ping)
    ui.adicionar_mensagem("Pronto! Setas=mover  │  WASD=atirar  │  /sair=sair")

    _ultimo_movimento = 0.0

    # ── Loop de input ─────────────────────────────────────────────────────────
    while _rodando:
        try:
            tecla = ui.ler_tecla()
        except KeyboardInterrupt:
            break

        if tecla in TECLAS_MOVER:
            agora = time.time()
            if agora - _ultimo_movimento >= 0.1:  
                _ultimo_movimento = agora
                sock.sendto(f"{proto.CMD_MOVER} {TECLAS_MOVER[tecla]}".encode(), ADDR)
            continue

        if tecla in TECLAS_ATIRAR:
            sock.sendto(f"{proto.CMD_ATIRAR} {TECLAS_ATIRAR[tecla]}".encode(), ADDR)
            continue

        if tecla == "/":
            texto = "/" + ui.ler_texto("> /")
            texto = texto.strip()
            if texto == proto.CMD_SAIR:
                sock.sendto(proto.CMD_SAIR.encode(), ADDR)
                _rodando = False
                break
            sock.sendto(texto.encode(), ADDR)
            continue

        if len(tecla) == 1:
            texto = tecla + ui.ler_texto(f"> {tecla}")
            texto = texto.strip()
            if not texto:
                continue
            sock.sendto(texto.encode(), ADDR)
            with _lock:
                ui.adicionar_mensagem(f"Você ({apelido}): {texto}")

    receptor.parar()
    sock.close()


curses.wrapper(main)
print("Cliente encerrado.")