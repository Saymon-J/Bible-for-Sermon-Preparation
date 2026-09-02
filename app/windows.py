# -*- coding: utf-8 -*-
"""Инструментальные окна: комментарий, поиск, урок, словарь."""
import re
import threading

import tkinter as tk
from tkinter import ttk, messagebox

from markup import (FN_MARKER_ONLY_RE, XREF_ANY_RE, XREF_RE, blink_text,
                    href_ref, note_to_plain, xref_text)
from module import web_catalog, web_install
from refs import (BOOK_GROUPS, SEARCH_SCOPES, build_lesson, dict_search,
                  find_strong_verses, full_book_name, parse_refs)
from style import tag_greek

NO_COMMENTARY = '(выбрать)'



class CommentaryWindow:
    """Отдельное окно с комментарием; следует за окном читалки, которое его открыло.
    Координаты (<x>, <a href='B:…'>) кликабельны — открывают отрывок в новом окне читалки."""

    def __init__(self, app, reader, comm=None):
        self.app = app
        self.reader = reader
        self.comm = None
        self._xr_seq = 0
        self.top = tk.Toplevel(app.root)
        self.top.title('Комментарий')
        self.top.geometry('560x420')
        bar = ttk.Frame(self.top, padding=(12, 7, 12, 7))
        bar.pack(fill='x')
        self.cb = ttk.Combobox(bar, state='readonly', width=44,
                               values=[NO_COMMENTARY] + [c.description for c in app.commentaries])
        self.cb.pack(side='left')
        self.cb.bind('<<ComboboxSelected>>', self.on_comm)
        self.pos_label = ttk.Label(bar, text='', style='Fg2.TLabel')
        self.pos_label.pack(side='left', padx=(12, 0))
        ttk.Separator(self.top, orient='horizontal').pack(fill='x')
        frame = ttk.Frame(self.top, padding=(12, 6, 12, 12))
        frame.pack(fill='both', expand=True)
        self.text = tk.Text(frame, wrap='word', padx=14, pady=8, takefocus=0,
                            cursor='arrow', relief='flat', bd=0, highlightthickness=1)
        sb = ttk.Scrollbar(frame, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.text.pack(fill='both', expand=True)
        self.text.bind('<Button-1>',
                       lambda e: self.top.focus_set(), add='+')  # фокус окна для Ctrl+C
        self.app.reg_copy(self.top, self._copy_selection)
        self.top.protocol('WM_DELETE_WINDOW', self.on_close)
        self.apply_theme()
        if comm is not None:
            self.set_comm(comm)
        else:
            self.cb.set(NO_COMMENTARY)

    def apply_theme(self):
        T = self.app.theme()
        self.top.configure(bg=T['window_bg'])
        self.text.configure(bg=T['text_bg'], fg=T['fg'], selectbackground=T['selv'],
                            selectforeground=T['fg'],
                            highlightbackground=T['stroke'], highlightcolor=T['stroke'])
        self.apply_fonts()

    def apply_fonts(self):
        fam, s = self.app.font_family, max(self.app.font_size - 2, 9)
        self.text.configure(font=(fam, s))
        self.text.tag_configure('nh', font=(fam, s, 'bold'))

    def set_comm(self, comm):
        self.comm = comm
        self.cb.set(comm.description)
        self.refresh()

    def on_comm(self, _=None):
        idx = self.cb.current()
        self.comm = self.app.commentaries[idx - 1] if idx > 0 else None
        self.refresh()

    def _insert_note(self, raw):
        """Текст примечания; координаты (<x>, <a href='B:…'>) — кликабельные,
        с именем книги, открывают отрывок в новом окне читалки."""
        t, pos = self.text, 0
        sm = self.reader.module.short_map
        for m in XREF_ANY_RE.finditer(raw):
            if m.start() > pos:
                t.insert('end', note_to_plain(raw[pos:m.start()], sm))
            is_x = m.group(1) is not None
            ref = m.group(1) if is_x else href_ref(m.group(2))
            label = m.group(1) if is_x else blink_text(m.group(2), m.group(3), sm)
            parsed = XREF_RE.match(ref or '')
            tag = f'xr{self._xr_seq}'
            self._xr_seq += 1
            T = self.app.theme()
            t.tag_configure(tag, foreground=T['xref'], underline=True)
            t.tag_bind(tag, '<Button-1>', lambda e, p=parsed: self.on_xref(p))
            t.tag_bind(tag, '<Enter>', lambda e: self.text.configure(cursor='hand2'))
            t.tag_bind(tag, '<Leave>', lambda e: self.text.configure(cursor='arrow'))
            if is_x:
                shown = xref_text(m.group(1), sm)
            else:
                shown = note_to_plain(label, sm)
            t.insert('end', shown, (tag,))
            pos = m.end()
        if pos < len(raw):
            t.insert('end', note_to_plain(raw[pos:], sm))

    def on_xref(self, parsed):
        if not parsed:
            return
        self.app.open_passage(int(parsed.group(1)), int(parsed.group(2)),
                              int(parsed.group(3)))

    def refresh(self):
        t = self.text
        t.configure(state='normal')
        t.delete('1.0', 'end')
        if self.comm is None:
            t.insert('end', '(выберите комментарий в списке сверху)\n')
            t.configure(state='disabled')
            self.pos_label.configure(text='')
            return
        r = self.reader
        book_number, short_name, long_name = r.module.books[r.book_idx]
        self.pos_label.configure(text=f'{full_book_name(long_name)} {r.chapter}')
        self.top.title(f'Комментарий — {self.comm.description}')
        n = 0
        for vf, vt, marker, text in self.comm.notes(book_number, r.chapter):
            rng = f'ст. {vf}' if vf >= vt else f'ст. {vf}–{vt}'
            t.insert('end', rng + (f'  {marker}' if marker else '') + '\n', ('nh',))
            self._insert_note(text)
            t.insert('end', '\n\n')
            n += 1
        for vnum, raw in r._fns:
            plain = note_to_plain(raw, r.module.short_map)
            if plain and not FN_MARKER_ONLY_RE.match(plain):
                t.insert('end', f'ст. {vnum} — прим.\n', ('nh',))
                self._insert_note(raw)
                t.insert('end', '\n\n')
                n += 1
        if not n:
            t.insert('end', '(нет примечаний к этой главе)\n')
        tag_greek(t, self.app.theme()['greek'])
        t.configure(state='disabled')

    def _copy_selection(self):
        try:
            sel = self.text.selection_get()
        except tk.TclError:
            return
        self.top.clipboard_clear()
        self.top.clipboard_append(sel)

    def on_close(self):
        self.app.unreg_copy(self.top)
        if self in self.reader.comm_windows:
            self.reader.comm_windows.remove(self)
        self.top.destroy()


# ---------- окно поиска ----------

class SearchWindow:
    def __init__(self, app, reader):
        self.app = app
        self.reader = reader
        self.rows = []
        self.top = tk.Toplevel(app.root)
        self.top.title(f'Поиск — {reader.module.description}')
        self.top.geometry('780x480')
        bar = ttk.Frame(self.top, padding=(12, 7, 12, 7))
        bar.pack(fill='x')
        self.entry = ttk.Entry(bar, width=32)
        self.entry.pack(side='left')
        self.scope = ttk.Combobox(bar, state='readonly', width=22, values=SEARCH_SCOPES)
        self.scope.current(0)
        self.scope.pack(side='left', padx=(8, 0))
        ttk.Button(bar, text='Найти', style='Accent.TButton',
                   command=self.search).pack(side='left', padx=(8, 0))
        self.in_comms = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text='по комментариям', variable=self.in_comms
                        ).pack(side='left', padx=(12, 0))
        self.status = ttk.Label(bar, text='', style='Fg2.TLabel')
        self.status.pack(side='left', padx=(10, 0))
        frm = ttk.Frame(self.top, padding=(12, 6, 12, 12))
        frm.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(frm, columns=('ref', 'text'), show='headings')
        self.tree.heading('ref', text='Место')
        self.tree.column('ref', width=150, stretch=False)
        self.tree.heading('text', text='Фрагмент')
        self.tree.column('text', width=560)
        sb = ttk.Scrollbar(frm, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.entry.bind('<Return>', lambda e: self.search())
        self.tree.bind('<Double-1>', self.jump)
        self.top.protocol('WM_DELETE_WINDOW', self.on_close)
        self.entry.focus_set()

    def _scope_filter(self):
        """(книга|None, множество книг|None) по выбранной области поиска."""
        i = self.scope.current()
        if i == 0:
            return self.reader.module.books[self.reader.book_idx][0], None
        if i >= 2:
            return None, BOOK_GROUPS[SEARCH_SCOPES[i]]
        return None, None

    def search(self):
        q = self.entry.get().strip().lower()
        if not q:
            return
        bn, books = self._scope_filter()
        if self.in_comms.get():
            self.status.configure(text='Идёт индексация комментариев…')
            self.top.update_idletasks()
            # ponytail: регистронезависимость через python lower — SQLite LIKE не умеет кириллицу
            self.rows = [(b, c, v, plain, cm.description)
                         for cm in self.app.commentaries
                         for b, c, v, plain in cm.commentary_cache(self.reader.module.short_map)
                         if q in plain.lower()
                         and (bn is None or b == bn) and (books is None or b in books)]
        else:
            self.status.configure(text='Идёт индексация перевода…')
            self.top.update_idletasks()
            cache = self.reader.module.search_cache()
            self.rows = [(b, c, v, plain, '')
                         for b, c, v, plain in cache if q in plain.lower()
                         and (bn is None or b == bn) and (books is None or b in books)]
        self.tree.delete(*self.tree.get_children())
        sm = self.reader.module.short_map
        for i, (b, c, v, plain, src) in enumerate(self.rows):
            p = plain.lower().find(q)
            frag = ('…' + plain[max(0, p - 50):p + 90] + '…') if p >= 0 else plain[:120]
            ref = f'{sm.get(b, b)} {c}:{v}' if v else f'{sm.get(b, b)} {c}'
            self.tree.insert('', 'end', iid=str(i),
                             values=((f'{src} · ' if src else '') + ref,
                                     frag.replace('\n', ' ')))
        self.status.configure(text=f'Найдено: {len(self.rows)}')

    def jump(self, _=None):
        sel = self.tree.selection()
        if not sel:
            return
        b, c, v, _plain, _src = self.rows[int(sel[0])]
        r = self.reader
        if r.goto_book(b, c, v, mark=True):
            r.top.lift()

    def on_close(self):
        if self in self.app.search_windows:
            self.app.search_windows.remove(self)
        self.top.destroy()


# ---------- окно «Модули»: скачать из каталога / удалить скачанные ----------

class DownloadWindow:
    """Вкладка «Скачать» — каталог модулей MyBible с ph4.ru: фильтр по названию,
    скачивание zip, установка всех модулей архива (тип — по таблицам, как у
    «+ Модуль»). Вкладка «Скачанные» — установленные модули, лишние удаляются."""

    def __init__(self, app):
        self.app = app
        self.rows = []
        self._inst = []  # модули по строкам вкладки «Скачанные»
        self.top = tk.Toplevel(app.root)
        self.top.title('Модули')
        self.top.geometry('760x560')
        self.top.transient(app.root)
        self.top.configure(bg=app.theme()['window_bg'])
        nb = ttk.Notebook(self.top)
        nb.pack(fill='both', expand=True)

        # --- Скачать: каталог ph4.ru ---
        tab_dl = ttk.Frame(nb, padding=(12, 7, 12, 12))
        nb.add(tab_dl, text='Скачать')
        bar = ttk.Frame(tab_dl)
        bar.pack(fill='x')
        self.entry = ttk.Entry(bar, width=28)
        self.entry.pack(side='left')
        self.entry.bind('<KeyRelease>', lambda _e: self.fill())
        ttk.Button(bar, text='Скачать', style='Accent.TButton',
                   command=self.download).pack(side='left', padx=(8, 0))
        self.status = ttk.Label(bar, text='Загрузка каталога…', style='Fg2.TLabel')
        self.status.pack(side='left', padx=(10, 0))
        frm = ttk.Frame(tab_dl)
        frm.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(frm, columns=('name',), show='headings',
                                 selectmode='extended')
        self.tree.heading('name', text='Модуль (переводы, комментарии, словари)')
        self.tree.column('name', width=700)
        sb = ttk.Scrollbar(frm, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<Double-1>', lambda _e: self.download())
        self.top.protocol('WM_DELETE_WINDOW', self.on_close)

        # --- Скачанные: установленные модули + удаление ---
        tab_in = ttk.Frame(nb, padding=(12, 7, 12, 12))
        nb.add(tab_in, text='Скачанные')
        bar2 = ttk.Frame(tab_in)
        bar2.pack(fill='x')
        ttk.Button(bar2, text='Удалить выбранные',
                   command=self.remove).pack(side='left')
        self.in_status = ttk.Label(bar2, text='', style='Fg2.TLabel')
        self.in_status.pack(side='left', padx=(10, 0))
        frm2 = ttk.Frame(tab_in)
        frm2.pack(fill='both', expand=True)
        self.itree = ttk.Treeview(frm2, columns=('kind', 'name', 'file'),
                                  show='headings', selectmode='extended')
        self.itree.heading('kind', text='Тип')
        self.itree.column('kind', width=110, stretch=False)
        self.itree.heading('name', text='Название')
        self.itree.column('name', width=380)
        self.itree.heading('file', text='Файл')
        self.itree.column('file', width=200)
        sb2 = ttk.Scrollbar(frm2, orient='vertical', command=self.itree.yview)
        self.itree.configure(yscrollcommand=sb2.set)
        sb2.pack(side='right', fill='y')
        self.itree.pack(fill='both', expand=True)
        self.refresh_installed()
        self._bg(web_catalog, self._loaded)

    def refresh_installed(self):
        """Список установленных модулей по типам (после загрузки/удаления/обновления)."""
        self._inst = []
        self.itree.delete(*self.itree.get_children())
        for kind, mods in (('перевод', self.app.translations),
                           ('комментарий', self.app.commentaries),
                           ('словарь', self.app.dictionaries)):
            for m in mods:
                self.itree.insert('', 'end', iid=str(len(self._inst)),
                                  values=(kind, m.description, m.file_name))
                self._inst.append(m)
        self.in_status.configure(text=f'Модулей: {len(self._inst)}')

    def remove(self):
        sel = self.itree.selection()
        if not sel:
            return
        mods = [self._inst[int(s)] for s in sel]
        if not messagebox.askyesno(
                'Библия', 'Удалить файлы модулей?\n'
                + '\n'.join(m.file_name for m in mods), parent=self.top):
            return
        if self.app.remove_modules(mods):
            self.in_status.configure(text='Удалено')
        self.refresh_installed()

    def _loaded(self, rows, err):
        if err is not None:
            self.status.configure(text='Нет связи с сайтом')
            messagebox.showerror(
                'Библия', f'Не удалось получить каталог ph4.ru:\n{err}', parent=self.top)
            return
        self.rows = rows
        self.status.configure(text=f'Модулей: {len(rows)}')
        self.fill()

    def fill(self):
        q = self.entry.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        for i, (label, _url) in enumerate(self.rows):
            if not q or q in label.lower():
                self.tree.insert('', 'end', iid=str(i), values=(label,))

    def download(self):
        sel = self.tree.selection()
        if not sel:
            return
        chosen = [self.rows[int(s)] for s in sel]
        self.status.configure(text=f'Скачивание ({len(chosen)})…')

        def fetch():
            out = []
            for label, url in chosen:
                try:
                    out.append((label, web_install(url)))
                except Exception as ex:
                    out.append((label, [('', None, str(ex))]))
            return out
        self._bg(fetch, self._done)

    def _done(self, results, _err):
        lines, added = [], False
        for label, res in results:
            for fname, kind, err in res:
                if kind:
                    added = True
                    lines.append(f'{label}: +{fname} ({kind})')
                else:
                    lines.append(f'{label}: {err or fname}')
        if added:
            self.app.reload_modules(show_info=False)
            self.refresh_installed()
        self.status.configure(text='Готово')
        messagebox.showinfo('Библия', '\n'.join(lines) or 'Ничего не скачано',
                            parent=self.top)

    def _bg(self, fn, done):
        """fn — в фоновом потоке (сеть), done(ok, err) — в главном:
        виджеты tkinter из потока трогать нельзя."""

        def run():
            try:
                box['ok'] = fn()
            except Exception as ex:
                box['err'] = ex
        box = {}
        threading.Thread(target=run, daemon=True).start()

        def poll():
            if not box:
                self.top.after(150, poll)
            else:
                done(box.get('ok'), box.get('err'))
        poll()

    def on_close(self):
        if self in self.app.tool_windows:
            self.app.tool_windows.remove(self)
        self.top.destroy()


# ---------- окно «Собрать урок» ----------

class LessonWindow:
    """Текст со ссылками -> текст, где каждая ссылка развёрнута в цитату
    (перевод первого окна). Результат копируется в буфер одним кликом."""

    def __init__(self, app):
        self.app = app
        self.top = tk.Toplevel(app.root)
        self.top.title('Собрать урок')
        self.top.geometry('720x560')
        self.top.transient(app.root)
        self._build_ui()
        self.apply_theme()
        app.reg_copy(self.top, self._copy_selection)
        self.top.protocol('WM_DELETE_WINDOW', self.on_close)

    def _build_ui(self):
        T = self.app.theme()
        bar = ttk.Frame(self.top, padding=(12, 7, 12, 7))
        bar.pack(fill='x')
        ttk.Label(bar, text='Вставьте текст со ссылками (Ин 15:13, 1-Петра 2:24, Пс 22…) — '
                            'каждая разворачивается в цитату:').pack(side='left')
        frm_in = ttk.Frame(self.top, padding=(12, 4, 12, 4))
        frm_in.pack(fill='both', expand=True)
        self.inp = tk.Text(frm_in, wrap='word', height=6, padx=10, pady=8, relief='flat',
                           bd=0, highlightthickness=1, highlightbackground=T['stroke'])
        sbi = ttk.Scrollbar(frm_in, orient='vertical', command=self.inp.yview)
        self.inp.configure(yscrollcommand=sbi.set)
        sbi.pack(side='right', fill='y')
        self.inp.pack(fill='both', expand=True)
        bar2 = ttk.Frame(self.top, padding=(12, 4, 12, 4))
        bar2.pack(fill='x')
        ttk.Button(bar2, text='Собрать', style='Accent.TButton',
                   command=self.build).pack(side='left')
        self.btn_copy = ttk.Button(bar2, text='Копировать результат',
                                   command=self.copy, state='disabled')
        self.btn_copy.pack(side='left', padx=6)
        self.status = ttk.Label(bar2, text='', style='Fg2.TLabel')
        self.status.pack(side='left', padx=8)
        frm_out = ttk.Frame(self.top, padding=(12, 4, 12, 12))
        frm_out.pack(fill='both', expand=True)
        self.out = tk.Text(frm_out, wrap='word', padx=10, pady=8, takefocus=0,
                           relief='flat', bd=0, highlightthickness=1,
                           highlightbackground=T['stroke'])
        sbo = ttk.Scrollbar(frm_out, orient='vertical', command=self.out.yview)
        self.out.configure(yscrollcommand=sbo.set)
        sbo.pack(side='right', fill='y')
        self.out.pack(fill='both', expand=True)

    def apply_theme(self):
        T = self.app.theme()
        self.top.configure(bg=T['window_bg'])
        for t in (self.inp, self.out):
            t.configure(bg=T['text_bg'], fg=T['fg'], selectbackground=T['selv'],
                        selectforeground=T['fg'],
                        highlightbackground=T['stroke'], highlightcolor=T['stroke'],
                        font=(self.app.font_family, self.app.font_size))

    def build(self):
        if not self.app.windows:
            return
        m = self.app.windows[0].module
        src = self.inp.get('1.0', 'end-1c')
        refs = parse_refs(src, m.books)
        result = build_lesson(src, m, inline=self.app.copy_inline.get())
        self.out.configure(state='normal')
        self.out.delete('1.0', 'end')
        self.out.insert('1.0', result)
        tag_greek(self.out, self.app.theme()['greek'])
        self.out.configure(state='disabled')
        self.status.configure(text=f'Ссылок: {len(refs)}')
        self.btn_copy.configure(state='normal' if result.strip() else 'disabled')

    def copy(self):
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(self.out.get('1.0', 'end-1c'))
        self.status.configure(text='Скопировано в буфер')

    def _copy_selection(self):
        try:
            sel = self.inp.selection_get() if self.top.focus_get() is self.inp \
                else self.out.selection_get()
        except tk.TclError:
            return
        self.top.clipboard_clear()
        self.top.clipboard_append(sel)

    def on_close(self):
        self.app.unreg_copy(self.top)
        if self in self.app.tool_windows:
            self.app.tool_windows.remove(self)
        self.top.destroy()


# ---------- окно «Словарь» ----------

class DictionaryWindow:
    """Поиск по словарям. Слово -> статьи, где оно встречается.
    Номер Стронга (G26, H7225, 7225) -> статья + все стихи перевода,
    где номер стоит в теге <S> (конкорданс, как в MyBible)."""

    def __init__(self, app, reader):
        self.app = app
        self.reader = reader
        self.mode = None
        self.rows = []   # strong: [(книга, глава, стих), ...]
        self.hits = []   # слово: [(словарь, тема), ...]
        self.art = None
        self.top = tk.Toplevel(app.root)
        self.top.title('Словарь')
        self.top.geometry('760x540')
        self.top.transient(app.root)
        self.top.configure(bg=app.theme()['window_bg'])
        bar = ttk.Frame(self.top, padding=(12, 7, 12, 7))
        bar.pack(fill='x')
        self.entry = ttk.Entry(bar, width=24)
        self.entry.pack(side='left')
        self.entry.bind('<Return>', lambda e: self.search())
        ttk.Button(bar, text='Найти', style='Accent.TButton',
                   command=self.search).pack(side='left', padx=(8, 0))
        self.status = ttk.Label(bar, text='слово или номер Стронга (G26, H7225)',
                                style='Fg2.TLabel')
        self.status.pack(side='left', padx=(10, 0))
        body = ttk.Frame(self.top)
        body.pack(fill='both', expand=True)
        frm_tree = ttk.Frame(body, padding=(12, 6, 4, 12))
        frm_tree.pack(side='left', fill='both', expand=True)
        self.tree = ttk.Treeview(frm_tree, columns=('src', 'topic'), show='headings')
        self.tree.heading('src', text='Источник')
        self.tree.column('src', width=280, stretch=False)
        self.tree.heading('topic', text='Тема / место')
        self.tree.column('topic', width=380)
        sbr = ttk.Scrollbar(frm_tree, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sbr.set)
        sbr.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<Double-1>', self.activate)
        self.art_frame = ttk.Frame(body, padding=(4, 6, 12, 12))
        self.art_frame.pack(side='left', fill='both', expand=True)
        app.reg_copy(self.top, self._copy_selection)
        self.top.protocol('WM_DELETE_WINDOW', self.on_close)
        self.entry.focus_set()

    def search(self):
        q = self.entry.get().strip()
        if not q:
            return
        if re.fullmatch(r'[GHgh]?\d{1,5}', q):
            self._strong(q)
        else:
            self._word(q)

    def _fill_tree(self, rows):
        self.tree.delete(*self.tree.get_children())
        for i, (src, topic) in enumerate(rows):
            self.tree.insert('', 'end', iid=str(i), values=(src, topic))

    def _strong(self, q):
        num = q.lstrip('GHgh')
        # темы словарей с префиксом завета: G26/H7225; для голого номера пробуем оба
        prefs = [q[0].upper()] if q[:1].lower() in ('g', 'h') else ['G', 'H']
        body = None
        for dm in self.app.dictionaries:
            for p in prefs:
                definition = dm.define(num, p)
                if definition:
                    body = note_to_plain(definition, self.reader.module.short_map)
                    break
            if body:
                break
        self._show_article(body or f'Статья для номера {q} в словарях не найдена.')
        sm = self.app.strong_module()
        self.rows = find_strong_verses(sm, num) if sm else []
        self.mode = 'strong'
        self._fill_tree([(sm.description, f'{sm.short_map.get(b, b)} {c}:{v}')
                         for b, c, v in self.rows])
        self.status.configure(text=f'Стихов с номером {q}: {len(self.rows)}'
                                  + ('' if sm else ' (нет перевода со Стронгом)'))

    def _word(self, q):
        self.status.configure(text='Идёт поиск по словарям…')
        self.top.update_idletasks()
        self.hits = dict_search(self.app.dictionaries, q)
        self.mode = 'word'
        self._fill_tree([(dm.description, topic) for dm, topic in self.hits])
        self.status.configure(text=f'Статей: {len(self.hits)}')

    def _show_article(self, body):
        if self.art is not None:
            self.art.master.destroy()  # фрейм-обёртка с текстом и бегунком
        self.art = self.reader._insert_strong_body(self.art_frame, body)

    def activate(self, _=None):
        sel = self.tree.selection()
        if not sel:
            return
        i = int(sel[0])
        if self.mode == 'strong':
            b, c, v = self.rows[i]
            self.app.open_passage(b, c, v)
        else:
            dm, topic = self.hits[i]
            definition = dm.define(topic) or ''
            self._show_article(note_to_plain(definition, self.reader.module.short_map))

    def _copy_selection(self):
        if self.art is None:
            return
        try:
            sel = self.art.selection_get()
        except tk.TclError:
            return
        self.top.clipboard_clear()
        self.top.clipboard_append(sel)

    def on_close(self):
        self.app.unreg_copy(self.top)
        if self in self.app.tool_windows:
            self.app.tool_windows.remove(self)
        self.top.destroy()
