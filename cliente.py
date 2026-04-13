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

_lock      = threading.Lock()
_rodando   = True
_ui: UI    = None
_apelido   = ""
_meu_time  = ""   # recebido do servidor na boas-vindas, usado só para UI
_aguardando = threading.Event()

# Ping medido localmente (legítimo — é uma medição de rede, não estado de jogo)
_ping_ms       = -1
_ping_enviado  = 0.0
_lock_ping     = threading.Lock()


# ── Callbacks da thread de rede ───────────────────────────────────────────────
def _on_mapa_estatico(payload: dict):
    if _ui:
        _ui.atualizar_mapa_estatico(payload)

def _on_estado(payload: dict):
    """
    Renderiza o mapa e atualiza a status bar com os valores do servidor.
    meu_estado = { hp, balas, escudo, bandeira, time } — autoritativo.
    """
    if not _ui:
        return

    meu = payload.get("meu_estado", {})
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
    """Servidor enviou ping — responde com pong e mede RTT."""
    global _ping_ms
    sock.sendto(proto.CMD_PONG.encode(), ADDR)
    with _lock_ping:
        if _ping_enviado > 0:
            _ping_ms = int((time.time() - _ping_enviado) * 1000)
            # Próximo ping: marca o envio agora para medir o próximo ciclo
            # (simples: usamos o timestamp do recebimento como referência)


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
        on_ping          = _on_ping,
    )
    receptor.iniciar()

    # ── Escolha de time ───────────────────────────────────────────────────────
    _aguardando.wait(timeout=10)
    _aguardando.clear()
    if not _rodando:
        receptor.parar(); sock.close(); return

    while _rodando:
        escolha = ui.ler_texto("Seu time (A ou B): ").strip().upper()
        if escolha in ("A", "B"):
            sock.sendto(f"{proto.CMD_TIME} {escolha}".encode(), ADDR)
            _meu_time = escolha   # usado apenas como fallback de UI até o 1º estado
            break
        ui.adicionar_mensagem("[!] Digite A ou B.")

    # ── Aguarda boas-vindas + 1º estado ──────────────────────────────────────
    _aguardando.wait(timeout=10)
    _aguardando.clear()
    if not _rodando:
        receptor.parar(); sock.close(); return

    ui.adicionar_mensagem("Pronto! Setas=mover  │  WASD=atirar  │  /sair=sair")

    # ── Loop de input ─────────────────────────────────────────────────────────
    while _rodando:
        try:
            tecla = ui.ler_tecla()
        except KeyboardInterrupt:
            break

        # Movimento — sem throttle local, servidor decide
        if tecla in {
            "KEY_UP": "cima", "KEY_DOWN": "baixo",
            "KEY_LEFT": "esq", "KEY_RIGHT": "dir",
        }:
            direcao = {
                "KEY_UP": "cima", "KEY_DOWN": "baixo",
                "KEY_LEFT": "esq", "KEY_RIGHT": "dir",
            }[tecla]
            sock.sendto(f"{proto.CMD_MOVER} {direcao}".encode(), ADDR)
            continue

        # Tiro
        if tecla in {
            "w": "cima", "W": "cima",
            "s": "baixo", "S": "baixo",
            "a": "esq",   "A": "esq",
            "d": "dir",   "D": "dir",
        }:
            direcao = {
                "w": "cima", "W": "cima",
                "s": "baixo", "S": "baixo",
                "a": "esq",   "A": "esq",
                "d": "dir",   "D": "dir",
            }[tecla]
            sock.sendto(f"{proto.CMD_ATIRAR} {direcao}".encode(), ADDR)
            continue

        # Comando de texto (/, chat)
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