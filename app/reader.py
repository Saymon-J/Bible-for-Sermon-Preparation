# -*- coding: utf-8 -*-
"""Окно читалки: панели чтения (до трёх), переход книги→главы→стихи, история
отрывков, синхронная прокрутка панелей, выделение стихов, Стронг."""
import re

import tkinter as tk
from tkinter import ttk, messagebox

from markup import (build_copy, note_to_plain, parse_markup, split_strong_tokens,
                    xref_text)
from refs import BOOK_SECTIONS, full_book_name, strong_body_from_entry
from theme import TEXT_FONT, THEMES, UI_FONT_SIZE
from style import tag_greek
from windows import CommentaryWindow, SearchWindow




class ReaderWindow:
    def __init__(self, app, master, state=None):
        self.app = app
        self.top = master
        self.sync = tk.BooleanVar(value=False)
        self.strongs = tk.BooleanVar(value=False)
        self._syncing = False
        self._scroll_sync = False   # идёт рендер или перенос прокрутки — не зацикливаем
        self._hist_after = None     # длинное нажатие «Истории»
        self._hist_long = False
        self._popup = None  # всплывающая кнопка «Скопировать»
        self.comm_windows = []
        self.panes = []          # панели чтения: {module, book_idx, chapter, frame, text, …}
        self.active_idx = 0     # панель, которой управляет тулбар (последняя кликнутая)
        self._pane_by_text = {}  # id(Text) -> панель
        st = state or {}
        self._build_ui()
        pane_states = st.get('panes') or [{'module': st.get('module'),
                                           'book': st.get('book', 0),
                                           'chapter': st.get('chapter', 1)}]
        for ps in pane_states[:3]:
            mi = 0
            for i, m in enumerate(app.translations):
                if m.file_name == ps.get('module'):
                    mi = i
                    break
            self._make_pane(app.translations[mi], ps.get('book', 0), ps.get('chapter', 1))
        self.active_idx = min(st.get('active', 0), len(self.panes) - 1)
        if len(self.panes) > 1:  # у панелей свои селекторы перевода
            for p in self.panes:
                self._ensure_header(p)
            self.cb_trans.pack_forget()
        self.sync.set(bool(st.get('sync', False)))
        self.strongs.set(bool(st.get('strongs', False)))
        self._refresh_all()
        self._mark_active()
        for p in self.panes:
            self._render_pane(p)
        self._set_title()
        self._reset_history()
        for fn in st.get('commentaries') or []:
            comm = next((c for c in app.commentaries if c.file_name == fn), None)
            if comm:
                self.open_commentary(comm)

    # Активная панель снаружи выглядит как «читалка» целиком — потребители в
    # windows.py/application.py (комментарий, поиск, словарь, попап стиха) не меняются.
    @property
    def module(self):
        return self.panes[self.active_idx]['module']

    @module.setter
    def module(self, m):
        self.panes[self.active_idx]['module'] = m

    @property
    def book_idx(self):
        return self.panes[self.active_idx]['book_idx']

    @book_idx.setter
    def book_idx(self, v):
        self.panes[self.active_idx]['book_idx'] = v

    @property
    def chapter(self):
        return self.panes[self.active_idx]['chapter']

    @chapter.setter
    def chapter(self, v):
        self.panes[self.active_idx]['chapter'] = v

    @property
    def _fns(self):  # встроенные сноски активной панели — читает окно комментария
        return self.panes[self.active_idx]['fns']

    def _reset_history(self):
        """История отрывков панели: [(номер книги, глава, стих|None)] — номер книги,
        не индекс: переживает смену перевода панели."""
        for p in self.panes:
            p['hist'] = [(p['module'].books[p['book_idx']][0], p['chapter'], None)]
            p['hist_pos'] = 0

    def _build_ui(self):
        T = self.app.theme()
        self.top.configure(bg=T['window_bg'])
        self._build_menu()

        self._reading = False
        self.top.minsize(620, 420)

        self.bar = ttk.Frame(self.top, padding=(12, 7, 12, 7))
        self.bar.pack(fill='x')
        self.cb_trans = ttk.Combobox(self.bar, state='readonly', width=26)
        self.btn_book = ttk.Button(self.bar, width=22, style='Tool.TButton',
                                   command=self.open_books)
        self.btn_chap = ttk.Button(self.bar, width=3, style='Tool.TButton',
                                   command=self.open_books)
        self.cb_trans.pack(side='left', padx=(0, 6))
        self.btn_book.pack(side='left', padx=(0, 6))
        self.btn_chap.pack(side='left', padx=(0, 6))
        self._tb_base = [self.cb_trans, self.btn_book, self.btn_chap]
        # ⟲: клик — отрывок назад, зажатие (450 мс) — окно истории
        self.btn_hist = ttk.Button(self.bar, text='\uE7A6', width=2,
                                   style='Ico.ToolFit.TButton')
        self.btn_hist.bind('<Button-1>', self._hist_press)
        self.btn_hist.bind('<ButtonRelease-1>', self._hist_release)
        self.btn_hist.pack(side='left', padx=(0, 1))
        self._tb_base.append(self.btn_hist)
        self.btn_split = ttk.Button(self.bar, text='\uE700',
                                    style='Ico.ToolFit.TButton',
                                    command=self.split_pane)
        self.btn_split.pack(side='left', padx=(6, 1))
        self._tb_base.append(self.btn_split)
        for step, arrow in ((-1, '◀'), (1, '▶')):
            b = ttk.Button(self.bar, text=arrow, width=2, style='Tool.TButton',
                           command=lambda s=step: self.step_chapter(s))
            b.pack(side='left', padx=1)
            self._tb_base.append(b)
        # вторичные контролы: в узком окне сворачиваются (с конца) в меню «⋯»;
        # tb_text — что на кнопке (Fluent-глифы E77B/E736/E8C8/E8AB — иконки
        # шрифтом Segoe Fluent Icons), menu_label — как зовут в меню
        self._tb_specs = [
            ('cmd', '🔍 Поиск', 'Поиск', None, self.open_search, 'ToolFit.TButton'),
            ('toggle', 'Стронг', 'Стронг', self.strongs, self.render_all, None),
            ('cmd', '\uE77B', 'Комментарий', None, lambda: self.open_commentary(),
             'Ico.ToolFit.TButton'),
            ('cmd', '\uE736', 'Словарь', None, lambda: self.app.open_dict(self),
             'Ico.ToolFit.TButton'),
            ('cmd', 'Урок', 'Урок', None, self.app.open_lesson, 'ToolFit.TButton'),
            ('toggle', '\uE8C8', 'Стих из буфера', self.app.clipref_var,
             self.app._clipref_toggled, 'Ico.ToolFit.TButton'),
            ('toggle', '\uE8AB', 'Синхр.', self.sync, None, 'Ico.ToolFit.TButton'),
        ]
        self._tb_extra = [self._make_tb_widget(spec) for spec in self._tb_specs]
        self.tb_more = ttk.Menubutton(self.bar, text='⋯', width=2,
                                      style='Tool.TMenubutton')
        self.tb_more_menu = tk.Menu(
            self.tb_more, tearoff=0, bg=T['text_bg'], fg=T['fg'], bd=0,
            activebackground=T['menu_active'], activeforeground=T['fg'])
        self.tb_more.configure(menu=self.tb_more_menu)
        self._tb_shown = -1   # сколько вторичных видно (-1 — ещё не раскладывали)
        self._tb_last_w = -1
        self.top.bind('<Configure>', self._on_configure)
        self.toolbar_sep = ttk.Separator(self.top, orient='horizontal')
        self.toolbar_sep.pack(fill='x')

        self.cb_trans.bind('<<ComboboxSelected>>', self.on_trans)
        self.top.bind('<Control-Left>', lambda e: self.step_chapter(-1))
        self.top.bind('<Control-Right>', lambda e: self.step_chapter(1))
        self.top.bind('<Alt-Left>', lambda e: self.history_go(-1))
        self.top.bind('<Alt-Right>', lambda e: self.history_go(1))
        self.top.bind('<Control-f>', lambda e: self.open_search())
        self.top.bind('<F11>', self.toggle_reading)
        self.top.bind('<Escape>', lambda e: self._exit_reading_or_clear())
        self.app.reg_copy(self.top, self.on_copy_key)

        self.body = ttk.Frame(self.top, padding=(12, 4, 12, 12))
        self.body.pack(fill='both', expand=True)
        # панели делят всю ширину окна поровну (weight=1), разделители тянутся мышью
        self.pane_host = ttk.PanedWindow(self.body, orient='horizontal')
        self.pane_host.pack(fill='both', expand=True)
        self.apply_fonts()

    def _make_tb_widget(self, spec):
        kind, tbt, _label, var, cmd, style = spec
        if kind == 'check':
            return ttk.Checkbutton(self.bar, text=tbt, variable=var, command=cmd)
        if kind == 'toggle':  # включено — зелёная рамка; галочка остаётся в меню
            off = style or 'ToolFit.TButton'
            on = off.replace('ToolFit', 'ToolOn', 1)
            btn = ttk.Button(self.bar, text=tbt, style=off,
                             command=lambda: (var.set(not var.get()), cmd and cmd()))

            def sync(*_):
                if btn.winfo_exists():  # окно могли закрыть, а трейс на общем var жив
                    btn.configure(style=on if var.get() else off)
            var.trace_add('write', sync)
            sync()
            return btn
        return ttk.Button(self.bar, text=tbt, style=style, command=cmd)

    # --- панели чтения ---

    def _make_pane(self, module, book_idx=0, chapter=1):
        T = self.app.theme()
        p = {'module': module, 'book_idx': book_idx, 'chapter': chapter,
             'selected': set(), 'anchor': None, 'raws': {}, 'found_verse': None,
             'found_mark': False, 'hist': [(module.books[book_idx][0], chapter, None)],
             'hist_pos': 0, 'strong_seq': 0, 'tags': {}, 'fns': [], 'head': None,
             'cb': None, 'bbtn': None, 'cbtn': None}
        p['frame'] = frm = ttk.Frame(self.body)
        # карточка Fluent: белый лист с рамкой 1px; активная панель — синяя рамка.
        # width=1: иначе Text требует ~80 символов и панели не сжимаются под окно
        p['text'] = t = tk.Text(frm, wrap='word', width=1, padx=18, pady=10,
                                cursor='arrow', font=(TEXT_FONT, self.app.font_size),
                                takefocus=0, relief='flat', bd=0, highlightthickness=1,
                                highlightbackground=T['stroke'],
                                highlightcolor=T['stroke'])
        p['sb'] = sb = ttk.Scrollbar(frm, command=t.yview)
        # любая прокрутка панели (колесо, бегунок, клавиши) проходит через нас —
        # точка синхронной прокрутки остальных панелей окна
        t.configure(yscrollcommand=lambda a, b, pp=p: self._pane_scrolled(pp, a, b))
        sb.pack(side='right', fill='y')
        t.pack(side='left', fill='both', expand=True)
        t.bind('<Button-1>', self._on_text_click, add='+')
        t.bind('<Control-Double-1>', self._on_compare_click, add='+')
        self.panes.append(p)
        self._pane_by_text[id(t)] = p
        self.pane_host.add(frm, weight=1)
        self.top.minsize(max(620, 360 * len(self.panes) + 60), 420)
        self.apply_fonts_pane(p)
        return p

    def _ensure_header(self, p):
        """Шапка панели (видна только когда панелей несколько): своя книга, глава,
        перевод и ✕."""
        if p['head'] is not None:
            return
        p['head'] = head = ttk.Frame(p['frame'], padding=(0, 0, 0, 4))
        head.pack(side='top', fill='x', before=p['sb'])
        p['bbtn'] = bbtn = ttk.Button(head, style='ToolFit.TButton',
                                      command=lambda pp=p: self.open_books(pane=pp))
        bbtn.pack(side='left')
        p['cbtn'] = cbtn = ttk.Button(head, width=3, style='ToolFit.TButton',
                                      command=lambda pp=p: self.open_books(pane=pp))
        cbtn.pack(side='left', padx=(4, 0))
        p['cb'] = cb = ttk.Combobox(head, state='readonly', width=14)
        cb.pack(side='left', fill='x', expand=True, padx=(6, 0))
        cb['values'] = [m.description for m in self.app.translations]
        cb.set(p['module'].description)
        cb.bind('<<ComboboxSelected>>', lambda e, pp=p: self._pane_trans(pp))
        ttk.Button(head, text='✕', width=2, style='Tool.TButton',
                   command=lambda pp=p: self.close_pane(pp)).pack(side='left',
                                                                  padx=(6, 0))
        self._refresh_pane_header(p)

    def _refresh_pane_header(self, p):
        """Книга/глава в шапке панели — вслед за самой панелью."""
        if p['head'] is None:
            return
        p['bbtn'].configure(
            text=p['module'].books[p['book_idx']][1].replace(chr(0x200A), ' '))
        p['cbtn'].configure(text=str(p['chapter']))

    def _drop_header(self, p):
        if p['head'] is not None:
            p['head'].destroy()
            p['head'] = p['cb'] = p['bbtn'] = p['cbtn'] = None

    def split_pane(self):
        """☰: добавить панель чтения (до трёх) в этом же окне, с новым переводом."""
        if len(self.panes) >= 3:
            return
        cur = self.panes[self.active_idx]
        used = {p['module'].file_name for p in self.panes}
        nxt = next((m for m in self.app.translations if m.file_name not in used),
                   cur['module'])
        bn = cur['module'].books[cur['book_idx']][0]
        bi = next((i for i, b in enumerate(nxt.books) if b[0] == bn), 0)
        p = self._make_pane(nxt, bi, cur['chapter'])
        if len(self.panes) > 1:  # селекторы перевода переезжают в шапки панелей
            for pp in self.panes:
                self._ensure_header(pp)
            self.cb_trans.pack_forget()
        self._render_pane(p)
        self._activate(p)
        self._tb_relayout(self.top.winfo_width())

    def close_pane(self, p):
        if len(self.panes) <= 1:
            return
        i = self.panes.index(p)
        self.panes.remove(p)
        self._pane_by_text.pop(id(p['text']), None)
        self.pane_host.forget(p['frame'])
        p['frame'].destroy()
        if i < self.active_idx:
            self.active_idx -= 1
        self.active_idx = min(self.active_idx, len(self.panes) - 1)
        self.top.minsize(max(620, 360 * len(self.panes) + 60), 420)
        if len(self.panes) == 1:
            self._drop_header(self.panes[0])
            self.cb_trans.pack(side='left', padx=(0, 6), before=self.btn_book)
        self._refresh_all()
        self._mark_active()
        self._set_title()
        self._tb_relayout(self.top.winfo_width())

    def _pane_trans(self, p):
        idx = p['cb'].current()
        if idx < 0:
            return
        p['module'] = self.app.translations[idx]
        self._render_pane(p)
        if p is self.panes[self.active_idx]:
            self._refresh_all()
            self._set_title()

    def _activate(self, p):
        i = self.panes.index(p)
        if i == self.active_idx:
            return
        self.active_idx = i
        self._refresh_all()
        self._mark_active()
        self._set_title()

    def _mark_active(self):
        T = self.app.theme()
        for i, p in enumerate(self.panes):
            p['text'].configure(
                highlightbackground=T['accent'] if i == self.active_idx else T['stroke'],
                highlightcolor=T['accent'] if i == self.active_idx else T['stroke'])

    def remap_modules(self, trans):
        """Смена набора переводов (reload_modules): перекидывает модули всех панелей."""
        for p in self.panes:
            m = next((m for m in trans if m.file_name == p['module'].file_name), None)
            if m is None:
                p['module'], p['book_idx'], p['chapter'] = trans[0], 0, 1
            else:
                p['module'] = m
            if p['cb'] is not None:
                p['cb'].set(p['module'].description)

    def toggle_reading(self, _=None):
        """F11 — режим чтения: тулбар и меню спрятаны, только текст. F11/Esc — обратно."""
        self._reading = not self._reading
        if self._reading:
            self.bar.pack_forget()
            self.toolbar_sep.pack_forget()
            self.top.configure(menu='')  # снять панель меню
        else:
            self.bar.pack(fill='x', before=self.body)
            self.toolbar_sep.pack(fill='x', before=self.body)
            self.top.configure(menu=self._menu_bar)
            self._tb_relayout(self.top.winfo_width())

    def _on_configure(self, e):
        if e.widget is self.top and e.width != self._tb_last_w:
            self._tb_last_w = e.width
            self._tb_relayout(e.width)

    def _tb_relayout(self, w):
        """Узкое окно: сколько вторичных кнопок тулбара влезает, остальные — в меню «⋯»."""
        if self._reading or w < 60:
            return
        room = w - 48  # паддинги тулбара + запас
        # cb_trans скрыт в многопанельном режиме — считаем только упакованные
        base = sum(x.winfo_reqwidth() for x in self._tb_base
                   if x.winfo_manager()) + 20  # их padx
        need = base + sum(x.winfo_reqwidth() + 10 for x in self._tb_extra)
        shown = len(self._tb_extra)
        if need > room:  # место под саму кнопку «⋯»
            need += self.tb_more.winfo_reqwidth() + 10
            while shown > 0 and need > room:
                shown -= 1
                need -= self._tb_extra[shown].winfo_reqwidth() + 10
        if shown == self._tb_shown:
            return
        self._tb_shown = shown
        for wgt in self._tb_extra[shown:]:
            wgt.pack_forget()
        for wgt in self._tb_extra[:shown]:
            if not wgt.winfo_manager():
                wgt.pack(side='left', padx=(10, 0))
        m = self.tb_more_menu
        m.delete(0, 'end')
        for kind, _tbt, label, var, cmd, _style in self._tb_specs[shown:]:
            if kind in ('check', 'toggle'):  # в меню тумблер — обычная галочка
                m.add_checkbutton(label=label, variable=var, command=cmd)
            else:
                m.add_command(label=label, command=cmd)
        if shown < len(self._tb_extra):
            self.tb_more.pack(side='left', padx=(10, 0))
        else:
            self.tb_more.pack_forget()

    def _exit_reading_or_clear(self):
        if self._reading:
            self.toggle_reading()
        else:
            self.clear_selection()

    def _build_menu(self):
        T = self.app.theme()
        # панель меню лежит на подложке, выпадающие списки — карточки (как в Win11)
        bar_kw = dict(bg=T['window_bg'], fg=T['fg'], bd=0,
                      activebackground=T['menu_active'], activeforeground=T['fg'])
        dd_kw = dict(bar_kw, bg=T['text_bg'])
        mb = tk.Menu(self.top, **bar_kw)
        m_file = tk.Menu(mb, tearoff=0, **dd_kw)
        m_file.add_command(label='Собрать урок…', command=self.app.open_lesson)
        m_file.add_command(label='Добавить модуль…', command=self.app.add_module)
        m_file.add_command(label='Модули…', command=self.app.open_download)
        m_file.add_command(label='Обновить переводы', command=self.app.reload_modules)
        m_file.add_separator()
        m_file.add_command(label='О программе…', command=self.app.about)
        m_view = tk.Menu(mb, tearoff=0, **dd_kw)
        m_theme = tk.Menu(m_view, tearoff=0, **dd_kw)
        for name in THEMES:
            m_theme.add_radiobutton(label=name, variable=self.app.theme_var,
                                    command=lambda n=name: self.app.set_theme(n))
        m_view.add_cascade(label='Тема', menu=m_theme)
        m_view.add_command(label='Режим чтения\tF11', command=self.toggle_reading)
        m_view.add_command(label='+ Окно (новое)', command=self.app.new_window)
        m_view.add_command(label='Шрифт…', command=self.app.open_font_dialog)
        m_view.add_command(label='Словарь…', command=lambda: self.app.open_dict(self))
        m_view.add_checkbutton(label='Стих из буфера', variable=self.app.clipref_var,
                               command=self.app._clipref_toggled)
        m_view.add_checkbutton(label='Копировать стихи в одну строку',
                               variable=self.app.copy_inline)
        m_view.add_command(label='Введение к книге', command=self.show_introduction)
        m_view.add_command(label='Поиск\tCtrl+F', command=self.open_search)
        m_nav = tk.Menu(mb, tearoff=0, **dd_kw)
        m_nav.add_command(label='Назад\tAlt+←', command=lambda: self.history_go(-1))
        m_nav.add_command(label='Вперёд\tAlt+→', command=lambda: self.history_go(1))
        m_nav.add_command(label='История…', command=self.show_history)
        mb.add_cascade(label='Файл', menu=m_file)
        mb.add_cascade(label='Вид', menu=m_view)
        mb.add_cascade(label='Переход', menu=m_nav)
        self.top.configure(menu=mb)
        self._menu_bar = mb
        self._menus = [m_file, m_view, m_theme, m_nav]

    def apply_theme_menus(self):
        T = self.app.theme()
        self._menu_bar.configure(bg=T['window_bg'])
        for m in self._menus:
            m.configure(bg=T['text_bg'])
        for m in [self._menu_bar] + self._menus:
            m.configure(fg=T['fg'], activebackground=T['menu_active'],
                        activeforeground=T['fg'])
        self.tb_more_menu.configure(bg=T['text_bg'], fg=T['fg'],
                                    activebackground=T['menu_active'],
                                    activeforeground=T['fg'])

    def apply_fonts(self):
        for p in self.panes:
            self.apply_fonts_pane(p)

    def apply_fonts_pane(self, p):
        s = self.app.font_size
        fam = self.app.font_family
        T = self.app.theme()
        t = p['text']
        t.configure(font=(fam, s), bg=T['text_bg'], fg=T['fg'],
                    selectbackground=T['selv'], selectforeground=T['fg'],
                    insertbackground=T['fg'],
                    highlightbackground=T['stroke'], highlightcolor=T['stroke'])
        t.tag_configure('vnum', font=(fam, max(s - 5, 8)),
                        foreground=T['vnum'], spacing3=4)
        t.tag_configure('story', font=(fam, s, 'bold'),
                        spacing1=16, spacing3=8, justify='center')
        t.tag_configure('header', font=(fam, s + 4, 'bold'), foreground=T['chapter'],
                        spacing3=12, justify='center')
        t.tag_configure('selv', background=T['selv'])
        t.tag_configure('found', background=T['found'])
        p['tags'] = {}

    def style_tag(self, p, st):
        key = ''.join(sorted(st)) or 'plain'
        if key not in p['tags']:
            font = [self.app.font_family, self.app.font_size]
            if 'ital' in st:
                font.append('italic')
            opts = {'font': tuple(font)}
            if 'red' in st:
                opts['foreground'] = self.app.theme()['red']
            if 'poetry' in st:
                opts.update(lmargin1=36, lmargin2=36)
            p['text'].tag_configure(key, **opts)
            p['tags'][key] = True
        return key

    def _nl(self, p):
        if p['text'].get('end-2c', 'end-1c') != '\n':
            p['text'].insert('end', '\n')

    def _max_chapter(self, module, bi):
        return module.chapters.get(module.books[bi][0], 1)

    # --- рендер главы: каждый стих с новой строки, тег vs{N} на весь стих ---
    def _render_pane(self, p):
        # во время рендера вид сбрасывается и yscrollcommand стреляет — гасим,
        # чтобы пересборка главы не дёргала синхронную прокрутку других панелей
        self._scroll_sync = True
        try:
            self._render_pane_text(p)
        finally:
            self._scroll_sync = False

    def _render_pane_text(self, p):
        p['book_idx'] = min(max(p['book_idx'], 0), len(p['module'].books) - 1)
        module = p['module']
        book_number, short_name, _long_name = module.books[p['book_idx']]
        nch = self._max_chapter(module, p['book_idx'])
        p['chapter'] = min(max(p['chapter'], 1), nch)
        t = p['text']
        t.configure(state='normal')
        t.delete('1.0', 'end')
        # ponytail: >100 глав бывает только у Псалтыри — так выбираем
        # «Псалом N» вместо «Глава N» без привязки к языку модуля
        word = module.chapter_string_ps if nch > 100 else module.chapter_string
        t.insert('end', f'{word} {p["chapter"]}\n', ('header',))
        stories = module.stories(book_number, p['chapter'])
        p['raws'] = {}
        p['fns'] = []
        p['selected'] = set()
        p['anchor'] = None
        p['strong_seq'] = 0
        self._hide_popup()
        for vnum, raw in module.verses(book_number, p['chapter']):
            p['raws'][vnum] = raw
            for title in stories.get(vnum, ()):
                self._nl(p)
                # в заголовках NRT бывают <x>-ссылки — разворачиваем в имена книг
                t.insert('end', note_to_plain(title, module.short_map) + '\n',
                         ('story',))
            vstart = t.index('end-1c')
            t.insert('end', str(vnum), ('vnum',))
            t.insert('end', ' ')
            started = False  # ведущие <pb/> в начале стиха не отрывают номер от текста
            for kind, val, st in parse_markup(raw):
                if kind == 'text':
                    t.insert('end', val, (self.style_tag(p, st),))
                    started = True
                elif kind == 'nl':
                    if started:
                        self._nl(p)
                elif kind == 'xref':
                    t.insert('end', xref_text(val, module.short_map) + ' ',
                             (self.style_tag(p, frozenset()),))
                    started = True
                elif kind == 'sn':
                    if self.strongs.get():
                        p['strong_seq'] += 1
                        tag = f'sng{p["strong_seq"]}'
                        t.tag_configure(tag, font=(self.app.font_family,
                                                   max(self.app.font_size - 6, 7)),
                                        foreground=self.app.theme()['strong'])
                        t.tag_bind(tag, '<Button-1>',
                                   lambda e, n=val, v=vnum, pp=p:
                                       self.show_strong(n, verse=v, pane=pp))
                        t.tag_bind(tag, '<Enter>', lambda e: t.configure(cursor='hand2'))
                        t.tag_bind(tag, '<Leave>', lambda e: t.configure(cursor='arrow'))
                        t.insert('end', val, (tag,))
                elif kind == 'fn':
                    p['fns'].append((vnum, val))  # маркеры-сноски в тексте не показываем
            t.insert('end', '\n')
            t.tag_add(f'vs{vnum}', vstart, t.index('end-2c'))
        t.insert('end', '\n')
        if p['found_verse']:  # прокрутка к стиху; жёлтая подсветка — только поиск/ссылки
            v = p['found_verse']
            mark = p['found_mark']
            p['found_verse'] = None
            p['found_mark'] = False
            try:
                if mark:
                    t.tag_add('found', f'vs{v}.first', f'vs{v}.last')
                t.see(f'vs{v}.first')
            except tk.TclError:
                pass
        tag_greek(t, self.app.theme()['greek'])
        t.configure(state='disabled')
        self._refresh_pane_header(p)

    def render_all(self):
        for p in self.panes:
            self._render_pane(p)
        self._set_title()

    def _set_title(self):
        p = self.panes[self.active_idx]
        short = p['module'].books[p['book_idx']][1].replace(chr(0x200A), ' ')
        self.top.title(f'{short} {p["chapter"]} — {p["module"].description}')

    # --- выделение стихов и копирование (как в MyBible) ---
    def _verse_at(self, p, event):
        v = None
        for tag in p['text'].tag_names(f'@{event.x},{event.y}'):
            if tag.startswith('vs'):
                try:
                    v = int(tag[2:])
                except ValueError:
                    pass
        return v

    def _on_text_click(self, event):
        p = self._pane_by_text[id(event.widget)]
        self._activate(p)  # клик по панели — тулбар дальше действует на неё
        self.top.focus_set()  # фокус окна — чтобы Ctrl+C шёл сюда, а не в другое окно
        v = self._verse_at(p, event)
        if v is None:
            self.clear_selection(p)
            return
        if event.state & 0x0004:  # Ctrl — добавить/убрать стих
            if v in p['selected']:
                p['selected'].discard(v)
            else:
                p['selected'].add(v)
            p['anchor'] = v
        elif event.state & 0x0001 and p['anchor'] is not None:  # Shift — диапазон
            lo, hi = sorted((p['anchor'], v))
            p['selected'] = set(range(lo, hi + 1))
        else:
            p['selected'] = {v}
            p['anchor'] = v
        self._highlight(p)
        self._show_copy_popup(event, p)

    def _highlight(self, p):
        t = p['text']
        t.tag_remove('selv', '1.0', 'end')
        for v in p['selected']:
            t.tag_add('selv', f'vs{v}.first', f'vs{v}.last')

    def clear_selection(self, p=None):
        p = p or self.panes[self.active_idx]
        p['selected'] = set()
        p['anchor'] = None
        self._highlight(p)
        p['text'].tag_remove('found', '1.0', 'end')  # Esc снимает и подсветку поиска
        self._hide_popup()

    def _show_copy_popup(self, event, p):
        self._hide_popup()
        T = self.app.theme()
        self._popup = top = tk.Toplevel(self.top)
        top.overrideredirect(True)
        top.configure(bg=T['stroke'])  # рамка 1px вокруг кнопки
        ttk.Button(top, text='Скопировать', style='Accent.TButton',
                   command=lambda: self.copy_selected(p)).pack(padx=1, pady=1)
        top.geometry(f'+{event.x_root + 8}+{event.y_root + 8}')
        top.lift()

    def _hide_popup(self):
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None

    def copy_selected(self, p=None):
        p = p or self.panes[self.active_idx]
        if not p['selected']:
            return
        texts = {}
        book_number = p['module'].books[p['book_idx']][0]
        for vnum, raw in p['module'].verses(book_number, p['chapter']):
            if vnum in p['selected']:
                texts[vnum] = note_to_plain(raw, p['module'].short_map)
        long_name = full_book_name(p['module'].books[p['book_idx']][2])  # «Послание римлянам» -> «Римлянам»
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(
            build_copy(long_name, p['chapter'], texts,
                       inline=self.app.copy_inline.get()))
        self.clear_selection(p)

    def on_copy_key(self, _=None):
        p = self.panes[self.active_idx]
        if p['selected']:
            self.copy_selected(p)
            return 'break'
        try:  # обычное текстовое выделение мышью
            sel = p['text'].selection_get()
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(sel)
        except tk.TclError:
            pass
        return 'break'

    # --- карточка номера Стронга (ссылки на другие статьи кликабельны) ---
    def _insert_strong_body(self, top, body, exclude=None):
        """Текст статьи с кликабельными номерами Стронга; с бегунком прокрутки."""
        T = self.app.theme()
        frm = tk.Frame(top, bg=T['text_bg'], highlightthickness=1,
                       highlightbackground=T['stroke'])
        frm.pack(fill='both', expand=True)
        t = tk.Text(frm, wrap='word', padx=14, pady=10, cursor='arrow', relief='flat', bd=0,
                    highlightthickness=0)
        t.configure(bg=T['text_bg'], fg=T['fg'], selectbackground=T['selv'],
                    selectforeground=T['fg'],
                    font=(self.app.font_family, self.app.font_size + 1))  # крупнее текста читалки
        sb = ttk.Scrollbar(frm, orient='vertical', command=t.yview)
        t.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        t.pack(side='left', fill='both', expand=True)
        seq = 0
        for chunk, token in split_strong_tokens(body):
            if token is None or token == exclude:
                t.insert('end', chunk)
                continue
            seq += 1
            tag = f'stk{seq}'
            t.tag_configure(tag, foreground=T['xref'], underline=True)
            t.tag_bind(tag, '<Button-1>',
                       lambda e, n=token: self.show_strong(n), add='+')
            t.tag_bind(tag, '<Enter>', lambda e: t.configure(cursor='hand2'))
            t.tag_bind(tag, '<Leave>', lambda e: t.configure(cursor='arrow'))
            t.insert('end', chunk, (tag,))
        tag_greek(t, self.app.theme()['greek'])
        t.configure(state='disabled')
        t.bind('<Button-1>', lambda e: top.focus_set(), add='+')
        return t

    def _strong_entry(self, num, verse, p):
        """Статья для номера из «Стронга по стихам»: k-й номер Стронга в стихе
        соответствует k-му слову в глоссарии стиха (порядок слов совпадает)."""
        sn = self.app.strong_notes
        if sn is None or verse is None:
            return None
        raw = p['raws'].get(verse)
        if not raw:
            return None
        order = [v for k, v, _ in parse_markup(raw) if k == 'sn']
        try:
            k = order.index(str(num))
        except ValueError:
            return None
        book_number = p['module'].books[p['book_idx']][0]
        row = next((r for r in sn.notes(book_number, p['chapter'])
                    if r[0] <= verse <= r[1]), None)
        if row is None:
            return None
        parts = re.split(r'<br\s*/?>', row[3])
        # одно слово может занимать несколько <br/>-сегментов (варианты A(qal)/B(ni)/...),
        # новое слово начинается с <b>
        entries = []
        for part in parts:
            ps = part.strip()
            if not ps:
                continue
            if ps.startswith('<b>') or not entries:
                entries.append(ps)
            else:
                entries[-1] += '\n' + ps
        return entries[k] if k < len(entries) else None

    def show_strong(self, num, verse=None, pane=None):
        p = pane or self.panes[self.active_idx]
        top = tk.Toplevel(self.top)
        top.title(f'Стронг {num}')
        top.geometry('460x320')
        top.configure(bg=self.app.theme()['window_bg'])
        body = None
        prefer = None
        if verse is not None:
            bn = p['module'].books[p['book_idx']][0]
            prefer = 'H' if bn < 470 else 'G'  # темы словарей: H=ВЗ, G=НЗ
        for dm in self.app.dictionaries:
            definition = dm.define(num, prefer)
            if definition:
                body = note_to_plain(definition, p['module'].short_map)
                break
        if body is None:
            entry = self._strong_entry(num, verse, p)
            if entry:
                body = strong_body_from_entry(entry, p['module'].short_map)
                top.title(f'Стронг {num} · {full_book_name(p["module"].books[p["book_idx"]][2])} '
                          f'{p["chapter"]}:{verse}')
        if body is None:
            body = (f'Номер Стронга: {num}\n\n'
                    'Полной статьи нет: словаря Стронга (таблица dictionaries) в папке '
                    '«module/словари» не найдено, а в «Стронге по стихам» этот номер '
                    'не сопоставлен слову текущего стиха.\n\n'
                    'Подсказка: модуль «Словарь Стронга по стихам» можно открыть '
                    'и как комментарий (кнопка «Комментарий») — там все слова стиха.')
            exclude = None  # в подсказке номера не кликабельны
        else:
            exclude = str(num)  # ссылку на сам номер не делаем
        wrap = ttk.Frame(top, padding=(10, 8, 10, 4))
        wrap.pack(fill='both', expand=True)
        txt = self._insert_strong_body(wrap, body, exclude=exclude)
        ttk.Button(top, text='Закрыть', command=top.destroy).pack(pady=(2, 10))

        def _copy():
            try:
                sel = txt.selection_get()
            except tk.TclError:
                return
            top.clipboard_clear()
            top.clipboard_append(sel)
        self.app.reg_copy(top, _copy)
        top.bind('<Destroy>', lambda e: self.app.unreg_copy(top))
        top.transient(self.top)

    # --- один стих во всех переводах (Ctrl+двойной клик) ---
    def _on_compare_click(self, event):
        p = self._pane_by_text[id(event.widget)]
        v = self._verse_at(p, event)
        if v is not None:
            self.show_comparison(v, pane=p)

    def show_comparison(self, verse, pane=None):
        """Один и тот же стих во всех переводах подряд (карточка с бегунком)."""
        p = pane or self.panes[self.active_idx]
        book_number, _short, long_name = p['module'].books[p['book_idx']]
        T = self.app.theme()
        top = tk.Toplevel(self.top)
        top.title(f'{full_book_name(long_name)} {p["chapter"]}:{verse} — сравнение переводов')
        top.geometry('560x420')
        top.configure(bg=T['window_bg'])
        top.transient(self.top)
        frame = ttk.Frame(top, padding=(12, 8, 12, 8))
        frame.pack(fill='both', expand=True)
        frm = tk.Frame(frame, bg=T['text_bg'], highlightthickness=1,
                       highlightbackground=T['stroke'])
        frm.pack(fill='both', expand=True)
        t = tk.Text(frm, wrap='word', padx=14, pady=10, cursor='arrow', relief='flat',
                    bd=0, highlightthickness=0)
        t.configure(bg=T['text_bg'], fg=T['fg'], selectbackground=T['selv'],
                    selectforeground=T['fg'], font=(self.app.font_family, self.app.font_size))
        sb = ttk.Scrollbar(frm, orient='vertical', command=t.yview)
        t.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        t.pack(side='left', fill='both', expand=True)
        t.tag_configure('h', font=(self.app.font_family, self.app.font_size, 'bold'),
                        foreground=T['accent'], spacing1=8)
        for m in self.app.translations:
            row = next((r for r in m.verses(book_number, p['chapter'])
                        if r[0] == verse), None)
            if row is None:  # перевода книги нет или стих не совпал
                continue
            t.insert('end', m.description + '\n', ('h',))
            t.insert('end', note_to_plain(row[1], m.short_map) + '\n\n')
        tag_greek(t, self.app.theme()['greek'])
        t.configure(state='disabled')
        ttk.Button(top, text='Закрыть', command=top.destroy).pack(pady=(0, 10))
        t.bind('<Button-1>', lambda e: top.focus_set(), add='+')

        def _copy():
            try:
                sel = t.selection_get()
            except tk.TclError:
                return
            top.clipboard_clear()
            top.clipboard_append(sel)
        self.app.reg_copy(top, _copy)
        top.bind('<Destroy>', lambda e: self.app.unreg_copy(top))

    # --- введение к книге ---
    def show_introduction(self):
        book_number, _short, long_name = self.module.books[self.book_idx]
        intro = self.module.introduction(book_number)
        if not intro:
            messagebox.showinfo('Библия', 'В этом переводе нет введения к этой книге.',
                                parent=self.top)
            return
        show_text_window(self.app, self.top,
                         f'Введение — {full_book_name(long_name)}',
                         note_to_plain(intro, self.module.short_map))

    def open_search(self):
        sw = SearchWindow(self.app, self)
        self.app.search_windows.append(sw)
        sw.top.lift()
        return sw

    # --- навигация (действует на активную панель) ---
    def _refresh_all(self):
        p = self.panes[self.active_idx]
        p['book_idx'] = min(max(p['book_idx'], 0), len(p['module'].books) - 1)
        self.cb_trans['values'] = [m.description for m in self.app.translations]
        self.cb_trans.set(p['module'].description)
        self._set_book_button()
        self._refresh_chapters()

    def _refresh_chapters(self):
        self.btn_chap.configure(text=str(self.panes[self.active_idx]['chapter']))

    def on_trans(self, _=None):
        idx = self.cb_trans.current()
        if idx < 0:
            return
        p = self.panes[self.active_idx]
        p['module'] = self.app.translations[idx]
        if p['cb'] is not None:
            p['cb'].set(p['module'].description)
        self._refresh_all()
        self._render_pane(p)

    def open_commentary(self, comm=None):
        cw = CommentaryWindow(self.app, self, comm)
        self.comm_windows.append(cw)
        return cw

    # --- переход плитками: книги -> главы -> стихи (как в MyBible) ---
    def _set_book_button(self):
        self.btn_book.configure(text=full_book_name(self.module.books[self.book_idx][2]))

    def open_books(self, pane=None):
        """Окно перехода в три шага: плитки книг по разделам -> плитки глав ->
        плитки стихов. Выбор стиха закрывает окно и открывает отрывок в читалке
        с прокруткой к этому стиху."""
        p = pane or self.panes[self.active_idx]
        T = self.app.theme()
        top = tk.Toplevel(self.top)
        top.title('Переход')
        top.configure(bg=T['window_bg'])
        top.transient(self.top)
        top.geometry(f'560x640+{self.top.winfo_rootx() + 60}+{self.top.winfo_rooty() + 30}')
        head = ttk.Frame(top, padding=(12, 8, 12, 0))
        head.pack(fill='x')
        btn_back = ttk.Button(head, text='←', width=3, style='Tool.TButton')
        btn_back.pack(side='left')
        lbl = tk.Label(head, text='', bg=T['window_bg'], fg=T['fg2'], anchor='w',
                       font=(self.app.ui_family, UI_FONT_SIZE, 'bold'))
        lbl.pack(side='left', padx=(8, 0))
        cv = tk.Canvas(top, bg=T['window_bg'], highlightthickness=0)
        sb = ttk.Scrollbar(top, orient='vertical', command=cv.yview)
        inner = tk.Frame(cv, bg=T['window_bg'])
        slot = cv.create_window((0, 0), window=inner, anchor='nw')
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        cv.pack(side='left', fill='both', expand=True)
        top.bind('<MouseWheel>',
                 lambda e: cv.yview_scroll(-1 if e.delta > 0 else 1, 'units'))
        top.bind('<Escape>', lambda e: top.destroy())

        def _fit(_):
            cv.configure(scrollregion=cv.bbox('all'))
            cv.itemconfigure(slot, width=cv.winfo_width())
        inner.bind('<Configure>', _fit)
        cv.bind('<Configure>', lambda e: cv.itemconfigure(slot, width=cv.winfo_width()))

        def _cols(n):
            for c in range(8):
                if c < n:
                    inner.grid_columnconfigure(c, uniform='g', weight=1)
                else:
                    inner.grid_columnconfigure(c, uniform='', weight=0)

        def _clear():
            for w in inner.winfo_children():
                w.destroy()

        def _scroll_to(btn):
            if btn is not None:  # текущая плитка — в поле зрения
                top.update_idletasks()
                cv.yview_moveto(max(btn.winfo_y() - 60, 0) / max(inner.winfo_height(), 1))

        def show_books():
            _clear()
            _cols(6)
            lbl.configure(text='Книги')
            btn_back.configure(state='disabled', command=None)
            cur = p['module'].books[p['book_idx']][0]
            covered = set()
            cur_btn = None
            for title, nums in BOOK_SECTIONS:
                covered |= nums
                btn = self._book_section(inner, T, title,
                                         [(i, b) for i, b in enumerate(p['module'].books)
                                          if b[0] in nums], cur, show_chapters)
                cur_btn = cur_btn or btn
            rest = [(i, b) for i, b in enumerate(p['module'].books) if b[0] not in covered]
            if rest:  # апокрифы и прочее вне стандартных разделов
                btn = self._book_section(inner, T, 'Прочее', rest, cur, show_chapters)
                cur_btn = cur_btn or btn
            _scroll_to(cur_btn)

        def show_chapters(bi):
            _clear()
            _cols(8)
            lbl.configure(text=p['module'].books[bi][1].replace('\u200a', ' '))
            btn_back.configure(state='normal', command=show_books)
            n = self._max_chapter(p['module'], bi)
            cur = p['chapter'] if bi == p['book_idx'] else None
            self._tiles(inner, T, [(i, str(i)) for i in range(1, n + 1)],
                        cur, lambda ch: show_verses(bi, ch))
            cv.yview_moveto(0)  # главы всегда с первой, к текущей листаем сами

        def show_verses(bi, ch):
            _clear()
            _cols(8)
            bname = p['module'].books[bi][1].replace('\u200a', ' ')
            word = p['module'].chapter_string_ps \
                if self._max_chapter(p['module'], bi) > 100 else p['module'].chapter_string
            lbl.configure(text=f'{bname} · {word.lower()} {ch}')
            btn_back.configure(state='normal', command=lambda: show_chapters(bi))
            bn = p['module'].books[bi][0]
            verses = [v for v, _raw in p['module'].verses(bn, ch)]

            def _pick(v):
                top.destroy()
                self.goto(bi, ch, verse=v, pane=p)
            self._tiles(inner, T, [(v, str(v)) for v in verses], None, _pick)
            cv.yview_moveto(0)

        show_books()
        top.grab_set()
        top.focus_set()

    def _tile(self, parent, T, label, is_cur, on_pick):
        """Одна плитка: текущая — фирменный синий, остальные — карточка с ховером."""
        bg = T['accent'] if is_cur else T['text_bg']
        fg = T['accent_text'] if is_cur else T['fg']
        btn = tk.Button(parent, text=label, relief='flat', bd=0, highlightthickness=0,
                        bg=bg, fg=fg,
                        activebackground=T['accent_hover'] if is_cur else T['hover'],
                        activeforeground=fg,
                        font=(self.app.ui_family, 9), padx=10, pady=5, cursor='hand2',
                        command=on_pick)
        if not is_cur:  # ховер у tk.Button штатного нет — подсвечиваем сами
            btn.bind('<Enter>', lambda e, b=btn: b.configure(
                bg=self.app.theme()['hover']))
            btn.bind('<Leave>', lambda e, b=btn: b.configure(
                bg=self.app.theme()['text_bg']))
        return btn

    def _book_section(self, parent, T, title, items, cur, on_book):
        """Заголовок раздела + плитки книг в 6 колонок. Возвращает кнопку текущей
        книги раздела (или None)."""
        row = parent.grid_size()[1]
        tk.Label(parent, text=title, bg=T['window_bg'], fg=T['fg2'], anchor='w',
                 font=(self.app.ui_family, UI_FONT_SIZE, 'bold')
                 ).grid(row=row, column=0, columnspan=6, sticky='we', pady=(14, 4))
        cur_btn = None
        for n, (i, (num, short, _long)) in enumerate(items):
            btn = self._tile(parent, T, short.replace('\u200a', ' '), num == cur,
                             lambda i=i: on_book(i))
            if num == cur:
                cur_btn = btn
            btn.grid(row=row + 1 + n // 6, column=n % 6, sticky='ew', padx=2, pady=2)
        return cur_btn

    def _tiles(self, parent, T, items, cur, on_pick):
        """Плитки-числа (главы, стихи) в 8 колонок. Возвращает кнопку текущей
        (или None)."""
        cur_btn = None
        for n, (val, label) in enumerate(items):
            btn = self._tile(parent, T, label, val == cur, lambda v=val: on_pick(v))
            if val == cur:
                cur_btn = btn
            btn.grid(row=n // 8, column=n % 8, sticky='ew', padx=2, pady=2)
        return cur_btn

    def goto(self, book_idx, chapter, verse=None, mark=False, propagate=True,
             history=True, pane=None):
        """Открыть главу (и промотать к стиху verse, если задан) в панели pane.
        mark=True — подсветить стих жёлтым (переходы из поиска и по ссылкам);
        обычная навигация просто проматывает. Тумблер «Синхр.» повторяет переход
        в остальных панелях этого же окна (книга — по номеру, каждый перевод
        своей нумерацией книг); независимые окна читалок не затрагиваются."""
        p = pane or self.panes[self.active_idx]
        p['book_idx'] = min(max(book_idx, 0), len(p['module'].books) - 1)
        p['chapter'] = chapter
        if verse:
            p['found_verse'] = verse
            p['found_mark'] = mark
        self._render_pane(p)
        if p is self.panes[self.active_idx]:
            self._set_book_button()
            self._refresh_chapters()
            self._set_title()
            for cw in self.comm_windows:  # окно комментария следует за активной панелью
                cw.refresh()
        bn = p['module'].books[p['book_idx']][0]
        if history:
            if p['hist_pos'] < len(p['hist']) - 1:
                del p['hist'][p['hist_pos'] + 1:]
            if p['hist'][p['hist_pos']] != (bn, p['chapter'], verse):
                p['hist'].append((bn, p['chapter'], verse))
                p['hist_pos'] = len(p['hist']) - 1
        if propagate and self.sync.get() and not self._syncing:
            for pp in self.panes:
                if pp is p:
                    continue
                bi = next((i for i, b in enumerate(pp['module'].books)
                           if b[0] == bn), None)
                if bi is None:  # в этом переводе книги нет — панель на месте
                    continue
                self._syncing = True
                try:
                    self.goto(bi, chapter, verse=verse, propagate=False,
                              history=False, pane=pp)
                finally:
                    self._syncing = False

    def goto_book(self, book_number, chapter, verse=None, mark=False):
        for i, b in enumerate(self.module.books):
            if b[0] == book_number:
                self.goto(i, chapter, verse=verse, mark=mark)
                return True
        self.top.bell()
        return False

    def _goto_ref(self, p, book_number, chapter, verse):
        bi = next((i for i, b in enumerate(p['module'].books)
                   if b[0] == book_number), p['book_idx'])
        self.goto(bi, chapter, verse=verse, history=False, pane=p)

    def history_go(self, delta):
        p = self.panes[self.active_idx]
        pos = p['hist_pos'] + delta
        if 0 <= pos < len(p['hist']):
            p['hist_pos'] = pos
            self._goto_ref(p, *p['hist'][pos])

    # --- история отрывков активной панели: клик по ⟲ — назад, зажатие — список ---
    def _hist_press(self, _e):
        self._hist_long = False
        self._hist_after = self.top.after(450, self._hist_hold)

    def _hist_hold(self):
        self._hist_after = None
        self._hist_long = True
        self.show_history()

    def _hist_release(self, _e):
        if self._hist_after is not None:  # отпустили раньше порога — короткий клик
            self.top.after_cancel(self._hist_after)
            self._hist_after = None
            self.history_go(-1)

    def show_history(self):
        p = self.panes[self.active_idx]
        top = tk.Toplevel(self.top)
        top.title('История переходов')
        top.geometry('340x480')
        top.transient(self.top)
        top.configure(bg=self.app.theme()['window_bg'])
        tree = ttk.Treeview(top, columns=('ref',), show='headings', selectmode='browse')
        tree.heading('ref', text='Отрывок')
        tree.column('ref', width=320)
        sb = ttk.Scrollbar(top, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        tree.pack(fill='both', expand=True)
        sm = p['module'].short_map
        for pos in range(len(p['hist']) - 1, -1, -1):  # свежие сверху
            bn, ch, v = p['hist'][pos]
            label = f'{sm.get(bn, str(bn))} {ch}' + (f':{v}' if v else '')
            tree.insert('', 'end', iid=str(pos), values=(label,))
        tree.selection_set(str(p['hist_pos']))
        tree.see(str(p['hist_pos']))

        def jump(_e=None):
            sel = tree.selection()
            if not sel:
                return
            p['hist_pos'] = int(sel[0])
            self._goto_ref(p, *p['hist'][p['hist_pos']])
            top.destroy()
        tree.bind('<Double-1>', jump)
        tree.bind('<Return>', jump)

    # --- синхронная прокрутка панелей одного окна ---
    def _pane_scrolled(self, p, first, last):
        """Бегунок панели + (при «Синхр.») мгновенная прокрутка остальных панелей
        окна к тому же стиху — колесо, бегунок, клавиши, всё через здесь."""
        p['sb'].set(first, last)
        if self._scroll_sync or not self.sync.get():
            return
        self._scroll_sync = True
        try:
            bn = p['module'].books[p['book_idx']][0]
            v = self._top_verse(p)
            for pp in self.panes:
                if pp is p or pp['chapter'] != p['chapter'] \
                        or pp['module'].books[pp['book_idx']][0] != bn:
                    continue  # чужая глава/книга — панель не трогаем
                if v is None or not self._scroll_to_verse(pp, v):
                    pp['text'].yview_moveto(first)
        finally:
            self._scroll_sync = False

    def _top_verse(self, p):
        """Стих у верхней границы видимой области (бинарный поиск по началам)."""
        t = p['text']
        top = t.index('@0,0')
        vs = sorted(p['raws'])
        best = None
        lo, hi = 0, len(vs) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if t.compare(f'vs{vs[mid]}.first', '<=', top):
                best, lo = vs[mid], mid + 1
            else:
                hi = mid - 1
        return best

    def _scroll_to_verse(self, p, v):
        """Прокрутить панель, чтобы стих v встал к верхнему краю."""
        t = p['text']
        try:
            t.see(f'vs{v}.first')  # грубо; пиксельная доводка ниже
            for _ in range(8):  # see лишь показывает строку, не ставит к краю
                info = t.dlineinfo(f'vs{v}.first')
                if info is None:
                    break  # окно не отображено — точнее не получится
                if abs(info[1]) <= 2:
                    break
                first, last = t.yview()
                h = t.winfo_height()
                if h <= 0 or last <= first:
                    break
                t.yview_moveto(first + info[1] * (last - first) / h)
            return True
        except tk.TclError:  # такого стиха в этой панели нет (иная нумерация)
            return False

    def step_chapter(self, step):
        p = self.panes[self.active_idx]
        bi, ch = p['book_idx'], p['chapter'] + step
        nch = self._max_chapter(p['module'], bi)
        if ch < 1:
            bi -= 1
            ch = self._max_chapter(p['module'], bi) if bi >= 0 else 1
            bi = max(bi, 0)
        elif ch > nch:
            bi += 1
            if bi >= len(p['module'].books):
                bi, ch = len(p['module'].books) - 1, nch
            else:
                ch = 1
        self.goto(bi, ch)

    def close(self):
        self.app.unreg_copy(self.top)
        for cw in list(self.comm_windows):
            cw.top.destroy()
        self.comm_windows = []
        self._hide_popup()
        self.top.destroy()

    def save_state(self):
        return {'panes': [{'module': p['module'].file_name,
                           'book': p['book_idx'], 'chapter': p['chapter']}
                          for p in self.panes],
                'active': self.active_idx,
                'sync': self.sync.get(),
                'strongs': self.strongs.get(),
                'commentaries': [cw.comm.file_name for cw in self.comm_windows if cw.comm]}


# ---------- универсальное текстовое окно (введения и пр.) ----------

def show_text_window(app, parent, title, body):
    T = app.theme()
    top = tk.Toplevel(parent)
    top.title(title)
    top.geometry('640x520')
    top.configure(bg=T['window_bg'])
    frame = ttk.Frame(top, padding=(12, 8, 12, 12))
    frame.pack(fill='both', expand=True)
    t = tk.Text(frame, wrap='word', padx=14, pady=10, cursor='arrow', relief='flat', bd=0,
                highlightthickness=1, highlightbackground=T['stroke'])
    t.configure(bg=T['text_bg'], fg=T['fg'], selectbackground=T['selv'],
                selectforeground=T['fg'])
    t.insert('1.0', body)
    tag_greek(t, app.theme()['greek'])
    t.configure(state='disabled')
    sb = ttk.Scrollbar(frame, command=t.yview)
    t.configure(yscrollcommand=sb.set)
    sb.pack(side='right', fill='y')
    t.pack(side='left', fill='both', expand=True)
    ttk.Button(top, text='Закрыть', command=top.destroy).pack(pady=(0, 10))
    t.bind('<Button-1>', lambda e: top.focus_set(), add='+')

    def _copy():
        try:
            sel = t.selection_get()
        except tk.TclError:
            return
        top.clipboard_clear()
        top.clipboard_append(sel)
    app.reg_copy(top, _copy)
    top.bind('<Destroy>', lambda e: app.unreg_copy(top))
    return top
