"""
client/ui.py
Layout curses, renderização do mapa e leitura de input por tecla.
"""
import curses

# ── Símbolos do mapa ──────────────────────────────────────────────────────────
CELULA = {0: ".", 1: "#"}

# Mínimo de linhas/colunas para criar os painéis sem erro
MIN_LINHAS  = 24
MIN_COLUNAS = 40

# Linhas reservadas para o mapa (deve ser >= MAPA_LINHAS + legenda)
AREA_MAPA = 16


class UI:
    """
    Encapsula todos os painéis curses e expõe métodos simples
    para o resto do cliente.
    """

    def __init__(self, stdscr):
        self.stdscr = stdscr
        self._lock  = None   # será injetado pelo cliente

        curses.curs_set(0)
        stdscr.keypad(True)   # habilita teclas especiais (setas etc.)
        stdscr.clear()

        altura, largura = stdscr.getmaxyx()
        self._verificar_tamanho(altura, largura)

        self.altura  = altura
        self.largura = largura

        # Painel do mapa (topo)
        self.painel_mapa = curses.newwin(AREA_MAPA, largura, 0, 0)

        # Separador 1
        sep1 = curses.newwin(1, largura, AREA_MAPA, 0)
        sep1.addstr(0, 0, "─" * (largura - 1))
        sep1.refresh()

        # Painel de mensagens
        msgs_h = max(altura - AREA_MAPA - 3, 2)
        self.painel_msgs = curses.newwin(msgs_h, largura, AREA_MAPA + 1, 0)
        self.painel_msgs.scrollok(True)

        # Separador 2
        sep2 = curses.newwin(1, largura, altura - 2, 0)
        sep2.addstr(0, 0, "─" * (largura - 1))
        sep2.refresh()

        # Linha de status (rodapé)
        self.painel_status = curses.newwin(1, largura, altura - 1, 0)
        self._atualizar_status("Conectando...")

    # ── Verificação de tamanho ────────────────────────────────────────────────
    @staticmethod
    def _verificar_tamanho(altura, largura):
        if altura < MIN_LINHAS or largura < MIN_COLUNAS:
            raise RuntimeError(
                f"Terminal muito pequeno! "
                f"Mínimo: {MIN_LINHAS}x{MIN_COLUNAS}, "
                f"atual: {altura}x{largura}."
            )

    # ── Status bar ────────────────────────────────────────────────────────────
    def _atualizar_status(self, texto: str):
        self.painel_status.erase()
        self.painel_status.addstr(0, 0, texto[: self.largura - 1])
        self.painel_status.refresh()

    def status_jogo(self):
        self._atualizar_status(
            "WASD = mover  |  /sair = desconectar  |  qualquer texto = chat"
        )

    # ── Mensagens ─────────────────────────────────────────────────────────────
    def adicionar_mensagem(self, msg: str):
        self.painel_msgs.addstr(f"{msg}\n")
        self.painel_msgs.refresh()

    # ── Mapa ──────────────────────────────────────────────────────────────────
    def renderizar_mapa(self, estado: dict):
        """Desenha a matriz + indicador de cada jogador."""
        if estado is None:
            return

        linhas    = estado["linhas"]
        colunas   = estado["colunas"]
        mapa      = estado["mapa"]
        jogadores = estado["jogadores"]   # { apelido: {x, y} }

        pos_jogadores = {(d["x"], d["y"]): ap for ap, d in jogadores.items()}

        self.painel_mapa.erase()

        for r in range(linhas):
            for c in range(colunas):
                if (c, r) in pos_jogadores:
                    char = pos_jogadores[(c, r)][0].upper()
                else:
                    char = CELULA[mapa[r][c]]
                try:
                    self.painel_mapa.addch(r, c, char)
                except curses.error:
                    pass

        # Legenda abaixo da matriz
        try:
            linha_leg = linhas + 1
            self.painel_mapa.addstr(linha_leg, 0, "Jogadores:")
            for i, (ap, d) in enumerate(jogadores.items()):
                self.painel_mapa.addstr(
                    linha_leg + 1 + i, 0,
                    f"  {ap[0].upper()} = {ap}  pos:({d['x']},{d['y']})"
                )
        except curses.error:
            pass

        self.painel_mapa.refresh()

    # ── Leitura de tecla (sem Enter) ──────────────────────────────────────────
    def ler_tecla(self) -> str:
        """
        Retorna uma string representando a tecla pressionada.
        Teclas de seta retornam 'KEY_UP', 'KEY_DOWN', etc.
        Letras normais retornam o caractere.
        Backspace/Enter são tratados internamente para o modo de texto.
        """
        return self.stdscr.getkey()

    # ── Modo de entrada de texto (para chat) ──────────────────────────────────
    def ler_texto(self, prompt: str = "> ") -> str:
        """
        Lê uma linha de texto caractere a caractere e exibe no status bar.
        """
        texto = ""
        curses.curs_set(1)
        while True:
            self._atualizar_status(f"{prompt}{texto}_")
            try:
                k = self.stdscr.getkey()
            except curses.error:
                continue

            if k in ("\n", "\r", "KEY_ENTER"):
                break
            elif k in ("KEY_BACKSPACE", "\x7f", "\b"):
                texto = texto[:-1]
            elif len(k) == 1:
                texto += k
        curses.curs_set(0)
        self.status_jogo()
        return texto