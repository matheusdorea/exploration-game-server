"""
servidor.py — Entry point do servidor UDP.

Suporta dois modos:
  - Interativo (padrão local): interface curses com painel de logs e comandos
  - Headless (container/CI):   logs em stdout, sem curses
                               Ativado automaticamente quando não há terminal TTY,
                               ou forçado com a variável de ambiente HEADLESS=1
"""
import os
import sys
import socket
import threading
import signal

HOST = "0.0.0.0"   # aceita conexões de qualquer interface (necessário no Docker)
PORT = int(os.environ.get("PORT", 12345))

HEADLESS = (
    os.environ.get("HEADLESS", "0") == "1"
    or not sys.stdout.isatty()
)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind((HOST, PORT))

from server import conexoes

# ── Modo headless ─────────────────────────────────────────────────────────────
def _log_stdout(msg: str):
    print(msg, flush=True)


def _rodar_headless():
    print(f"=== Exploration Game Server (headless) ===", flush=True)
    print(f"Escutando em {HOST}:{PORT}/udp", flush=True)
    print("Comandos via stdin: /online | /all <msg> | /desligar", flush=True)

    conexoes.iniciar(sock, _log_stdout)
    thread_recv = threading.Thread(target=conexoes.loop_recebimento, daemon=True)
    thread_recv.start()

    # Graceful shutdown em SIGTERM (Docker envia isso no `docker stop`)
    def _sigterm(*_):
        print("\n[SIGTERM] Encerrando servidor...", flush=True)
        conexoes.desligar()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sigterm)

    # Loop de stdin para comandos admin (opcional — funciona via `docker exec` também)
    try:
        while True:
            try:
                cmd = input()
            except EOFError:
                # stdin fechado (comum em containers sem -it); fica rodando
                signal.pause()
                break

            cmd = cmd.strip()
            if cmd == "/desligar":
                print("Encerrando...", flush=True)
                conexoes.desligar()
                break
            elif cmd == "/online":
                print(conexoes.listar_online(), flush=True)
            elif cmd.startswith("/all "):
                conexoes.broadcast_admin(cmd[5:])
            else:
                print(f"Comando desconhecido: {cmd}", flush=True)
    except KeyboardInterrupt:
        print("\n[Ctrl+C] Encerrando servidor...", flush=True)
        conexoes.desligar()


# ── Modo interativo (curses) ──────────────────────────────────────────────────
def _rodar_curses():
    import curses

    _lock_ui = threading.Lock()
    painel_logs = None

    def log(msg: str):
        with _lock_ui:
            if painel_logs:
                try:
                    painel_logs.addstr(f"{msg}\n")
                    painel_logs.refresh()
                except curses.error:
                    pass

    def main(stdscr):
        nonlocal painel_logs

        curses.curs_set(1)
        stdscr.clear()
        altura, largura = stdscr.getmaxyx()

        painel_logs = curses.newwin(altura - 2, largura, 0, 0)
        painel_logs.scrollok(True)
        painel_logs.addstr(f"=== Servidor UDP — Exploration Game ===\n")
        painel_logs.addstr(f"Escutando em {HOST}:{PORT}/udp\n")
        painel_logs.addstr("Comandos: /online | /all <msg> | /desligar\n\n")
        painel_logs.refresh()

        sep = curses.newwin(1, largura, altura - 2, 0)
        sep.addstr(0, 0, "─" * (largura - 1))
        sep.refresh()

        painel_input = curses.newwin(1, largura, altura - 1, 0)

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


# ── Entry point ───────────────────────────────────────────────────────────────
if HEADLESS:
    _rodar_headless()
else:
    _rodar_curses()

print("Servidor encerrado.")