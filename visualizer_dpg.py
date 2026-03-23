import math, time, os
try:
    import dearpygui.dearpygui as dpg
    HAS_DPG = DPG_AVAILABLE = True
except ImportError:
    HAS_DPG = DPG_AVAILABLE = False

WIN_W, WIN_H = 1200, 780
STAT_W = 320
COL_W = 42
ROW_H = 46
TOP = 80
LABEL_W = 160

_context_created = False

def cx(ci): return LABEL_W + ci * COL_W + COL_W // 2
def ry(rid, rows):
    for i, (r, _) in enumerate(rows):
        if r == rid: return TOP + i * ROW_H
    return TOP

BG = (15, 17, 24)
PANEL_BG = (22, 24, 34)
TEXT = (210, 215, 230)
DIM = (110, 115, 130)
LINE_DIM = (45, 48, 60)
BLUE = (94, 161, 255)
ORANGE = (255, 158, 100)
GREEN = (166, 227, 161)
RED = (243, 139, 168)
COL_ALT = (18, 20, 28)
COL_SIFT = (35, 50, 45)

class State:
    def __init__(self, eve=False):
        self.qubits = []; self.alice_bits = []; self.alice_bases = []
        self.bob_bases = []; self.bob_bits = []; self.eve_bases = []
        self.eve_bits = []; self.eve_set = set()
        self.match = []; self.sifted = []; self.qber = None
        self.eve_detected = False; self.eve = eve
        self.key = ""; self.n = 0; self.page = 0; self.phase = "tx"
        
        self.alice_text = ""; self.bob_text = ""; self.eve_text = ""; self.cipher_hex = ""
        self.otp_info = {}; self.otp_progress = 0.0
        self.waiting_for_enter = False

    def rows(self):
        r = [("ap","Фотон Алисы"),("ab","Бит Алисы"),("abs","Базис Алисы"),("ch","--- Квантовый Канал ---")]
        if self.eve: r += [("ebs","Базис Евы"),("ebt","Бит Евы"), ("ch2","--- Квантовый Канал ---")]
        r += [("bbs","Базис Боба"),("brb","Измерение Боба"),("sp","--- Открытый Канал ---"),
              ("mt","Совпадение?"),("sk","Просеянный Ключ")]
        return r

    @property
    def max_page(self): return max(0, (self.n - 1) // 20) if self.n else 0

def load_cyrillic_font():
    font_paths = [
        "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/calibri.ttf", 
        "C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf"
    ]
    try:
        with dpg.font_registry():
            for path in font_paths:
                if os.path.exists(path):
                    try:
                        with dpg.font(path, 15) as font:
                            dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                            dpg.add_font_range_hint(dpg.mvFontRangeHint_Cyrillic)
                        dpg.bind_font(font)
                        return
                    except Exception:
                        continue
    except Exception as e:
        print(f"Внимание: ошибка загрузки шрифта DPG ({e})")

def c_text(dl, x, y, text, color=TEXT, size=15):
    s = str(text); w = len(s) * (size * 0.45)
    dpg.draw_text((x - w/2, y - size*0.45), s, color=color, size=size, parent=dl)

def arrow(dl, x, y, ang, col, sz=11):
    r = math.radians(ang); c, s = math.cos(r), math.sin(r)
    p1, p2 = (x - c*sz, y + s*sz), (x + c*sz, y - s*sz)
    dpg.draw_line(p1, p2, color=col, thickness=2, parent=dl)
    h = sz * 0.4
    for a in (ang + 145, ang - 145):
        ra = math.radians(a)
        dpg.draw_line(p2, (p2[0] + math.cos(ra)*h, p2[1] - math.sin(ra)*h), color=col, thickness=2, parent=dl)
    for a in (ang + 35, ang - 35):
        ra = math.radians(a)
        dpg.draw_line(p1, (p1[0] + math.cos(ra)*h, p1[1] - math.sin(ra)*h), color=col, thickness=2, parent=dl)

def basis(dl, x, y, b, col=None):
    c = col or (BLUE if b == 0 else ORANGE)
    dpg.draw_circle((x, y), 10, color=c, thickness=1.5, parent=dl)
    if b == 0:
        dpg.draw_line((x-6, y), (x+6, y), color=c, thickness=1.5, parent=dl)
        dpg.draw_line((x, y-6), (x, y+6), color=c, thickness=1.5, parent=dl)
    else:
        dpg.draw_line((x-4, y-4), (x+4, y+4), color=c, thickness=1.5, parent=dl)
        dpg.draw_line((x+4, y-4), (x-4, y+4), color=c, thickness=1.5, parent=dl)

def pol(dl, x, y, p):
    ang = {0:0, 90:90, 45:45, 135:135}.get(p, 0)
    arrow(dl, x, y, ang, BLUE if p in (0, 90) else ORANGE)

def tick(dl, x, y, ok):
    c = GREEN if ok else RED
    if ok:
        dpg.draw_line((x-6, y), (x-2, y+6), color=c, thickness=2.5, parent=dl)
        dpg.draw_line((x-2, y+6), (x+7, y-5), color=c, thickness=2.5, parent=dl)
    else:
        dpg.draw_line((x-5, y-5), (x+5, y+5), color=c, thickness=2, parent=dl)
        dpg.draw_line((x+5, y-5), (x-5, y+5), color=c, thickness=2, parent=dl)

def stat_card(dl, y, lbl, val, val_col=TEXT):
    dpg.draw_rectangle((10, y), (STAT_W-10, y+48), fill=BG, color=LINE_DIM, thickness=1, rounding=6, parent=dl)
    dpg.draw_text((20, y+6), lbl, color=DIM, size=13, parent=dl)
    dpg.draw_text((20, y+24), val, color=val_col, size=15, parent=dl)
    return y + 54

class R:
    def __init__(self):
        self._s = None
        self.WM, self.WS = "win_main", "win_stats"
        self.DG, self.DS = "dl_grid", "dl_stats"

    def setup(self, s):
        tw = WIN_W - STAT_W
        with dpg.theme() as global_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)
                dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize, 0)
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, BG)
        dpg.bind_theme(global_theme)
        
        load_cyrillic_font()

        with dpg.window(tag=self.WM, width=tw, height=WIN_H, pos=(0,0), no_move=True, no_resize=True, no_title_bar=True):
            dpg.add_drawlist(tag=self.DG, width=tw, height=WIN_H)
        with dpg.window(tag=self.WS, width=STAT_W, height=WIN_H, pos=(tw,0), no_move=True, no_resize=True, no_title_bar=True):
            dpg.add_drawlist(tag=self.DS, width=STAT_W, height=WIN_H)

        with dpg.handler_registry():
            dpg.add_key_press_handler(dpg.mvKey_Right, callback=lambda: self._page(1))
            dpg.add_key_press_handler(dpg.mvKey_Left,  callback=lambda: self._page(-1))
            dpg.add_key_press_handler(dpg.mvKey_Escape, callback=lambda: dpg.stop_dearpygui())
            dpg.add_key_press_handler(dpg.mvKey_Return, callback=lambda: self._confirm_enter())

    def _confirm_enter(self):
        if self._s and self._s.waiting_for_enter:
            self._s.waiting_for_enter = False

    def _page(self, d):
        if self._s and self._s.phase not in ("otp", "otp_done"):
            self._s.page = max(0, min(self._s.page + d, self._s.max_page))
            self.rebuild(self._s)

    def rebuild(self, s):
        self._s = s
        dpg.delete_item(self.DG, children_only=True)
        dpg.delete_item(self.DS, children_only=True)
        if s.phase == "otp" or s.phase == "otp_done":
            self._otp_screen(s)
        else:
            self._grid(s)
        self._stats(s)

    def _draw_bit_row(self, dl, x, y, bits, label, color_theme, alpha=255):
        if alpha <= 0: return
        dpg.draw_text((x - 120, y + 2), label, color=(DIM[0], DIM[1], DIM[2], alpha), size=13, parent=dl)
        for i, b in enumerate(bits):
            bx = x + i * 20
            bg = color_theme if b else COL_ALT
            bg_a = (bg[0], bg[1], bg[2], alpha)
            dpg.draw_rectangle((bx, y), (bx+18, y+18), fill=bg_a, color=(LINE_DIM[0], LINE_DIM[1], LINE_DIM[2], alpha), parent=dl, rounding=2)
            c_text(dl, bx+9, y+9, str(b), color=(255,255,255,alpha), size=12)

    def _otp_screen(self, s):
        dl = self.DG; tw = WIN_W - STAT_W; info = s.otp_info

        dpg.draw_rectangle((0, 0), (tw, WIN_H), fill=BG, color=BG, parent=dl)
        dpg.draw_rectangle((0, 0), (tw, 50), fill=PANEL_BG, color=PANEL_BG, parent=dl)
        dpg.draw_text((20, 16), "Шифрование Одноразовым Блокнотом (OTP)", color=TEXT, size=18, parent=dl)
        dpg.draw_rectangle((tw - 170, 13), (tw - 10, 37), fill=GREEN, rounding=4, parent=dl)
        c_text(dl, tw - 90, 25, "ОТП ШИФРОВАНИЕ", color=BG, size=14)

        n_show = min(16, len(info.get("msg_bits", [])))
        if n_show == 0:
            return

        mb = info["msg_bits"][:n_show]
        pb = info["pad"][:n_show]
        cb = info["cipher_bits"][:n_show]

        TITLE_H   = 20
        NOTE_H    = 18
        ROW_H_OTP = 24
        SEC_GAP   = 14
        DIV_GAP   = 10

        def draw_section(y, title, title_col, note, rows):
            dpg.draw_text((20, y), title, color=title_col, size=16, parent=dl)
            y += TITLE_H + 2
            if note:
                dpg.draw_text((20, y), note, color=TEXT, size=13, parent=dl)
                y += NOTE_H
            for bits, lbl, col in rows:
                self._draw_bit_row(dl, 180, y, bits, lbl, col)
                y += ROW_H_OTP
            return y + SEC_GAP

        def divider(y, col=LINE_DIM):
            dpg.draw_line((20, y), (tw - 20, y), color=col, thickness=1, parent=dl)
            return y + DIV_GAP

        y = 66

        y = draw_section(y, "Алиса (Отправитель)", BLUE,
            f"Сообщение: '{info.get('alice_text', '')}'",
            [(mb, "Биты (UTF-8)", BLUE), (pb, "Ключ BB84", GREEN), (cb, "Шифртекст", ORANGE)])

        y = divider(y)

        bob_dec = info.get("bob_dec_bits", [])[:n_show]
        ok = info.get("bob_text", "") == info.get("alice_text", "")
        y = draw_section(y, "Боб (Получатель)", GREEN,
            f"Результат: '{info.get('bob_text', '')}'  {'' if ok else 'ОШИБКА'}",
            [(cb, "Шифртекст", ORANGE), (pb, "Ключ BB84", GREEN), (bob_dec, "Расшифровка", BLUE)])

        if s.eve:
            y = divider(y, col=(RED[0], RED[1], RED[2], 90))
            eve_pad = info.get("eve_fake_pad", [])[:n_show]
            eve_dec = info.get("eve_dec_bits", [])[:n_show]
            draw_section(y, "Ева (Перехватчик)", RED,
                f"Результат: '{info.get('eve_text', '')}'",
                [(cb, "Шифртекст", ORANGE), (eve_pad, "Фейк. Ключ", RED), (eve_dec, "Расшифровка", DIM)])

    def _grid(self, s):
        dl = self.DG; rows = s.rows(); nr = len(rows); bot = TOP + nr * ROW_H
        start = s.page * 20; end = min(start + 20, s.n); sift = set(s.match); tw = WIN_W - STAT_W

        dpg.draw_rectangle((0,0), (tw, WIN_H), fill=BG, color=BG, parent=dl)
        dpg.draw_rectangle((0,0), (tw, 50), fill=PANEL_BG, color=PANEL_BG, parent=dl)
        dpg.draw_text((20, 16), "Визуализатор протокола BB84", color=TEXT, size=18, parent=dl)
        
        phase_map = {"tx": "ПЕРЕДАЧА", "sift": "СВЕРКА", "qber": "АНАЛИЗ", "done": "ГОТОВО"}
        phase_colors = {"tx": BLUE, "sift": ORANGE, "qber": RED, "done": GREEN}
        dpg.draw_rectangle((tw - 110, 13), (tw - 10, 37), fill=phase_colors.get(s.phase, DIM), rounding=4, parent=dl)
        c_text(dl, tw - 60, 25, phase_map.get(s.phase, ""), color=BG, size=14)

        for ci, gi in enumerate(range(start, end)):
            x = cx(ci)
            if ci % 2 == 0: dpg.draw_rectangle((x - COL_W//2, TOP - 20), (x + COL_W//2, bot + 10), fill=COL_ALT, color=(0,0,0,0), parent=dl)
            if s.phase != "tx" and gi in sift: dpg.draw_rectangle((x - COL_W//2 + 2, TOP - 20), (x + COL_W//2 - 2, bot + 10), fill=COL_SIFT, color=(0,0,0,0), rounding=4, parent=dl)

        for rid, txt in rows:
            cy = ry(rid, rows)
            if "---" in txt:
                dpg.draw_text((15, cy - 7), txt.replace("---", "").strip(), color=DIM, size=13, parent=dl)
                dpg.draw_line((LABEL_W, cy), (tw, cy), color=LINE_DIM, thickness=1, parent=dl)
            else:
                dpg.draw_text((15, cy - 7), txt, color=TEXT, size=14, parent=dl)
                dpg.draw_line((LABEL_W, cy + ROW_H//2), (tw, cy + ROW_H//2), color=LINE_DIM, thickness=1, parent=dl)

        for ci, gi in enumerate(range(start, end)):
            x = cx(ci); y = lambda r: ry(r, rows)

            if gi < len(s.qubits) and s.qubits[gi] is not None: pol(dl, x, y("ap"), s.qubits[gi])
            if gi < len(s.alice_bits) and s.alice_bits[gi] is not None: c_text(dl, x, y("ab"), s.alice_bits[gi])
            if gi < len(s.alice_bases) and s.alice_bases[gi] is not None: basis(dl, x, y("abs"), s.alice_bases[gi])

            if s.eve:
                intd = gi in s.eve_set
                if intd:
                    dpg.draw_line((x, y("abs")+12), (x, y("ebs")-12), color=RED, thickness=1.5, parent=dl)
                    dpg.draw_line((x, y("ebt")+12), (x, y("bbs")-12), color=RED, thickness=1.5, parent=dl)
                else: dpg.draw_line((x, y("abs")+12), (x, y("bbs")-12), color=LINE_DIM, thickness=1.5, parent=dl)

                if gi < len(s.eve_bases) and s.eve_bases[gi] is not None:
                    eb = s.eve_bases[gi]
                    ab = s.alice_bases[gi] if gi < len(s.alice_bases) else None
                    basis(dl, x, y("ebs"), eb, GREEN if eb == ab else RED)
                elif not intd: c_text(dl, x, y("ebs"), "-", DIM)

                if gi < len(s.eve_bits) and s.eve_bits[gi] is not None: c_text(dl, x, y("ebt"), s.eve_bits[gi], RED)
                elif not intd: c_text(dl, x, y("ebt"), "-", DIM)
            else:
                dpg.draw_line((x, y("abs")+12), (x, y("bbs")-12), color=LINE_DIM, thickness=1.5, parent=dl)

            if gi < len(s.bob_bases) and s.bob_bases[gi] is not None: basis(dl, x, y("bbs"), s.bob_bases[gi], GREEN if gi in sift else None)
            if gi < len(s.bob_bits) and s.bob_bits[gi] is not None: c_text(dl, x, y("brb"), s.bob_bits[gi], GREEN if gi in sift else TEXT)

            if s.phase != "tx":
                tick(dl, x, y("mt"), gi in sift)
                if gi in sift and s.phase in ("qber", "done"):
                    try:
                        idx = s.match.index(gi)
                        if idx < len(s.sifted): c_text(dl, x, y("sk"), s.sifted[idx], GREEN)
                    except ValueError: pass
                elif s.phase in ("sift", "qber", "done"): c_text(dl, x, y("sk"), "-", DIM)

        dpg.draw_text((LABEL_W, WIN_H - 30), f"Стр. {s.page+1} / {s.max_page+1}   (Стрелки Влево/Вправо)", color=DIM, size=14, parent=dl)
        if s.waiting_for_enter:
            prompt = "  ↵ Enter  →  OTP шифрование"
            dpg.draw_rectangle((LABEL_W - 4, WIN_H - 56), (LABEL_W + 260, WIN_H - 36),
                               fill=(20, 50, 30), color=GREEN, rounding=4, thickness=1, parent=dl)
            dpg.draw_text((LABEL_W + 4, WIN_H - 53), prompt, color=GREEN, size=14, parent=dl)

    def _stats(self, s):
        dl = self.DS; n = s.n; ns = len(s.match)
        kl = len(s.key) if s.key else (len(s.sifted) if s.phase in ("done", "otp", "otp_done") else 0)

        dpg.draw_rectangle((0,0), (STAT_W, WIN_H), fill=PANEL_BG, color=PANEL_BG, parent=dl)
        dpg.draw_text((20, 16), "Статистика сеанса", color=TEXT, size=18, parent=dl)
        dpg.draw_line((0, 50), (STAT_W, 50), color=LINE_DIM, thickness=1, parent=dl)

        y = 60
        y = stat_card(dl, y, "Отправлено кубитов", str(n))
        y = stat_card(dl, y, "Просеянный ключ", f"{ns} битов ({ns/n*100:.0f}%)" if n else "-")
        y = stat_card(dl, y, "Уровень ошибок (QBER)", f"{s.qber:.1%}" if s.qber is not None else "-", RED if (s.qber or 0) > 0.11 else GREEN if s.qber else TEXT)
        y = stat_card(dl, y, "Присутствие Евы", "ОБНАРУЖЕНА" if s.eve_detected else ("Скрыта" if s.eve else "Отсутствует"), RED if s.eve_detected else (ORANGE if s.eve else GREEN))
        y = stat_card(dl, y, "Финальный Ключ BB84", f"{kl} битов" if kl else "-", GREEN if kl else TEXT)

        if s.phase in ["otp", "otp_done"] and hasattr(s, 'otp_info'):
            info = s.otp_info
            short_a = info.get('alice_text','')[:22] + "..."
            short_b = info.get('bob_text','')[:22] + "..."
            short_c = info.get('cipher_hex','')[:22] + "..."
            y = stat_card(dl, y, "Исходный текст", short_a, BLUE)
            y = stat_card(dl, y, "Шифртекст (One-Time Pad)", "0x" + short_c, ORANGE)
            y = stat_card(dl, y, "Расшифровка Боба", short_b, GREEN if info.get('bob_text') == info.get('alice_text') else RED)
            if s.eve:
                short_e = info.get('eve_text','')[:22] + "..."
                y = stat_card(dl, y, "Расшифровка Евы", short_e, RED)

_app = None
_renderer = None

def init_display(eve_present=False):
    global _app, _renderer, _context_created
    if not HAS_DPG: return False
    
    if not _context_created:
        dpg.create_context()
        dpg.create_viewport(title="BB84", width=1210, height=815, resizable=False)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        _context_created = True
    else:
        dpg.set_viewport_title("BB84 Visualizer")
        dpg.set_viewport_width(1210)
        dpg.set_viewport_height(815)
        
    _app = State(eve=eve_present)
    _renderer = R()
    _renderer.setup(_app)
    _renderer.rebuild(_app)
    return True

def running(): return HAS_DPG and dpg.is_dearpygui_running()

def _tick(ms=40):
    end = time.time() + ms/1000
    while time.time() < end:
        if not dpg.is_dearpygui_running(): return False
        dpg.render_dearpygui_frame()
    return True

def _redraw():
    global _app, _renderer
    if _app and _renderer and running():
        dpg.delete_item("dl_grid", children_only=True)
        dpg.delete_item("dl_stats", children_only=True)
        _renderer.rebuild(_app)
        dpg.render_dearpygui_frame()

def draw_transmission_step(step, eve_present=False):
    if not running(): return
    s = _app; i = step["index"]; s.n = i + 1
    for lst in (s.qubits, s.alice_bits, s.alice_bases, s.bob_bases, s.bob_bits, s.eve_bases, s.eve_bits):
        while len(lst) <= i: lst.append(None)
    s.qubits[i] = step["qubit"]; s.alice_bits[i] = step["alice_bit"]
    s.alice_bases[i] = step["alice_basis"]; s.bob_bases[i] = step["bob_basis"]; s.bob_bits[i] = step["bob_bit"]
    if step.get("eve_intercepted"):
        s.eve_set.add(i); s.eve_bases[i] = step.get("eve_basis"); s.eve_bits[i] = step.get("eve_bit")
    s.page = i // 20; s.phase = "tx"
    _redraw(); _tick(40)

def draw_sifting_step(a_bases, b_bases, sifted_mask, max_show=None):
    if not running(): return
    _app.match = list(sifted_mask); _app.phase = "sift"; _app.page = 0; _redraw(); _tick(1500)

def draw_qber_estimation(s_alice, s_bob, sample, qber_val, threshold=0.11):
    if not running(): return
    s = _app; s.sifted = list(s_alice); s.qber = qber_val
    s.eve_detected = qber_val > threshold; s.phase = "qber"; s.page = 0; _redraw(); _tick(2000)

def draw_otp_animation(info):
    if not running(): return
    s = _app
    s.otp_info = info
    s.otp_progress = 1.0
    s.phase = "otp_done"
    s.page = 0
    _redraw()
    while dpg.is_dearpygui_running(): dpg.render_dearpygui_frame()

def draw_final_result(secret_key, info):
    if not running(): return
    s = _app
    s.key = secret_key
    s.eve_detected = info.get("eve_detected", False)
    s.phase = "done"
    s.page = 0
    s.waiting_for_enter = True
    _redraw()
    while running() and s.waiting_for_enter:
        _tick(40)
        _redraw()

def close_display():
    if HAS_DPG and _app: dpg.stop_dearpygui(); dpg.destroy_context()