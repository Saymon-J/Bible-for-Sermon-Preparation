# -*- coding: utf-8 -*-
"""GUI-проверка: строит все окна живьём — python app/bible.py --selftest-gui.

Ловит NameError/wiring после структурных правок (импорты, перенос кода между
модулями), которые не видны статике и обычному --selftest. Конфиг только
читается — on_exit не зовём, config.json не трогаем (договорённость соблюдена).
"""
import sys
import tkinter as tk
from tkinter import ttk, messagebox

import application
import module


def _walk(w):
    out = []
    for c in w.winfo_children():
        out.append(c)
        out += _walk(c)
    return out


def selftest_gui():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    trans, comms, dicts, errors = module.load_modules()
    assert trans, 'нет переводов'
    root = tk.Tk()
    root.withdraw()
    app = application.App(root, trans, comms, dicts, errors)
    w0 = app.windows[0]
    w0.top.update()

    # плитки перехода: книги -> главы -> стихи, выбор стиха открывает отрывок
    # (у неполных переводов вроде VIN книг <66)
    ch_start = w0.panes[0]['chapter']  # стартовый отрывок может быть любым (конфиг)
    w0.open_books()
    tops = [t for t in root.winfo_children() if isinstance(t, tk.Toplevel)]
    books_top = tops[-1]
    books_top.update_idletasks()
    btns = [w for w in _walk(books_top) if isinstance(w, tk.Button)]
    assert len(btns) >= len(w0.module.books), \
        f'кнопок книг {len(btns)} < книг модуля {len(w0.module.books)} — окно пустое?'
    btns[0].invoke()  # первая книга раздела «Закон» -> плитки глав
    root.update()
    chap_btns = [w for w in _walk(books_top) if isinstance(w, tk.Button)]
    assert all(b.cget('text').isdigit() for b in chap_btns) and len(chap_btns) >= 1, \
        'после книги не показались плитки глав'
    chap_btns[2].invoke()  # глава 3 -> плитки стихов
    root.update()
    verse_btns = [w for w in _walk(books_top) if isinstance(w, tk.Button)]
    assert all(b.cget('text').isdigit() for b in verse_btns) and len(verse_btns) >= 1, \
        'после главы не показались плитки стихов'
    p0 = w0.panes[0]
    verse_btns[4].invoke()  # стих 5 -> читалка на нём, без жёлтой подсветки
    root.update()
    assert not books_top.winfo_exists(), 'выбор стиха не закрыл окно перехода'
    assert p0['chapter'] == 3, 'выбор стиха не открыл главу'
    assert not p0['text'].tag_ranges('found'), 'навигация пикером подсветила стих'
    bn0 = p0['module'].books[p0['book_idx']][0]
    assert p0['hist'][-1] == (bn0, 3, 5), 'отрывок со стихом не попал в историю'

    # история: назад/вперёд (Alt+←/→), окно списка — по кнопке ⟲ зажатием
    w0.history_go(-1)
    root.update()
    assert p0['chapter'] == ch_start and p0['hist_pos'] == 0, \
        '«назад» не вернул прежний отрывок'
    w0.history_go(1)
    root.update()
    assert p0['chapter'] == 3 and p0['found_verse'] is None, \
        '«вперёд» не вернул отрывок (стих должен быть промотан и снят с подсветки)'
    assert not p0['text'].tag_ranges('found'), 'возврат по истории подсветил стих'
    w0.show_history()
    hist_top = [t for t in root.winfo_children() if isinstance(t, tk.Toplevel)][-1]
    trees = [w for w in _walk(hist_top) if isinstance(w, ttk.Treeview)]
    assert trees and len(trees[0].get_children()) == len(p0['hist']), \
        'окно истории не совпало с историей панели'
    hist_top.destroy()

    # перевод со сносками/Стронгом (RST+) — путь сноски в окне комментария
    rst = next((m for m in trans
                if '<S>' in (m.verses(m.books[0][0], 1) or [('', '')])[0][1]),
               trans[0])
    w0.cb_trans.current(trans.index(rst))
    w0.on_trans()
    w0.top.update()
    assert w0.btn_book.cget('text').strip(), 'кнопка книги пустая'
    cw = w0.open_commentary(comms[0] if comms else None)
    root.update()
    body = cw.text.get('1.0', 'end')
    assert body.strip(), 'окно комментария пустое'
    cw.on_close()

    # поиск: по переводу и по комментариям, переход по результату
    sw = w0.open_search()
    sw.entry.insert('0', 'Бог')
    sw.search()
    root.update()
    assert sw.rows, 'поиск по переводу пуст'
    sw.in_comms.set(True)
    sw.search()
    root.update()
    assert sw.rows, 'поиск по комментариям пуст'
    sw.tree.selection_set('0')
    sw.jump()
    root.update()
    assert w0.panes[0]['text'].tag_ranges('found'), \
        'переход из поиска не подсветил найденный стих'
    sw.on_close()

    # остальное: сравнение переводов, Стронг, урок, словарь, попап стиха,
    # режим чтения, шрифт, тёмная тема по живым окнам
    w0.show_comparison(1)
    w0.show_strong('430', verse=1)
    lw = app.open_lesson()
    lw.inp.insert('1.0', 'Ин 15:13')
    lw.build()
    assert 'Ссылок' in lw.status.cget('text'), 'урок не собрался'
    # Ctrl+V в русской раскладке: физическая клавиша V (keycode 86), keysym
    # «м» — синтетический keypress Tk не даёт создать, зовём обработчик напрямую
    class _FakeEv:
        keycode, keysym, widget = 86, 'Cyrillic_em', lw.inp
    lw.inp.delete('1.0', 'end')
    app.root.clipboard_clear()
    app.root.clipboard_append('Мф 1:1')
    app._on_ctrl_keypress(_FakeEv())
    root.update()
    assert 'Мф 1:1' in lw.inp.get('1.0', 'end'), 'Ctrl+V в русской раскладке не вставляет'
    dw = app.open_dict(w0)
    dw.entry.insert('0', 'G26')
    dw.search()
    root.update()
    assert dw.rows or dw.art, 'словарь ничего не нашёл'
    app._show_verse_popup(500, 15, 13, 13)
    assert app._verse_popup is not None and app._verse_popup.winfo_exists()
    w0.toggle_reading()
    root.update()
    assert w0.bar.winfo_manager() == '', 'режим чтения не спрятал тулбар'
    w0._exit_reading_or_clear()
    root.update()
    assert w0.bar.winfo_manager() == 'pack', 'выход из режима чтения не вернул тулбар'

    # узкое окно: вторичные кнопки сворачиваются в «⋯», широкое — возвращаются
    # (1600 — уже узко: у ttk-кнопок темы Windows минимальная ширина ~100px,
    # весь тулбар целиком ~1600px)
    w0._tb_relayout(1700)
    all_shown = w0._tb_shown
    assert all_shown == len(w0._tb_extra) and not w0.tb_more.winfo_manager(), \
        'в широком окне «⋯» не спрятан'
    w0._tb_relayout(620)
    root.update()
    assert w0._tb_shown < all_shown, 'узкое окно не свернуло кнопки в «⋯»'
    assert w0.tb_more.winfo_manager() == 'pack', '«⋯» не появился'
    hidden = w0._tb_extra[w0._tb_shown:]
    assert all(w.winfo_manager() == '' for w in hidden), 'свёрнутые кнопки остались в тулбаре'
    assert w0.tb_more_menu.index('end') + 1 == len(hidden), \
        'меню «⋯» не совпало с числом свёрнутых'
    w0._tb_relayout(1700)
    root.update()
    assert w0._tb_shown == all_shown and not w0.tb_more.winfo_manager(), \
        'широкое окно не вернуло кнопки из «⋯»'

    # ☰: панели чтения в одном окне (до трёх) со своими селекторами перевода,
    # ✕ закрывает панель; тумблеры 📋/⇄ — включено = зелёная рамка.
    # Тест не зависит от локального конфига: лишние панели (если были) закрываем
    while len(w0.panes) > 1:
        w0.close_pane(w0.panes[-1])
    assert len(w0.panes) == 1
    w0.split_pane()
    root.update()
    assert len(w0.panes) == 2 and w0.cb_trans.winfo_manager() == '', \
        '☰ не разделил окно или селектор перевода не переехал в шапки панелей'
    assert all(p['cb'] is not None and p['head'] is not None for p in w0.panes), \
        'у панелей нет шапки с селектором перевода'
    w0.split_pane()
    w0.split_pane()
    root.update()
    assert len(w0.panes) == 3, '☰ не остановился на трёх панелях'
    # панели независимы: навигация тулбаром действует только на активную панель
    w0.sync.set(False)  # тест не зависит от сохранённого в конфиге тумблера
    w0._activate(w0.panes[1])
    ch0 = w0.panes[0]['chapter']
    target = w0._max_chapter(w0.panes[1]['module'], w0.panes[1]['book_idx'])
    w0.goto(w0.book_idx, target)
    root.update()
    assert w0.panes[1]['chapter'] == target and w0.panes[0]['chapter'] == ch0, \
        'панели не независимы'
    assert w0.btn_chap.cget('text') == str(target), 'тулбар не следит за активной панелью'
    # у каждой панели — свои книга и глава в шапке
    assert all(p['cbtn'] is not None and p['bbtn'] is not None for p in w0.panes), \
        'в шапке панели нет выбора книги/главы'
    b2 = w0.panes[2]['book_idx']
    w0.goto(b2, 2, pane=w0.panes[2])
    root.update()
    assert w0.panes[2]['chapter'] == 2 and w0.panes[0]['chapter'] == ch0 \
        and w0.panes[1]['chapter'] == target, 'goto с панелью задел чужие панели'
    assert w0.panes[2]['cbtn'].cget('text') == '2', 'шапка панели не следит за главой'

    # тумблер «⇄»: переход и прокрутка синхронны панелям этого же окна;
    # независимое окно читалки не затрагивается. Книга — общая для переводов
    # обеих панелей (в неполных переводах нет ветхозаветных книг)
    pa, pb = w0.panes[0], w0.panes[1]
    bn = next(b[0] for b in pa['module'].books
              if any(bb[0] == b[0] for bb in pb['module'].books))
    pa_bi = next(i for i, b in enumerate(pa['module'].books) if b[0] == bn)
    w0._activate(pa)
    w0.sync.set(True)
    w0.goto(pa_bi, 2)
    root.update()
    assert pb['chapter'] == 2 and pb['module'].books[pb['book_idx']][0] == bn, \
        '«Синхр.» не повторила переход в панели этого окна'
    w1 = app.new_window()
    ch_before = w1.panes[0]['chapter']
    w0.goto(pa_bi, 3)
    root.update()
    assert pb['chapter'] == 3 and w1.panes[0]['chapter'] == ch_before, \
        'синхронизация не дошла до панели или залезла в независимое окно'
    app.close_window(w1)
    # мгновенная прокрутка: верхний стих одной панели = верхний стих другой
    # (проверка пиксельная — окно должно быть показано)
    w0.top.deiconify()
    w0.top.geometry('1700x900')
    root.update()
    assert w0._scroll_to_verse(pa, 2)
    root.update()
    assert w0._top_verse(pa) == 2 and w0._top_verse(pb) == 2, \
        f'прокрутка не синхронна: {w0._top_verse(pa)} != {w0._top_verse(pb)}'
    w0.sync.set(False)

    w0.close_pane(w0.panes[2])
    w0.close_pane(w0.panes[1])
    root.update()
    assert len(w0.panes) == 1 and w0.cb_trans.winfo_manager() == 'pack' \
        and w0.panes[0]['head'] is None, \
        '✕ не закрыл панели или тулбар не вернул селектор перевода'
    # порядок: глава → ⟲ → ☰ → ◀ ▶ → Поиск → Стронг (координаты честные только у
    # показанного окна — в свёрнутом пакер их не пересчитывает)
    w0.top.deiconify()
    w0.top.geometry('1700x900')
    w0._tb_relayout(1700)
    root.update()
    arrow_l, arrow_r = w0._tb_base[5], w0._tb_base[6]
    assert w0.btn_chap.winfo_x() < w0.btn_hist.winfo_x() < w0.btn_split.winfo_x() \
        < arrow_l.winfo_x() < arrow_r.winfo_x() < w0._tb_extra[0].winfo_x() \
        < w0._tb_extra[1].winfo_x(), \
        'порядок тулбара не «глава ⟲ ☰ ◀ ▶ Поиск Стронг»'
    w0.top.withdraw()
    # тумблер «Стих из буфера»: клик инвертирует и красит рамку в зелёный
    clip_btn = w0._tb_extra[[s[2] for s in w0._tb_specs].index('Стих из буфера')]
    app.clipref_var.set(False)
    root.update()
    assert clip_btn.cget('style').endswith('ToolFit.TButton'), 'выключенный тумблер зелёный'
    clip_btn.invoke()
    root.update()
    assert app.clipref_var.get(), 'тумблер не переключает «Стих из буфера»'
    assert clip_btn.cget('style').endswith('ToolOn.TButton'), 'включённый тумблер без зелёной рамки'
    app.clipref_var.set(False)  # синхронизация стиля через меню/трейс
    root.update()
    assert clip_btn.cget('style').endswith('ToolFit.TButton'), 'выключенный тумблер остался зелёным'
    # «Стронг» — тот же тумблер (текст, без иконки): включён = зелёная рамка
    strong_btn = w0._tb_extra[[s[2] for s in w0._tb_specs].index('Стронг')]
    strong_btn.invoke()
    root.update()
    assert w0.strongs.get() and strong_btn.cget('style') == 'ToolOn.TButton', \
        '«Стронг» не переключается или без зелёной рамки'
    strong_btn.invoke()
    root.update()
    assert not w0.strongs.get()

    fd = app.open_font_dialog()
    fd.destroy()
    # древнегреческие слова подкрашиваются в любом заполненном Text
    import style as style_mod
    probe = tk.Text(root)
    probe.insert('end', 'ἀγάπη Ἀλήθεια любовь')
    style_mod.tag_greek(probe, '#123456')
    assert len(probe.tag_ranges('grk')) == 4, 'греческие слова не размечены'
    probe.destroy()

    # модули: вкладка «Скачанные» в окне «Модули» — ставим тестовый словарь
    # и удаляем его оттуда (после удаления файл исчезает, набор перечитывается)
    import sqlite3
    import tempfile
    from pathlib import Path
    from module import install_module, MODULE_DIR
    leftover = MODULE_DIR / 'словари' / 'tmp_dict_selftest.sqlite3'
    if leftover.exists():  # огрызок упавшего прогона не должен ломать тест
        leftover.unlink()
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / 'tmp_dict_selftest.sqlite3'
        c = sqlite3.connect(db)
        c.execute('CREATE TABLE dictionaries (topic TEXT, definition TEXT)')
        c.execute("INSERT INTO dictionaries VALUES ('тест', 'тестовая статья')")
        c.commit()
        c.close()
        kind, err = install_module(db)
        assert kind == 'словари', err
    app.reload_modules(show_info=False)
    dw = app.open_download()
    root.update()
    row = next((i for i, m in enumerate(dw._inst)
                if m.file_name == 'tmp_dict_selftest.sqlite3'), None)
    assert row is not None, 'тестовый модуль не попал во вкладку «Скачанные»'
    dw.itree.selection_set(str(row))
    real_ask = messagebox.askyesno
    messagebox.askyesno = lambda *a, **k: True  # «Да» в подтверждении удаления
    try:
        dw.remove()
    finally:
        messagebox.askyesno = real_ask
    root.update()
    assert all(m.file_name != 'tmp_dict_selftest.sqlite3'
               for m in app.dictionaries), 'модуль не удалён из набора'
    assert not (MODULE_DIR / 'словари' / 'tmp_dict_selftest.sqlite3').exists(), \
        'файл модуля не удалён с диска'
    dw.on_close()

    # темы: все именованные применяются к живым окнам, стартовая возвращается
    from theme import THEMES
    start_theme = app.theme_name
    for name in THEMES:
        app.set_theme(name)
        root.update()
    app.set_theme(start_theme)
    root.update()
    root.destroy()
    print('GUI OK: переход книги→главы→стихи (главы с первой, без подсветки),'
          ' история отрывков, панели + синхр. прокрутки, подсветка из поиска,'
          ' удаление модулей, все темы, комментарий со сносками, поиск в обоих'
          ' режимах, сравнение, Стронг, урок, словарь, попап, режим чтения,'
          ' сворачивание тулбара')


if __name__ == '__main__':
    selftest_gui()
