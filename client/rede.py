"""
client/rede.py
Thread de recebimento. Responde pings automaticamente.
"""
import threading
import time
from shared import protocolo as proto


class Receptor:
    def __init__(self, sock, on_mapa_estatico, on_estado, on_msg,
             on_erro, on_desligar, on_escolha_time, on_atingido,
             on_municao=None, on_ping=None):
        self._sock             = sock
        self._on_mapa_estatico = on_mapa_estatico
        self._on_estado        = on_estado
        self._on_msg           = on_msg
        self._on_erro          = on_erro
        self._on_desligar      = on_desligar
        self._on_escolha_time  = on_escolha_time
        self._on_atingido      = on_atingido
        self._on_municao       = on_municao
        self._rodando          = True
        self._thread           = threading.Thread(target=self._loop, daemon=True)
        self._ping_enviado: float = 0.0
        self._on_ping = on_ping

    def iniciar(self):
        self._thread.start()

    def parar(self):
        self._rodando = False

    def _loop(self):
        while self._rodando:
            try:
                raw, addr = self._sock.recvfrom(proto.BUFFERSIZE)
                payload   = proto.decode(raw)
                tipo      = payload.get("tipo", "")

                if tipo == proto.TIPO_PING:
                    agora = time.time()
                    if self._ping_enviado > 0:
                        ms = int((agora - self._ping_enviado) * 1000)
                        if self._on_ping:
                            self._on_ping(ms)
                    self._ping_enviado = agora
                    try:
                        self._sock.sendto(proto.CMD_PONG.encode(), addr)
                    except OSError:
                        pass
                    continue

                if tipo == proto.TIPO_MAPA_ESTATICO:
                    self._on_mapa_estatico(payload)

                elif tipo == proto.TIPO_ESTADO:
                    self._on_estado(payload)

                elif tipo == proto.TIPO_BV:
                    self._on_msg(payload.get("texto", ""))

                elif tipo == proto.TIPO_MSG:
                    texto = payload.get("texto", "")
                    if texto == "/desligar":
                        self._on_desligar()
                        self._rodando = False
                    else:
                        self._on_msg(texto)

                elif tipo == proto.TIPO_ERRO:
                    self._on_erro(payload.get("texto", ""))

                elif tipo == proto.TIPO_ESCOLHA:
                    self._on_escolha_time(payload.get("texto", ""))

                elif tipo == proto.TIPO_ATINGIDO:
                    self._on_atingido(
                        payload.get("hp", 0),
                        payload.get("atirador", "?"),
                    )

                elif tipo == proto.TIPO_MUNICAO:
                    if self._on_municao:
                        self._on_municao(payload.get("qtd", 0))

            except Exception:
                if self._rodando:
                    self._on_desligar()
                break