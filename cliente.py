import socket
import threading
import curses

# 1. Cria socket UDP
cliente = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

HOST = 'localhost'
PORT = 12345
BUFFERSIZE = 1024
ADDR = (HOST, PORT)

rodando = True
lock = threading.Lock()

def main(stdscr = curses.initscr()):
    global rodando
    
    curses.curs_set(1)
    stdscr.clear()
    altura, largura = stdscr.getmaxyx()
    
    painel_msgs = curses.newwin(altura - 2, largura, 0, 0)
    painel_msgs.scrollok(True)
    
    separador = curses.newwin(1, largura, altura-2, 0)
    separador.addstr(0, 0, "-" * (largura - 1))
    separador.refresh()
    
    painel_input = curses.newwin(1, largura, altura - 1, 0)
    
    def adicionar_mensagem(msg):
        with lock:
            painel_msgs.addstr(f"{msg}\n")
            painel_msgs.refresh()
    
    #iniciando cliente
    painel_input.clear()
    painel_input.addstr("Apelido: ")
    painel_input.refresh()
    curses.echo()
    apelido = painel_input.getstr().decode()
    curses.noecho()
    cliente.sendto(apelido.encode(), ADDR)
    
    boas_vindas, _ = cliente.recvfrom(BUFFERSIZE)
    adicionar_mensagem(boas_vindas.decode())
    
    def receber_mensagens():
        global rodando
        while rodando:
            try:
                msg, _ = cliente.recvfrom(BUFFERSIZE)
                if msg == b"/desligar":
                    adicionar_mensagem("[Servidor encerrado]")
                    rodando = False
                    break
                adicionar_mensagem(msg.decode())
            except:
                break
            
    thread_receber = threading.Thread(target=receber_mensagens)
    thread_receber.start()
    
    while rodando:
        painel_input.clear()
        painel_input.addstr("Você: ")
        painel_input.refresh()
        
        curses.echo()
        try:
            msg = painel_input.getstr().decode()
        except:
            continue
        curses.noecho()
        
        if msg == "/sair":
            cliente.sendto(b"/sair", ADDR)
            with lock:
                rodando = False
            break
        
        cliente.sendto(msg.encode(), ADDR)
        adicionar_mensagem(f"Você ({apelido}): {msg}")
        
    cliente.close()
                
curses.wrapper(main)

print("Cliente encerrado...")
