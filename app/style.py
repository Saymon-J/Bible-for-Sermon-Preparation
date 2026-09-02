# -*- coding: utf-8 -*-
"""Тема Microsoft Fluent 2 на ttk/clam: плоские элементы, фирменный синий,
карточки на подложке, тонкие бегунки без стрелок (радиусов в ttk нет — flat)."""
import tkinter as tk
from tkinter import ttk, font as tkfont


def apply_fluent_style(root, T, ui):
    """root — окно, T — словарь темы (theme.THEMES[...]), ui — кортеж (гарнитура, размер)."""
    st = ttk.Style(root)
    try:
        st.theme_use('clam')
    except Exception:
        pass
    st.configure('.', background=T['window_bg'], foreground=T['fg'], font=ui)
    st.configure('TFrame', background=T['window_bg'])
    st.configure('TLabel', background=T['window_bg'], foreground=T['fg'])
    st.configure('Fg2.TLabel', foreground=T['fg2'])
    st.configure('TSeparator', background=T['stroke'])

    ring = [T['stroke']] * 3          # bordercolor/lightcolor/darkcolor — рамка 1px
    ring_hover = [T['stroke_hover']] * 3
    ring_dis = [T['stroke2']] * 3

    # вторичная кнопка: карточка с рамкой, ховер — светлее
    st.configure('TButton', background=T['text_bg'], foreground=T['fg'],
                 bordercolor=ring[0], lightcolor=ring[1], darkcolor=ring[2],
                 padding=(12, 4), focuscolor=T['text_bg'])
    st.map('TButton',
           background=[('disabled', T['text_bg']), ('pressed', T['press']),
                       ('active', T['hover'])],
           foreground=[('disabled', T['fg2'])],
           bordercolor=[('disabled', ring_dis[0]), ('pressed', ring_hover[0]),
                        ('active', ring_hover[0])],
           lightcolor=[('disabled', ring_dis[1]), ('pressed', ring_hover[1]),
                       ('active', ring_hover[1])],
           darkcolor=[('disabled', ring_dis[2]), ('pressed', ring_hover[2]),
                      ('active', ring_hover[2])])

    # главная кнопка — фирменная заливка
    st.configure('Accent.TButton', background=T['accent'], foreground=T['accent_text'],
                 bordercolor=T['accent'], lightcolor=T['accent'], darkcolor=T['accent'],
                 padding=(12, 4), focuscolor=T['accent'])
    st.map('Accent.TButton',
           background=[('disabled', T['stroke2']), ('pressed', T['accent_press']),
                       ('active', T['accent_hover'])],
           foreground=[('disabled', T['fg2'])])

    # кнопка тулбара: прозрачная, рамка и подложка появляются на ховере
    st.configure('Tool.TButton', background=T['window_bg'], foreground=T['fg'],
                 bordercolor=T['window_bg'], lightcolor=T['window_bg'],
                 darkcolor=T['window_bg'], padding=(10, 4),
                 focuscolor=T['window_bg'])
    st.map('Tool.TButton',
           background=[('disabled', T['window_bg']), ('pressed', T['press']),
                       ('active', T['hover'])],
           foreground=[('disabled', T['fg2'])],
           bordercolor=[('active', T['stroke'])],
           lightcolor=[('active', T['stroke'])],
           darkcolor=[('active', T['stroke'])])

    # «⋯» — свёрнутые кнопки тулбара: тот же вид, что у кнопки тулбара
    st.configure('Tool.TMenubutton', background=T['window_bg'], foreground=T['fg'],
                 bordercolor=T['window_bg'], lightcolor=T['window_bg'],
                 darkcolor=T['window_bg'], padding=(10, 4), focuscolor=T['window_bg'],
                 arrowcolor=T['fg'])
    st.map('Tool.TMenubutton',
           background=[('disabled', T['window_bg']), ('pressed', T['press']),
                       ('active', T['hover'])],
           foreground=[('disabled', T['fg2'])],
           bordercolor=[('active', T['stroke'])],
           lightcolor=[('active', T['stroke'])],
           darkcolor=[('active', T['stroke'])])

    # компактная кнопка тулбара (иконки, «Урок»): тот же вид, уже паддинги
    st.configure('ToolFit.TButton', padding=(4, 4))

    # иконки тулбара: родные Fluent-глифы Windows (PUA-шрифт, не эмодзи —
    # эмодзи в tk рендерятся тонким монохромным контуром). Кегль +4, поля
    # минимальные, но по горизонтали 4px: Fluent-глифы рисуются чуть шире
    # своей измеренной ширины — без запаса край срезается
    ico = next((f for f in ('Segoe Fluent Icons', 'Segoe MDL2 Assets')
                if f in tkfont.families(root)), None)
    if ico:
        st.configure('Ico.ToolFit.TButton', font=(ico, ui[1] + 4), padding=(4, 2))
        st.configure('Ico.ToolOn.TButton', font=(ico, ui[1] + 4), padding=(4, 2))

    # включённый тумблер тулбара («Стих из буфера», «Синхр.»): зелёная рамка
    st.configure('ToolOn.TButton', background=T['green_bg'], foreground=T['fg'],
                 bordercolor=T['green'], lightcolor=T['green'],
                 darkcolor=T['green'], padding=(4, 4), focuscolor=T['green_bg'])
    st.map('ToolOn.TButton',
           background=[('disabled', T['window_bg']), ('pressed', T['green_hover']),
                       ('active', T['green_hover'])],
           foreground=[('disabled', T['fg2'])],
           bordercolor=[('disabled', T['stroke2']), ('pressed', T['green']),
                        ('active', T['green'])],
           lightcolor=[('disabled', T['stroke2']), ('pressed', T['green']),
                       ('active', T['green'])],
           darkcolor=[('disabled', T['stroke2']), ('pressed', T['green']),
                      ('active', T['green'])])

    st.configure('TCheckbutton', background=T['window_bg'], foreground=T['fg'],
                 focuscolor=T['window_bg'])
    st.map('TCheckbutton', background=[('active', T['window_bg'])],
           foreground=[('disabled', T['fg2'])])

    # вкладки (окно «Модули»): на подложке, выбранная — карточка
    st.configure('TNotebook', background=T['window_bg'], borderwidth=0, tabmargins=(0, 4, 0, 0))
    st.configure('TNotebook.Tab', background=T['window_bg'], foreground=T['fg'],
                 padding=(14, 5), focuscolor=T['window_bg'])
    st.map('TNotebook.Tab',
           background=[('selected', T['text_bg']), ('active', T['hover'])])

    # поля ввода: рамка 1px, в фокусе — фирменный синий
    for w in ('TEntry', 'TSpinbox'):
        st.configure(w, fieldbackground=T['text_bg'], foreground=T['fg'],
                     bordercolor=T['stroke'], lightcolor=T['text_bg'],
                     darkcolor=T['stroke'], padding=(6, 3), arrowcolor=T['fg'])
        st.map(w, bordercolor=[('focus', T['accent'])],
               lightcolor=[('focus', T['accent'])],
               darkcolor=[('focus', T['accent'])])
    st.configure('TCombobox', fieldbackground=T['text_bg'], background=T['text_bg'],
                 foreground=T['fg'], arrowcolor=T['fg'], bordercolor=T['stroke'],
                 lightcolor=T['text_bg'], darkcolor=T['stroke'],
                 arrowsize=11, padding=(6, 3))
    st.map('TCombobox',
           fieldbackground=[('readonly', T['text_bg'])],
           foreground=[('readonly', T['fg'])],
           bordercolor=[('focus', T['accent'])],
           lightcolor=[('focus', T['accent'])],
           darkcolor=[('focus', T['accent'])])

    # таблицы: без рамок, выбранная строка — светло-синяя
    st.configure('Treeview', background=T['text_bg'], foreground=T['fg'],
                 fieldbackground=T['text_bg'], borderwidth=0, relief='flat',
                 rowheight=26)
    st.map('Treeview', background=[('selected', T['menu_active'])],
           foreground=[('selected', T['fg'])])
    st.configure('Treeview.Heading', background=T['window_bg'], foreground=T['fg2'],
                 relief='flat', padding=(8, 5))
    st.map('Treeview.Heading', background=[('active', T['hover'])])

    # бегунки Fluent: тонкие, без насечек, темнеют на ховере; стрелки штатного
    # layout задают ширину — красим в цвет желоба (невидимы, но кликабельны)
    st.configure('Vertical.TScrollbar', troughcolor=T['window_bg'],
                 background=T['thumb'], bordercolor=T['window_bg'],
                 lightcolor=T['window_bg'], darkcolor=T['window_bg'],
                 arrowcolor=T['window_bg'], gripcount=0, arrowsize=13)
    st.map('Vertical.TScrollbar', background=[('active', T['fg2'])])

    for opt, val in (('background', T['text_bg']), ('foreground', T['fg']),
                     ('selectBackground', T['menu_active']),
                     ('selectForeground', T['fg']),
                     ('borderWidth', 0), ('relief', 'flat'),
                     ('highlightThickness', 0), ('font', ui)):
        root.option_add(f'*TCombobox*Listbox.{opt}', val)


def tag_greek(t, color):
    """Подкрасить древнегреческие слова в уже заполненном tk.Text (политоника
    U+1F00–1FFF + базовая греческая U+0370–3FF). Звать после вставки текста."""
    t.tag_configure('grk', foreground=color)
    t.tag_raise('grk')  # поверх шрифтовых тегов (курсив и пр.)
    n = tk.IntVar()
    pos = '1.0'
    while True:
        m = t.search('[\u0370-\u03ff\u1f00-\u1fff]+', pos, 'end', regexp=True, count=n)
        if not m or not n.get():
            break
        end = f'{m}+{n.get()}c'
        t.tag_add('grk', m, end)
        pos = end
