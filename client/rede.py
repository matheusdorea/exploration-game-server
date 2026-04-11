"""
client/rede.py
Thread responsável por receber pacotes do servidor e atualizar o estado local.
"""
import threading
from shared import protocolo as proto


class Receptor:
    """
    Roda em background e despacha payloads recebidos para callbacks.
    """

    def __init__(self, sock, on_mapa, on_msg, on_erro, on_desligar):
        """
        Parâmetros
        ----------
        sock        : socket UDP já conectado
        on_mapa     : callable(dict)  — chamado quando chega snapshot de mapa
        on_msg      : callable(str)   — chamado quando chega mensagem de chat
        on_erro     : callable(str)   — chamado quando chega erro do servidor
        on_desligar : callable()      — chamado quando o servidor é encerrado
        """
        self._sock        = sock
        self._on_mapa     = on_mapa
        self._on_msg      = on_msg
        self._on_erro     = on_erro
        self._on_desligar = on_desligar
        self._rodando     = True
        self._thread      = threading.Thread(target=self._loop, daemon=True)

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

                if tipo in (proto.TIPO_MAPA, proto.TIPO_BV):
                    # boas-vindas também carrega snapshot em payload["mapa"]
                    mapa_payload = payload if tipo == proto.TIPO_MAPA else payload.get("mapa", {})
                    self._on_mapa(mapa_payload)

                elif tipo == proto.TIPO_MSG:
                    texto = payload.get("texto", "")
                    if texto == "/desligar":
                        self._on_desligar()
                        self._rodando = False
                    else:
                        self._on_msg(texto)

                elif tipo == proto.TIPO_ERRO:
                    self._on_erro(payload.get("texto", ""))

            except Exception:
                if self._rodando:
                    self._on_desligar()
                break