"""
cliente.py  —  Entry point do cliente UDP.
"""
import socket
import threading
import curses

from shared import protocolo as proto
from client.ui   import UI
from client.rede import Receptor

HOST = "localhost"
PORT = 12345
ADDR = (HOST, PORT)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Estado compartilhado entre threads
_lock        = threading.Lock()
_estado_mapa = None
_rodando     = True
_ui: UI      = None


# ── Mapeamento de teclas → direção ────────────────────────────────────────────
TECLAS_MOVIMENTO = {
    # WASD (maiúsculo e minúsculo)
    "w": "cima",  "W": "cima",
    "s": "baixo", "S": "baixo",
    "a": "esq",   "A": "esq",
    "d": "dir",   "D": "dir",
    # Teclas de seta (curses)
    "KEY_UP":    "cima",
    "KEY_DOWN":  "baixo",
    "KEY_LEFT":  "esq",
    "KEY_RIGHT": "dir",
}


# ── Callbacks da thread de rede ───────────────────────────────────────────────
def _on_mapa(payload: dict):
    global _estado_mapa
    with _lock:
        _estado_mapa = payload
    if _ui:
        _ui.renderizar_mapa(payload)


def _on_msg(texto: str):
    if _ui:
        with _lock:
            _ui.adicionar_mensagem(texto)


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


# ── Main ──────────────────────────────────────────────────────────────────────
def main(stdscr=curses.initscr()):
    global _rodando, _ui

    try:
        ui = UI(stdscr)
    except RuntimeError as e:
        stdscr.addstr(0, 0, str(e))
        stdscr.addstr(1, 0, "Pressione qualquer tecla para sair.")
        stdscr.refresh()
        stdscr.getch()
        return

    _ui = ui

    # ── Login ──────────────────────────────────────────────────────────────────
    apelido = ui.ler_texto("Apelido: ")
    sock.sendto(apelido.encode(), ADDR)

    # Aguarda boas-vindas
    raw, _ = sock.recvfrom(proto.BUFFERSIZE)
    payload = proto.decode(raw)
    ui.adicionar_mensagem(payload.get("texto", ""))

    # Inicializa mapa a partir do payload de boas-vindas
    mapa_inicial = payload.get("mapa")
    if mapa_inicial:
        _on_mapa(mapa_inicial)

    # ── Receptor de rede ───────────────────────────────────────────────────────
    receptor = Receptor(sock, _on_mapa, _on_msg, _on_erro, _on_desligar)
    receptor.iniciar()

    # ── Status ────────────────────────────────────────────────────────────────
    ui.status_jogo()
    ui.adicionar_mensagem(
        "Conectado! Use WASD ou setas para mover. "
        "Digite /chat para enviar mensagem ou /sair para sair."
    )

    # ── Loop de input por tecla única ─────────────────────────────────────────
    while _rodando:
        try:
            tecla = ui.ler_tecla()
        except curses.error:
            continue
        except KeyboardInterrupt:
            break

        # Movimento
        if tecla in TECLAS_MOVIMENTO:
            direcao = TECLAS_MOVIMENTO[tecla]
            cmd = f"{proto.CMD_MOVER} {direcao}"
            sock.sendto(cmd.encode(), ADDR)
            continue

        # /sair
        if tecla in ("\n", "\r") or tecla == "q":
            # Se pressionou Enter ou 'q', abre modo texto para confirmar comando
            pass   # tratado abaixo no modo texto

        # Qualquer outra tecla abre modo de texto (chat ou comandos)
        if len(tecla) == 1 and tecla not in TECLAS_MOVIMENTO:
            # Primeiro caractere já digitado, passa para ler_texto
            if tecla == "/":
                texto = "/" + ui.ler_texto("> /")
            else:
                texto = tecla + ui.ler_texto(f"> {tecla}")

            texto = texto.strip()
            if not texto:
                continue

            if texto == proto.CMD_SAIR:
                sock.sendto(proto.CMD_SAIR.encode(), ADDR)
                _rodando = False
                break

            sock.sendto(texto.encode(), ADDR)
            with _lock:
                ui.adicionar_mensagem(f"Você ({apelido}): {texto}")

    receptor.parar()
    sock.close()


curses.wrapper(main)
print("Cliente encerrado.")