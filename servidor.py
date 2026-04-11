"""
servidor.py  —  Entry point do servidor UDP.
"""
import socket
import threading
import curses

from server import conexoes
from shared import protocolo as proto

HOST = "localhost"
PORT = 12345

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((HOST, PORT))

painel_logs = None
_lock_ui = threading.Lock()


def log(msg: str):
    with _lock_ui:
        if painel_logs:
            try:
                painel_logs.addstr(f"{msg}\n")
                painel_logs.refresh()
            except curses.error:
                pass


def main(stdscr=curses.initscr()):
    global painel_logs

    curses.curs_set(1)
    stdscr.clear()
    altura, largura = stdscr.getmaxyx()

    painel_logs = curses.newwin(altura - 2, largura, 0, 0)
    painel_logs.scrollok(True)
    painel_logs.addstr("=== Servidor UDP — Exploration Game ===\n")
    painel_logs.addstr("Comandos: /online | /all <msg> | /desligar\n\n")
    painel_logs.refresh()

    sep = curses.newwin(1, largura, altura - 2, 0)
    sep.addstr(0, 0, "─" * (largura - 1))
    sep.refresh()

    painel_input = curses.newwin(1, largura, altura - 1, 0)

    # Inicializa módulo de conexões
    conexoes.iniciar(sock, log)

    thread_recv = threading.Thread(target=conexoes.loop_recebimento, daemon=True)
    thread_recv.start()

    rodando = True
    while rodando:
        try:
            painel_input.clear()
            painel_input.addstr("Admin: ")
            painel_input.refresh()

            curses.echo()
            try:
                cmd = painel_input.getstr().decode().strip()
            except Exception:
                continue
            curses.noecho()

            if cmd == "/desligar":
                log("Encerrando servidor...")
                conexoes.desligar()
                rodando = False

            elif cmd == "/online":
                log(conexoes.listar_online())

            elif cmd.startswith("/all "):
                conexoes.broadcast_admin(cmd[5:])

            else:
                log(f"Comando desconhecido: {cmd}")

            with _lock_ui:
                try:
                    painel_logs.addstr(f"Admin: {cmd}\n")
                    painel_logs.refresh()
                except curses.error:
                    pass

        except (ConnectionAbortedError, KeyboardInterrupt):
            pass


curses.wrapper(main)
print("Servidor encerrado.")