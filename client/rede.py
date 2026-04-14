"""
client/rede.py
Thread de recebimento. Despacha payloads para callbacks sem guardar estado.
"""
import threading
from shared import protocolo as proto


class Receptor:
    def __init__(self, sock, on_mapa_estatico, on_estado, on_msg,
                 on_erro, on_desligar, on_escolha_time, on_ping,
                 on_versao_ok, on_versao_invalida, on_pong_servidor=None):
        self._sock                = sock
        self._on_mapa_estatico    = on_mapa_estatico
        self._on_estado           = on_estado
        self._on_msg              = on_msg
        self._on_erro             = on_erro
        self._on_desligar         = on_desligar
        self._on_escolha_time     = on_escolha_time
        self._on_ping             = on_ping
        self._on_versao_ok        = on_versao_ok
        self._on_versao_invalida  = on_versao_invalida
        self._on_pong_servidor    = on_pong_servidor   # callback RTT real
        self._rodando             = True
        self._thread              = threading.Thread(target=self._loop, daemon=True)

    def iniciar(self):
        self._thread.start()

    def parar(self):
        self._rodando = False

    def _loop(self):
        while self._rodando:
            try:
                raw, _ = self._sock.recvfrom(proto.BUFFERSIZE)
                payload = proto.decode(raw)
                tipo    = payload.get("tipo", "")

                if tipo == proto.TIPO_VERSAO_OK:
                    self._on_versao_ok()

                elif tipo == proto.TIPO_VERSAO_INVALIDA:
                    self._on_versao_invalida(
                        payload.get("versao", "?"),
                        payload.get("texto",  ""),
                    )
                    self._rodando = False

                elif tipo == proto.TIPO_MAPA_ESTATICO:
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

                elif tipo == proto.TIPO_PING:
                    self._on_ping()

                elif tipo == proto.TIPO_PONG_SERVIDOR:
                    if self._on_pong_servidor:
                        self._on_pong_servidor(payload.get("ts", 0.0))

            except Exception:
                if self._rodando:
                    self._on_desligar()
                break