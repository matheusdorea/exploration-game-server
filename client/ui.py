"""
client/ui.py
Renderização curses. Mudanças:
  - status_jogo exibe munição e flag de portador
  - renderizar_estado desenha itens e bandeiras
  - ler_tecla ignora KEY_ENTER para não crashar
  - clipping de mapa: nunca tenta escrever fora da área visível
  - painel_chat_input dedicado: ler_chat usa linha própria entre
    painel_msgs e sep2, evitando clipping com mensagens da rede
"""
import curses

CELULA = {0: ".", 1: "#", 2: "a", 3: "b"}

SIMBOLO_ITEM = {"cura": "+", "escudo": "S"}

MIN_LINHAS  = 24
MIN_COLUNAS = 42
AREA_MAPA   = 18


class UI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
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

        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN,    -1)  # Time A / Base A
        curses.init_pair(2, curses.COLOR_RED,     -1)  # Time B / Base B
        curses.init_pair(3, curses.COLOR_YELLOW,  -1)  # Projétil
        curses.init_pair(4, curses.COLOR_GREEN,   -1)  # Item cura
        curses.init_pair(5, curses.COLOR_YELLOW,  -1)  # Item escudo
        curses.init_pair(6, curses.COLOR_WHITE,   -1)  # Bandeira neutra / chão

        self.COR_A      = curses.color_pair(1)
        self.COR_B      = curses.color_pair(2)
        self.COR_PROJ   = curses.color_pair(3)
        self.COR_CURA   = curses.color_pair(4)
        self.COR_ESCUDO = curses.color_pair(5)
        self.COR_FLAG   = curses.color_pair(6)

        self.painel_mapa = curses.newwin(AREA_MAPA, largura, 0, 0)

        sep1 = curses.newwin(1, largura, AREA_MAPA, 0)
        sep1.addstr(0, 0, "─" * (largura - 1))
        sep1.refresh()

        # -4 em vez de -3: reserva 1 linha extra para painel_chat_input
        msgs_h = max(altura - AREA_MAPA - 4, 2)
        self.painel_msgs = curses.newwin(msgs_h, largura, AREA_MAPA + 1, 0)
        self.painel_msgs.scrollok(True)

        # Linha dedicada ao input de chat — fica logo abaixo de painel_msgs
        chat_y = AREA_MAPA + 1 + msgs_h
        self.painel_chat_input = curses.newwin(1, largura, chat_y, 0)

        sep2 = curses.newwin(1, largura, chat_y + 1, 0)
        sep2.addstr(0, 0, "─" * (largura - 1))
        sep2.refresh()

        self.painel_status = curses.newwin(1, largura, altura - 1, 0)
        self._atualizar_status("Conectando...")

    @staticmethod
    def _verificar_tamanho(altura, largura):
        if altura < MIN_LINHAS or largura < MIN_COLUNAS:
            raise RuntimeError(
                f"Terminal muito pequeno! Mínimo: {MIN_LINHAS}x{MIN_COLUNAS}, "
                f"atual: {altura}x{largura}."
            )

    def atualizar_mapa_estatico(self, payload: dict):
        self._mapa_cache   = payload["mapa"]
        self._linhas_mapa  = payload["linhas"]
        self._colunas_mapa = payload["colunas"]

    def _atualizar_status(self, texto: str):
        self.painel_status.erase()
        try:
            self.painel_status.addstr(0, 0, texto[: self.largura - 1])
        except curses.error:
            pass
        self.painel_status.refresh()

    def status_jogo(self, time: str = "", hp: int = 3,
                balas: int = 5, tem_bandeira: bool = False,
                ping_ms: int = -1):
        barra   = "♥" * max(hp, 0) + "♡" * max(3 - hp, 0)
        municao = "●" * max(balas, 0) + "○" * max(5 - balas, 0)
        flag    = " 🚩" if tem_bandeira else ""
        ping    = f"  {ping_ms}ms" if ping_ms >= 0 else ""
        self._atualizar_status(
            f"[Time {time}] {barra}  {municao}{flag}"
            f"  │  Setas=mover  WASD=atirar  Enter=chat{ping}"
        )

    def adicionar_mensagem(self, msg: str):
        try:
            self.painel_msgs.addstr(f"{msg}\n")
            self.painel_msgs.refresh()
        except curses.error:
            pass

    def renderizar_estado(self, estado: dict):
        if self._mapa_cache is None:
            return

        jogadores = estado.get("jogadores", {})
        projeteis = estado.get("projeteis", [])
        itens     = estado.get("itens", [])
        bandeiras = estado.get("bandeiras", [])

        pos_jogadores = {(d["x"], d["y"]): (ap, d) for ap, d in jogadores.items()}
        pos_projeteis = {(p["x"], p["y"]) for p in projeteis}

        pos_itens = {
            (it["x"], it["y"]): (
                SIMBOLO_ITEM.get(it["tipo"], "i"),
                self.COR_CURA if it["tipo"] == "cura" else self.COR_ESCUDO,
            )
            for it in itens
        }

        # bandeiras sem portador aparecem no chão como "F"
        pos_bandeiras = {
            (b["x"], b["y"]): b["time"]
            for b in bandeiras
            if b["portador"] is None
        }

        # área visível — nunca ultrapassa o painel nem o mapa
        linhas_vis  = min(self._linhas_mapa,  AREA_MAPA - 2)
        colunas_vis = min(self._colunas_mapa, self.largura - 1)

        self.painel_mapa.erase()

        for r in range(linhas_vis):
            for c in range(colunas_vis):
                # proteção contra escrita na última coluna/linha do painel
                if r >= AREA_MAPA - 1 or c >= self.largura - 1:
                    continue

                pos = (c, r)
                if pos in pos_jogadores:
                    ap, d = pos_jogadores[pos]
                    if r >= linhas_vis or c >= colunas_vis:  # fora da área visível
                        continue
                    char = ap[0].upper()
                    cor  = self.COR_A if d.get("time") == "A" else self.COR_B
                    self._addch(r, c, char, cor | curses.A_BOLD)
                    continue

                # prioridade: projétil > jogador > item > bandeira > célula
                if pos in pos_projeteis:
                    self._addch(r, c, "*", self.COR_PROJ)
                    continue

                if pos in pos_jogadores:
                    ap, d = pos_jogadores[pos]
                    char  = ap[0].upper()
                    cor   = self.COR_A if d.get("time") == "A" else self.COR_B
                    self._addch(r, c, char, cor | curses.A_BOLD)
                    continue

                if pos in pos_itens:
                    simbolo, cor = pos_itens[pos]
                    self._addch(r, c, simbolo, cor | curses.A_BOLD)
                    continue

                if pos in pos_bandeiras:
                    t   = pos_bandeiras[pos]
                    cor = self.COR_A if t == "A" else self.COR_B
                    self._addch(r, c, "F", cor | curses.A_BOLD)
                    continue

                cel  = self._mapa_cache[r][c]
                char = CELULA.get(cel, "?")
                cor  = self.COR_A if cel == 2 else (self.COR_B if cel == 3 else 0)
                self._addch(r, c, char, cor)

        # legenda de jogadores abaixo do mapa
        try:
            linha_leg = linhas_vis + 1
            if linha_leg < AREA_MAPA - 1:
                partes = []
                for ap, d in jogadores.items():
                    t      = d.get("time", "?")
                    hp     = d.get("hp", 0)
                    escudo = " 🛡" if d.get("escudo") else ""
                    partes.append(
                        f"[{t}]{ap[0].upper()}={ap} "
                        f"{'♥'*max(hp,0)}{'♡'*max(3-hp,0)}{escudo}"
                    )
                legenda = "  ".join(partes)
                self.painel_mapa.addstr(
                    linha_leg, 0, legenda[: self.largura - 1]
                )
        except curses.error:
            pass

        self.painel_mapa.refresh()

    def _addch(self, r: int, c: int, ch: str, attr: int = 0):
        """Wrapper seguro para addch — nunca lança curses.error."""
        try:
            self.painel_mapa.addch(r, c, ch, attr)
        except curses.error:
            pass

    def ler_tecla(self) -> str:
        while True:
            try:
                k = self.stdscr.getkey()
            except curses.error:
                continue
            # Enter é retornado normalmente — o loop de cliente decide o que fazer
            return k

    def ler_chat(self, prompt: str = "> ") -> str:
        """
        Captura input de chat no painel_chat_input dedicado.
        painel_msgs continua recebendo mensagens da rede sem causar clipping,
        pois o input ocorre em uma linha separada entre msgs e sep2.
        Escape cancela e retorna string vazia.
        """
        texto = ""
        curses.curs_set(1)

        def _renderizar():
            self.painel_chat_input.erase()
            linha = f"{prompt}{texto}_"
            try:
                self.painel_chat_input.addstr(0, 0, linha[: self.largura - 1])
            except curses.error:
                pass
            self.painel_chat_input.refresh()

        _renderizar()

        while True:
            try:
                k = self.stdscr.getkey()
            except curses.error:
                continue

            if k in ("\n", "\r", "KEY_ENTER"):
                break
            elif k == "\x1b":              # Escape cancela
                texto = ""
                break
            elif k in ("KEY_BACKSPACE", "\x7f", "\b"):
                texto = texto[:-1]
            elif len(k) == 1:
                texto += k

            _renderizar()

        # Limpa a linha de input ao sair do modo chat
        self.painel_chat_input.erase()
        self.painel_chat_input.refresh()
        curses.curs_set(0)
        return texto

    def ler_texto(self, prompt: str = "> ") -> str:
        """Usado apenas no fluxo de login (apelido, escolha de time)."""
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