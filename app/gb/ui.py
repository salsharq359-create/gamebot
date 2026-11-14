"""الألوان والمكونات المشتركة (نفس هوية جيم بوت: كحلي + أخضر فسفوري)."""
from __future__ import annotations

import flet as ft

NAVY, LIME, GOLD = "#141B3D", "#B6FF3B", "#FFC83D"
GAME_COLORS = {"coins": GOLD, "guess": "#9DB4FF", "xo": "#FF9E7A"}
PALETTES = {
    False: dict(BG="#F8F9FD", CARD="#EEF1FA", INK="#141B3D", MUTED="#5A6388", SURFACE="#FFFFFF", NOTE="#FFF4E3",
                BTN_BG="#141B3D", BTN_FG="#FFFFFF", TRACK="#DDE4F5", ERROR="#C62828", OK="#1B7F3B"),
    True: dict(BG="#0D1230", CARD="#1A2150", INK="#EEF1FA", MUTED="#AEB6D6", SURFACE="#141B3D", NOTE="#3A3420",
               BTN_BG="#B6FF3B", BTN_FG="#141B3D", TRACK="#2A3366", ERROR="#FF8A80", OK="#7EE29B"),
}


class Theme:
    """القيم الحالية للألوان وحجم الخط (تتغير مع الوضع الداكن وإعداد التكبير)."""
    dark = False
    scale = 1.0
    c = dict(PALETTES[False])

    @classmethod
    def apply(cls, dark: bool, scale: float) -> None:
        cls.dark, cls.scale, cls.c = bool(dark), float(scale), dict(PALETTES[bool(dark)])


def C(name: str) -> str:
    return Theme.c[name]


def S(n: float) -> float:
    return round(n * Theme.scale, 1)


def T(text, size: float = 14, weight=None, color: str | None = None, **kw) -> ft.Text:
    return ft.Text(str(text), size=S(size), weight=weight, color=color or C("INK"), **kw)


def title(text: str, size: int = 18) -> ft.Text:
    return T(text, size, ft.FontWeight.W_900)


def card(content: ft.Control, bgcolor: str | None = None, padding: int = 14, on_click=None) -> ft.Container:
    return ft.Container(content=content, bgcolor=bgcolor or C("CARD"), border_radius=16, padding=padding,
                        on_click=on_click, ink=on_click is not None)


def note(text: str) -> ft.Container:
    return card(T(text, 13), bgcolor=C("NOTE"))


def _style(bg, fg, side=None):
    return ft.ButtonStyle(bgcolor=bg, color=fg, side=side, shape=ft.RoundedRectangleBorder(radius=14),
                          text_style=ft.TextStyle(font_family="Cairo", size=S(16), weight=ft.FontWeight.BOLD))


def primary(text: str, on_click, icon=None) -> ft.FilledButton:
    return ft.FilledButton(content=text, icon=icon, icon_color=C("BTN_FG"), on_click=on_click, height=50,
                           style=_style(C("BTN_BG"), C("BTN_FG")))


def outline(text: str, on_click, icon=None, color: str | None = None) -> ft.OutlinedButton:
    c = color or C("INK")
    return ft.OutlinedButton(content=text, icon=icon, icon_color=c, on_click=on_click, height=50,
                             style=_style(None, c, ft.BorderSide(2, c)))


def label_style() -> ft.TextStyle:
    return ft.TextStyle(font_family="Cairo", size=S(15), weight=ft.FontWeight.BOLD, color=C("INK"))


def robot_logo(size: int = 90) -> ft.Container:
    return ft.Container(width=size, height=size, bgcolor=NAVY, border_radius=size * 0.26,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Icon(ft.Icons.SMART_TOY_OUTLINED, color=LIME, size=size * 0.62))


def balance_card(label: str, cents: int, sub: str | None = None) -> ft.Container:
    items = [ft.Text(label, size=S(13), color="#C9CEE4", weight=ft.FontWeight.BOLD),
             ft.Text(f"$ {cents / 100:.2f}", size=S(34), color=LIME, weight=ft.FontWeight.W_900),
             ft.Text("كل لعبة = 1$  •  أرباح محاكاة", size=S(12), color=ft.Colors.WHITE)]
    if sub:
        items.append(ft.Text(sub, size=S(12), color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD))
    return ft.Container(ft.Column(items, spacing=2), bgcolor=NAVY, border_radius=18, padding=18,
                        border=ft.Border.all(1, C("TRACK")))


def stat(label: str, value: str) -> ft.Container:
    return ft.Container(card(ft.Column([T(label, 12, ft.FontWeight.BOLD, C("MUTED")),
                                        T(value, 18, ft.FontWeight.W_900)], spacing=0), padding=12), expand=True)


def menu_item(icon, text: str, sub: str, on_click) -> ft.Container:
    return card(ft.Row([
        ft.Container(ft.Icon(icon, color=NAVY, size=S(24)), width=44, height=44, border_radius=12, bgcolor=LIME,
                     alignment=ft.Alignment.CENTER),
        ft.Column([T(text, 16, ft.FontWeight.W_900), T(sub, 12, color=C("MUTED"))], spacing=0, expand=True),
        ft.Icon(ft.Icons.CHEVRON_LEFT, color=C("MUTED")),
    ], spacing=12), on_click=on_click)


def textfield(label: str, icon=None, password: bool = False, **kw) -> ft.TextField:
    return ft.TextField(label=label, prefix_icon=icon, password=password, can_reveal_password=password,
                        border_radius=14, **kw)


def strength(pw: str) -> tuple[int, str]:
    """تقدير قوة كلمة المرور على الجهاز (الطول أهم من الرموز، حسب NIST). الخادم يتحقق فعلياً."""
    labels = ["ضعيفة جداً", "مقبولة", "جيدة", "قوية", "قوية جداً"]
    if len(pw) < 8:
        return 0, labels[0]
    score = 1 + (len(pw) >= 12) + (len(pw) >= 15)
    if len(set(pw)) >= 8 and any(not ch.isalpha() for ch in pw):
        score += 1
    return score, labels[score]
