# -*- coding: utf-8 -*-
"""Класс App: окна, конфиг, темы, Ctrl+C, «стих из буфера»."""
import json
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter import font as tkfont

from icon import load_app_icons
from markup import inline_body
from module import install_module, load_modules
from paths import APP_VERSION, CONFIG_PATH
from reader import ReaderWindow
from refs import parse_ref, verse_block
from style import apply_fluent_style, tag_greek
from theme import DEFAULT_THEME, TEXT_FONT, THEMES, UI_FONT_SIZE, ui_font_family
from windows import DictionaryWindow, DownloadWindow, LessonWindow, NO_COMMENTARY

CTRL_KEYS = ('<Control-c>', '<Control-Cyrillic_es>', '<Control-Cyrillic_ES>',
             '<Control-Insert>')  # латиница, обе формы кириллической «с», запасная клавиша



class App:
    def __init__(self, root, translations, commentaries, dictionaries, errors):
        self.root = root
        self.translations = translations
        self.commentaries = commentaries
        self.dictionaries = dictionaries
        self.errors = errors
        # ponytail: справочник Стронга ищем по слову «стронг» в описании комментария —
        # это не словарь (dictionaries), а глоссарий по стихам; признака в схеме нет
        self.strong_notes = next(
            (c for c in commentaries if 'стронг' in c.description.lower()), None)
        self.font_size = 14
        self.windows = []
        cfg = {}
        if CONFIG_PATH.is_file():
            try:
                cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
            except Exception:
                cfg = {}
        self.font_size = cfg.get('font_size', 14)
        self.font_family = cfg.get('font_family', TEXT_FONT)
        # тема по имени; старые конфиги хранили bool dark — переводим
        name = cfg.get('theme') or ('Тёмная' if cfg.get('dark') else DEFAULT_THEME)
        self.theme_name = name if name in THEMES else DEFAULT_THEME
        self.theme_var = tk.StringVar(value=self.theme_name)
        self.copy_handlers = {}  # окно -> обработчик Ctrl+C
        self.search_windows = []
        self.tool_windows = []  # «Собрать урок», «Словарь» — закрываются при смене темы
        self.clipref_var = tk.BooleanVar(value=bool(cfg.get('clipref', False)))
        self.copy_inline = tk.BooleanVar(value=bool(cfg.get('copy_inline', False)))
        self._last_clip = None
        self._verse_popup = None
        self.ui_family = ui_font_family(root)
        self.setup_style()
        self._icon_imgs = []
        try:
            self._icon_imgs = load_app_icons()
            if self._icon_imgs:
                root.iconphoto(True, *self._icon_imgs)
        except Exception:
            self._icon_imgs = []
        for st in (cfg.get('windows') or [{}])[:8]:
            self.new_window(st)
        root.protocol('WM_DELETE_WINDOW', self.on_exit)
        root.bind_all('<Control-MouseWheel>',
                      lambda e: self.set_font(self.font_size + (1 if e.delta > 0 else -1)))
        for key in CTRL_KEYS:
            root.bind_all(key, self._on_copy_key)
        # ponytail: Windows с русской раскладкой может отдать Ctrl+с любым keysym
        # (c / Cyrillic_es / Cyrillic_ES / U0441); конкретные бинды покрывают известные,
        # общий перехват ниже ловит любой прочий вариант по keycode 67 (физическая C).
        root.bind_all('<Control-KeyPress>', self._on_ctrl_keypress)
        self.root.after(900, self._poll_clip)
        # Windows сообщает о каждой смене буфера (даже повторное копирование того же текста);
        # опрос выше остаётся запасным путём на случай, если событие не приходит
        self.root.bind_all('<<ClipboardChanged>>', lambda e: self._check_clip(force=True))

    def about(self):
        messagebox.showinfo(
            'О программе',
            f'Библия — читалка модулей MyBible (*.sqlite3)\n'
            f'Версия {APP_VERSION}\n\n'
            'Оформление: Microsoft Fluent 2\n'
            'Только стандартная библиотека Python',
            parent=self.root)

    def theme(self):
        return THEMES[self.theme_name]

    def setup_style(self):
        apply_fluent_style(self.root, self.theme(),
                           (self.ui_family, UI_FONT_SIZE))

    def set_theme(self, name):
        if name not in THEMES:
            return
        self.theme_name = name
        self.theme_var.set(name)
        self.setup_style()
        for sw in list(self.search_windows):  # окна поиска не перекрашиваются на лету
            sw.on_close()
        for tw in list(self.tool_windows):
            tw.on_close()
        for w in self.windows:
            w.top.configure(bg=self.theme()['window_bg'])
            w.apply_theme_menus()
            w.apply_fonts()
            w.render_all()
            for cw in w.comm_windows:
                cw.apply_theme()
                cw.refresh()

    def reg_copy(self, top, handler):
        self.copy_handlers[str(top)] = handler

    def unreg_copy(self, top):
        self.copy_handlers.pop(str(top), None)

    def _on_copy_key(self, event):
        """Ctrl+C уходит в окно, которому принадлежит сфокусированный виджет."""
        handler = self.copy_handlers.get(str(event.widget.winfo_toplevel()))
        if handler:
            return handler()
        return None

    def _on_ctrl_keypress(self, event):
        """Страховка: физические клавиши (Windows keycodes) в любой раскладке.
        C (67) — копирование; V/X (86/88) — вставка/вырезание: у tk стандартные
        биндинги висят на латинских keysym и в русской раскладке не срабатывают,
        поэтому для нелатинских symbols генерируем штатное виртуальное событие."""
        code = getattr(event, 'keycode', 0)
        if code in (86, 88) and (event.keysym or '').lower() not in ('v', 'x'):
            event.widget.event_generate('<<Paste>>' if code == 86 else '<<Cut>>')
            return 'break'
        if code == 67 or (event.keysym or '').lower() in ('c', 'cyrillic_es'):
            return self._on_copy_key(event)
        return None

    def new_window(self, state=None):
        master = self.root if not self.windows else tk.Toplevel(self.root)
        w = ReaderWindow(self, master, state)
        if master is not self.root:
            master.protocol('WM_DELETE_WINDOW', lambda: self.close_window(w))
        self.windows.append(w)
        return w

    def open_lesson(self):
        lw = LessonWindow(self)
        self.tool_windows.append(lw)
        lw.top.lift()
        return lw

    def open_dict(self, reader):
        dw = DictionaryWindow(self, reader)
        self.tool_windows.append(dw)
        dw.top.lift()
        return dw

    def open_download(self):
        dw = DownloadWindow(self)
        self.tool_windows.append(dw)
        dw.top.lift()
        return dw

    def strong_module(self):
        """Первый перевод с номерами Стронга в <S>-тегах (у пользователя это RST+)."""
        for m in self.translations:
            if any('<S>' in t for _, t in m.verses(m.books[0][0], 1)[:50]):
                return m
        return None

    def close_window(self, w):
        if w in self.windows:
            self.windows.remove(w)
        w.close()

    def add_module(self):
        """«+ Модуль»: выбрать файлы *.sqlite3 — тип (перевод/словарь/комментарий)
        определяется по таблицам, копируются в нужную подпапку module, список обновляется."""
        paths = filedialog.askopenfilenames(
            parent=self.root, title='Добавить модули MyBible',
            filetypes=[('Модули MyBible', '*.sqlite3 *.db'), ('Все файлы', '*.*')])
        if not paths:
            return
        labels = {'переводы': 'перевод', 'словари': 'словарь', 'комментарии': 'комментарий'}
        ok, bad = [], []
        for p in paths:
            kind, err = install_module(p)
            (ok if kind else bad).append(
                f'{Path(p).name} — {labels[kind]}' if kind else err)
        if ok:
            self.reload_modules(show_info=False)
            msg = 'Добавлено:\n' + '\n'.join(ok)
            if bad:
                msg += '\n\nНе добавлено:\n' + '\n'.join(bad)
            messagebox.showinfo('Библия', msg, parent=self.root)
        else:
            messagebox.showerror('Библия', '\n'.join(bad), parent=self.root)

    def open_passage(self, book_number, chapter, verse=None):
        """Клик по координатам (комментарий, словарь): отрывок — в новом окне
        читалки, чтобы не уводить текущее окно и следующий за ним комментарий."""
        w = self.new_window()
        w.goto_book(book_number, chapter, verse, mark=True)
        w.top.lift()
        return w

    def remove_modules(self, mods):
        """Удалить файлы модулей с диска и перезагрузить набор: панели и окна,
        сидевшие на них, переезжают на оставшиеся (remap в reload_modules).
        Последний перевод удалить нельзя — читалке не на что переключиться."""
        if not [m for m in self.translations if m not in mods]:
            messagebox.showerror('Библия', 'Нельзя удалить последний перевод.',
                                 parent=self.root)
            return False
        for m in mods:
            m.conn.close()  # Windows не даст удалить открытый файл
        bad = []
        for m in mods:
            try:
                m.path.unlink()
            except OSError as ex:
                bad.append(f'{m.file_name}: {ex}')
        # перезагрузка заменяет и объекты с уже закрытыми соединениями
        self.reload_modules(show_info=False)
        if bad:
            messagebox.showerror('Библия', 'Не удалено:\n' + '\n'.join(bad),
                                 parent=self.root)
        return not bad

    def reload_modules(self, show_info=True):
        """Перечитать папку «module» без перезапуска."""
        trans, comms, dicts, errors = load_modules()
        if not trans:
            messagebox.showerror('Библия', 'В папке «module» не осталось ни одного перевода.',
                                 parent=self.root)
            return
        self.translations, self.commentaries = trans, comms
        self.dictionaries, self.errors = dicts, errors
        self.strong_notes = next(
            (c for c in comms if 'стронг' in c.description.lower()), None)
        for w in self.windows:
            w.remap_modules(trans)
            w._refresh_all()
            w.render_all()
            w._reset_history()
            for cw in list(w.comm_windows):
                if cw.comm is None:
                    cw.cb['values'] = [NO_COMMENTARY] + [c.description for c in comms]
                    continue
                c = next((c for c in comms if c.file_name == cw.comm.file_name), None)
                if c is not None:
                    cw.comm = c
                    cw.cb['values'] = [NO_COMMENTARY] + [x.description for x in comms]
                    cw.cb.set(c.description)
                    cw.refresh()
                else:
                    cw.on_close()
        if show_info:
            messagebox.showinfo(
                'Библия',
                f'Переводов: {len(trans)}, комментариев: {len(comms)}, словарей: {len(dicts)}',
                parent=self.root)

    def apply_fonts_all(self):
        for w in self.windows:
            w.apply_fonts()
            w.render_all()
            for cw in w.comm_windows:
                cw.apply_fonts()

    def set_font(self, size):
        self.font_size = min(max(size, 8), 40)
        self.apply_fonts_all()

    def set_font_family(self, family):
        if family:
            self.font_family = family
            self.apply_fonts_all()

    def open_font_dialog(self):
        top = tk.Toplevel(self.root)
        top.title('Шрифт')
        top.configure(bg=self.theme()['window_bg'])
        top.transient(self.root)
        frm = ttk.Frame(top, padding=12)
        frm.pack()
        ttk.Label(frm, text='Гарнитура:').grid(row=0, column=0, sticky='w')
        cb = ttk.Combobox(frm, width=30, values=sorted(set(tkfont.families(self.root))))
        cb.set(self.font_family)
        cb.grid(row=0, column=1, padx=6, pady=4)
        ttk.Label(frm, text='Размер:').grid(row=1, column=0, sticky='w')
        sp = ttk.Spinbox(frm, from_=8, to=40, width=6)
        sp.set(self.font_size)
        sp.grid(row=1, column=1, sticky='w', padx=6, pady=4)
        prev = tk.Label(frm, text='Избрал вас, чтобы вы шли и приносили плод — Ин 15:16')
        prev.grid(row=2, column=0, columnspan=2, pady=8)

        def apply_(_=None):
            try:
                size = int(float(sp.get()))
            except ValueError:
                size = self.font_size
            size = min(max(size, 8), 40)
            fam = cb.get() or self.font_family
            prev.configure(font=(fam, size))
            self.set_font_family(fam)
            self.set_font(size)
        cb.bind('<Return>', apply_)
        sp.bind('<Return>', apply_)
        ttk.Button(frm, text='Применить', style='Accent.TButton',
                   command=apply_).grid(row=3, column=0, pady=6)
        ttk.Button(frm, text='Закрыть', command=top.destroy).grid(row=3, column=1, pady=6)
        return top

    def _clipref_toggled(self):
        if self.clipref_var.get():
            self._last_clip = None  # показываем и то, что уже лежит в буфере
            self._check_clip()

    def _poll_clip(self):
        try:
            self._check_clip()
        except Exception:
            pass  # ни один тик не должен рвать цепочку after
        self.root.after(900, self._poll_clip)

    def _check_clip(self, force=False):
        """Вид «Стих из буфера»: скопировали ссылку «Ин 15:13» — всплывает текст стиха.
        force — буфер точно менялся (событие <<ClipboardChanged>>): повторное копирование
        той же ссылки тоже всплывает, сравнение текста не годится."""
        try:
            txt = self.root.clipboard_get().strip()
        except tk.TclError:  # в буфере не текст (файл, картинка)
            txt = ''
        changed = force or txt != self._last_clip
        self._last_clip = txt
        # однострочка до 200 знаков: сработать на короткой ссылке, но не на скопированный
        # абзац со стихом из самой читалки (он многострочный)
        if (changed and txt and '\n' not in txt and len(txt) < 200
                and self.clipref_var.get() and self.windows):
            ref = parse_ref(txt, self.windows[0].module.books)
            if ref:
                self._show_verse_popup(*ref)

    def _show_verse_popup(self, book_number, chapter, vf, vt):
        """Карточка стиха в правом нижнем углу: перевод первого окна читалки.
        Длинный текст — в прокручиваемом поле высотой до 14 строк, за экран не уходит."""
        m = self.windows[0].module
        header, body = verse_block(m, book_number, chapter, vf, vt, peek=3)
        if not body:
            return
        if self._verse_popup is not None and self._verse_popup.winfo_exists():
            self._verse_popup.destroy()
        T = self.theme()
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)  # без рамки и без кражи фокуса
        top.configure(bg=T['stroke'])  # рамка карточки 1px
        ui = (self.ui_family, UI_FONT_SIZE)
        tk.Label(top, text=header, bg=T['text_bg'], fg=T['accent'], anchor='w',
                 font=(self.font_family, self.font_size, 'bold')
                 ).pack(fill='x', padx=16, pady=(12, 2))
        est = body.count('\n') + 1 + len(body) // 55  # примерная высота в строках
        frm = tk.Frame(top, bg=T['text_bg'])
        frm.pack(fill='x', padx=16, pady=4)
        txt = tk.Text(frm, wrap='word', width=58, height=min(max(est, 1), 14),
                      bg=T['text_bg'], fg=T['fg'], selectbackground=T['selv'],
                      selectforeground=T['fg'], relief='flat', bd=0,
                      highlightthickness=0, padx=8, pady=6, takefocus=0, cursor='arrow',
                      font=(self.font_family, max(self.font_size - 2, 9)))
        txt.insert('1.0', body)
        tag_greek(txt, self.theme()['greek'])
        txt.configure(state='disabled')
        if est > 14:
            sb = ttk.Scrollbar(frm, orient='vertical', command=txt.yview)
            txt.configure(yscrollcommand=sb.set)
            sb.pack(side='right', fill='y')
        txt.pack(side='left', fill='x', expand=True)
        top.bind('<MouseWheel>',
                 lambda e: txt.yview_scroll(-1 if e.delta > 0 else 1, 'units'))
        bar = tk.Frame(top, bg=T['text_bg'])
        bar.pack(fill='x', padx=16, pady=(2, 12))
        kw = dict(relief='flat', bd=0, padx=12, pady=4, cursor='hand2', font=ui)
        btn_copy = tk.Button(bar, text='Копировать', bg=T['accent'], fg=T['accent_text'],
                             activebackground=T['accent_hover'],
                             activeforeground=T['accent_text'], **kw)

        def _copy():
            body1 = inline_body(body) if self.copy_inline.get() else body
            self.root.clipboard_clear()
            self.root.clipboard_append(header + '\n' + body1)
            btn_copy.configure(text='Скопировано ✓')

        def _open():
            w0 = self.windows[0]
            w0.goto_book(book_number, chapter, vf or 1, mark=True)
            w0.top.lift()
            top.destroy()

        btn_copy.configure(command=_copy)
        btn_copy.pack(side='left')
        tk.Button(bar, text='Открыть в читалке', command=_open, bg=T['window_bg'],
                  fg=T['fg'], activebackground=T['hover'],
                  activeforeground=T['fg'], **kw).pack(side='left', padx=6)
        tk.Button(bar, text='Закрыть', command=top.destroy, bg=T['window_bg'],
                  fg=T['fg'], activebackground=T['hover'],
                  activeforeground=T['fg'], **kw).pack(side='right')
        top.update_idletasks()
        top.geometry(f'+{top.winfo_screenwidth() - top.winfo_width() - 24}'
                     f'+{top.winfo_screenheight() - top.winfo_height() - 56}')
        top.after(120000, top.destroy)  # авто-закрытие 2 минуты
        self._verse_popup = top

    def on_exit(self):
        try:
            cfg = {'font_size': self.font_size, 'font_family': self.font_family,
                   'theme': self.theme_name, 'clipref': self.clipref_var.get(),
                   'copy_inline': self.copy_inline.get(),
                   'windows': [w.save_state() for w in self.windows]}
            CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=1),
                                   encoding='utf-8')
        except Exception:
            pass
        self.root.destroy()  # каскадно закрывает все окна читалок и комментариев
