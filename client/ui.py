"""
client/ui.py
Layout curses + renderização do mapa.

O mapa estático (matriz de células) é cacheado localmente.
A cada tick só chega o estado dinâmico (jogadores + projéteis),
que é sobreposto ao cache para renderizar.
"""
import curses

CELULA = {
    0: ".",   # livre
    1: "#",   # parede
    2: "a",   # base Time A
    3: "b",   # base Time B
}

MIN_LINHAS  = 24
MIN_COLUNAS = 42

# Linhas reservadas para o mapa no topo da tela.
# Aumentado para suportar mapas maiores (scroll não disponível no painel_mapa).
# O mapa é renderizado dentro dessa área — se for maior, é cortado pelo terminal.
AREA_MAPA = 18


class UI:
    def __init__(self, stdscr):
        self.stdscr = stdscr

        # Cache do mapa estático (recebido uma vez do servidor)
        self._mapa_cache: list[list[int]] | None = None
        self._linhas_mapa  = 0
        self._colunas_mapa = 0

        curses.curs_set(0)
        stdscr.keypad(True)
        stdscr.clear()

        altura, largura = stdscr.getmaxyx()
        self._verificar_tamanho(altura, largura)
        self.altura  = altura
        self.largura = largura

        # Cores
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN,   -1)  # Time A / Base A
        curses.init_pair(2, curses.COLOR_RED,    -1)  # Time B / Base B
        curses.init_pair(3, curses.COLOR_YELLOW, -1)  # Projétil
        self.COR_A    = curses.color_pair(1)
        self.COR_B    = curses.color_pair(2)
        self.COR_PROJ = curses.color_pair(3)

        # Painéis
        self.painel_mapa = curses.newwin(AREA_MAPA, largura, 0, 0)

        sep1 = curses.newwin(1, largura, AREA_MAPA, 0)
        sep1.addstr(0, 0, "─" * (largura - 1))
        sep1.refresh()

        msgs_h = max(altura - AREA_MAPA - 3, 2)
        self.painel_msgs = curses.newwin(msgs_h, largura, AREA_MAPA + 1, 0)
        self.painel_msgs.scrollok(True)

        sep2 = curses.newwin(1, largura, altura - 2, 0)
        sep2.addstr(0, 0, "─" * (largura - 1))
        sep2.refresh()

        self.painel_status = curses.newwin(1, largura, altura - 1, 0)
        self._atualizar_status("Conectando...")

    # ── Tamanho ───────────────────────────────────────────────────────────────
    @staticmethod
    def _verificar_tamanho(altura, largura):
        if altura < MIN_LINHAS or largura < MIN_COLUNAS:
            raise RuntimeError(
                f"Terminal muito pequeno! Mínimo: {MIN_LINHAS}x{MIN_COLUNAS}, "
                f"atual: {altura}x{largura}."
            )

    # ── Cache do mapa estático ────────────────────────────────────────────────
    def atualizar_mapa_estatico(self, payload: dict):
        """Chamado uma única vez ao receber TIPO_MAPA_ESTATICO."""
        self._mapa_cache   = payload["mapa"]
        self._linhas_mapa  = payload["linhas"]
        self._colunas_mapa = payload["colunas"]

    # ── Status bar ────────────────────────────────────────────────────────────
    def _atualizar_status(self, texto: str):
        self.painel_status.erase()
        self.painel_status.addstr(0, 0, texto[: self.largura - 1])
        self.painel_status.refresh()

    def status_jogo(self, time: str = "", hp: int = 3):
        barra = "♥" * hp + "♡" * (3 - hp)
        self._atualizar_status(
            f"[Time {time}] {barra}  │  Setas=mover  WASD=atirar  /=comando"
        )

    # ── Mensagens ─────────────────────────────────────────────────────────────
    def adicionar_mensagem(self, msg: str):
        self.painel_msgs.addstr(f"{msg}\n")
        self.painel_msgs.refresh()

    # ── Renderização ──────────────────────────────────────────────────────────
    def renderizar_estado(self, estado: dict):
        """
        Sobrepõe o estado dinâmico (jogadores + projéteis) sobre o mapa cacheado.
        Chamado a cada tick/movimento.
        """
        if self._mapa_cache is None:
            return

        jogadores = estado.get("jogadores", {})
        projeteis = estado.get("projeteis", [])

        pos_jogadores = {(d["x"], d["y"]): (ap, d) for ap, d in jogadores.items()}
        pos_projeteis = {(p["x"], p["y"]) for p in projeteis}

        # Linhas e colunas visíveis (limitadas pela área do painel)
        linhas_vis  = min(self._linhas_mapa,  AREA_MAPA - 2)
        colunas_vis = min(self._colunas_mapa, self.largura - 1)

        self.painel_mapa.erase()

        for r in range(linhas_vis):
            for c in range(colunas_vis):
                # Projétil tem prioridade visual
                if (c, r) in pos_projeteis:
                    try:
                        self.painel_mapa.addch(r, c, "*", self.COR_PROJ)
                    except curses.error:
                        pass
                    continue

                if (c, r) in pos_jogadores:
                    ap, d = pos_jogadores[(c, r)]
                    char  = ap[0].upper()
                    cor   = self.COR_A if d.get("time") == "A" else self.COR_B
                    try:
                        self.painel_mapa.addch(r, c, char, cor | curses.A_BOLD)
                    except curses.error:
                        pass
                    continue

                cel  = self._mapa_cache[r][c]
                char = CELULA.get(cel, "?")
                cor  = self.COR_A if cel == 2 else (self.COR_B if cel == 3 else 0)
                try:
                    self.painel_mapa.addch(r, c, char, cor)
                except curses.error:
                    pass

        # Legenda de jogadores abaixo da matriz
        try:
            linha_leg = linhas_vis + 1
            partes = []
            for ap, d in jogadores.items():
                t  = d.get("time", "?")
                hp = d.get("hp", 0)
                partes.append(f"[{t}]{ap[0].upper()}={ap} {'♥'*hp}{'♡'*(3-hp)}")
            legenda = "  ".join(partes)
            self.painel_mapa.addstr(linha_leg, 0, legenda[: self.largura - 1])
        except curses.error:
            pass

        self.painel_mapa.refresh()

    # ── Input ─────────────────────────────────────────────────────────────────
    def ler_tecla(self) -> str:
        return self.stdscr.getkey()

    def ler_texto(self, prompt: str = "> ") -> str:
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
        return texto