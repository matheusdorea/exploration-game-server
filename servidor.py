import socket
import threading
import curses


servidor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

HOST = 'localhost'
PORT = 12345
BUFFERSIZE = 1024

servidor.bind((HOST, PORT))

lock = threading.Lock()
clientes = {}
rodando = True

painel_logs = None

def log(msg):
    with lock:
        if painel_logs:
            painel_logs.addstr(f"{msg}\n")
            painel_logs.refresh()

def broadcast(msg, remetente = None):
    with lock:
        for addr in clientes:
            if addr != remetente:
                servidor.sendto(msg.encode(), addr)

def aceitar_conexoes():
    while rodando:
        try:
            data, addr = servidor.recvfrom(BUFFERSIZE)
            msg = data.decode()
            
            if addr not in clientes:
                # Primeiro pacote = apelido
                clientes[addr] = msg
                log(f"[+] {msg} conectou ({addr})")
                servidor.sendto(f"Bem-vindo, {msg}!".encode(), addr)
                broadcast(f"[Servidor] {msg} entrou no chat.", addr)
            else:
                apelido = clientes[addr]
                if msg == "/sair":
                    broadcast(f"[Servidor] {apelido} saiu.", addr)
                    log(f"[-] {apelido} desconectou ({addr})")
                    with lock:
                        del clientes[addr]
                else:
                    log(f"{apelido}: {msg}")
                    broadcast(f"{apelido}: {msg}", addr)
        except OSError:
            break
            
def main(stdscr = curses.initscr()):
    global rodando, painel_logs
    
    curses.curs_set(1)
    stdscr.clear()
    
    altura, largura = stdscr.getmaxyx()
    
    painel_logs = curses.newwin(altura - 2, largura, 0, 0)
    painel_logs.scrollok(True)
    painel_logs.addstr("=== Servidor UDP iniciado ===\n")
    painel_logs.addstr("Comandos: /online | /all <msg> | /desligar\n\n")
    painel_logs.refresh()

    # Separador
    separador = curses.newwin(1, largura, altura - 2, 0)
    separador.addstr(0, 0, "─" * (largura - 1))
    separador.refresh()
    
    painel_input = curses.newwin(1, largura, altura - 1, 0)
    
    thread_connect = threading.Thread(target=aceitar_conexoes)
    thread_connect.start()
            
    while rodando:
        try:
            painel_input.clear()
            painel_input.addstr("Admin: ")
            painel_input.refresh()
            
            curses.echo()
            try:
                comando = painel_input.getstr().decode()
            except:
                continue
            curses.noecho()
            
            if comando == "/desligar":
                rodando = False
                log("Fechando conexões e saindo...")
                for addr in list(clientes):
                    servidor.sendto(b"/desligar", addr)
                servidor.close()
                break
                
            elif comando == "/online":
                with lock: 
                    lista = "\n".join(clientes.values())
                log(lista)
                    
            elif comando.startswith("/all "):
                msg = comando[5:]
                broadcast(f"[Servidor]: {msg}")

            painel_logs.addstr(f"Admin: {comando}\n")
            painel_logs.refresh()
        except(ConnectionAbortedError):
            pass

curses.wrapper(main)

print("Servidor Encerrado")