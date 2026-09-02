# -*- coding: utf-8 -*-
"""Самопроверка без GUI (python app/bible.py --selftest)."""
import io
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

from icon import (ICON_SIZES, icon_from_logo, make_ico, png_decode, png_encode,
                  resample_rgba)
from markup import (FN_MARKER_ONLY_RE, XREF_ANY_RE, build_copy, compress_ranges,
                    href_ref, note_to_plain, parse_markup, split_strong_tokens,
                    xref_text)
from module import install_module, install_zip, load_modules, web_catalog, web_url
from paths import LOGO_PATH, MODULE_DIR, ROOT_DIR
from refs import (BOOK_GROUPS, BOOK_SECTIONS, build_lesson, dict_search,
                  find_strong_verses, full_book_name, parse_ref, parse_refs,
                  strong_body_from_entry)
from theme import DEFAULT_THEME, THEMES



def selftest():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    segs = parse_markup('<pb/>В начале сотворил Бог небо и землю.')
    assert segs[0][0] == 'nl', segs
    assert 'В начале сотворил' in segs[1][1] and segs[1][2] == frozenset()

    # темы: именованные (Fluent-пара + пергамент/сепия/ночь/полночь), одинаковый
    # набор токенов, все значения — #RRGGBB
    assert len(THEMES) >= 6 and DEFAULT_THEME in THEMES, list(THEMES)
    keys = set(next(iter(THEMES.values())))
    assert all(set(t) == keys for t in THEMES.values()), 'темы разошлись по ключам'
    for t in THEMES.values():
        assert all(v.startswith('#') and len(v) == 7 for v in t.values()), t

    # иконка: PNG-кодек симметричен, ресемпл не подтекает фоном, ICO валиден
    rgba = bytearray(b'\x10\x9f\xd4\xff' * 256)  # 16x16 сплошной синий
    assert png_decode(png_encode(16, 16, rgba)) == (16, 16, bytes(rgba))
    assert resample_rgba(bytes(rgba), 16, 16, 4, 4) == b'\x10\x9f\xd4\xff' * 16
    ico = make_ico({16: b'x', 256: b'y'})
    assert ico[:6] == b'\x00\x00\x01\x00\x02\x00' and ico[6] == 16 and ico[22] == 0
    # синтетика: белое поле + красный прямоугольник 12x8 — фон отрезан, вписан в 256
    art = bytearray(32 * 32 * 4)
    for y in range(32):
        for x in range(32):
            o = (y * 32 + x) * 4
            art[o:o + 4] = (b'\xd0\x00\x00\xff' if 10 <= x < 22 and 10 <= y < 18
                            else b'\xff\xff\xff\xff')
    images = icon_from_logo(png_encode(32, 32, art))
    assert images and set(images) == set(ICON_SIZES)
    w2, h2, big = png_decode(images[256])
    assert (w2, h2) == (256, 256)
    assert big[3] == 0 and big[-1] == 0, 'фон не отрезан'
    opaque = sum(1 for a in big[3::4] if a > 127)  # 12x8 → 256x171 по центру
    assert 38000 < opaque < 50000, opaque
    mid = (128 * 256 + 128) * 4
    assert big[mid + 3] == 255 and big[mid] > 128, 'центр не закрашен'
    if LOGO_PATH.is_file():
        assert png_decode(LOGO_PATH.read_bytes()), 'logo2 не декодируется'

    segs = parse_markup('<pb/><e>Не используй имени Господа</e>, потому что Господь не оставит.<pb/>—————')
    assert 'ital' in segs[1][2] and 'Не используй' in segs[1][1]
    plain = [s for s in segs if s[0] == 'text' and 'потому что' in s[1]][0]
    assert plain[2] == frozenset()
    assert '—————' in segs[-1][1]

    segs = parse_markup('<pb/>Но Иисус ответил: <pb/><J>— Пусть сейчас <i>будет</i> так.</J> Тогда Иоанн согласился.')
    both = [s for s in segs if s[0] == 'text' and 'red' in s[2] and 'ital' in s[2]]
    assert both and 'будет' in both[0][1]
    after = [s for s in segs if s[0] == 'text' and 'Тогда' in s[1]][0]
    assert after[2] == frozenset()

    segs = parse_markup('<t>строка один</t><t>строка два</t>')
    texts = [s for s in segs if s[0] == 'text']
    assert len(texts) == 2 and all('poetry' in s[2] for s in texts)
    assert sum(1 for s in segs if s[0] == 'nl') >= 2

    # сноски: маркер-только из текста исчезает, содержимое уходит в 'fn'
    segs = parse_markup('землей<f>[2]</f> и над всеми пресмыкающимися')
    fns = [s for s in segs if s[0] == 'fn']
    assert len(fns) == 1 and fns[0][1] == '[2]'
    assert all('[2]' not in s[1] for s in segs if s[0] == 'text')
    assert FN_MARKER_ONLY_RE.match(note_to_plain('[2]', {}))
    # сноска-маркер вырезается и из чистого текста стиха (NRT: «…приду,<f>[143]</f> то…»)
    # — урок, попап из буфера и копирование из читалки показывают стих без «[143]»
    assert note_to_plain('пока Я не приду,<f>[143]</f> то что тебе до этого?', {}) == \
        'пока Я не приду, то что тебе до этого?'

    # перекрёстные ссылки внутри сноски -> читаемый вид
    bmap = {470: 'Мат.', 490: 'Лук.', 230: 'Пс.'}
    raw = '(<x>470 4:1-11</x>; <x>490 4:1-13</x>)'
    assert note_to_plain(raw, bmap) == '(Мат. 4:1-11; Лук. 4:1-13)', note_to_plain(raw, bmap)
    segs = parse_markup(f'См. <f>+{raw}</f> конец.')
    assert segs[1][0] == 'fn' and '470' in segs[1][1]
    assert note_to_plain(segs[1][1], bmap) == '+(Мат. 4:1-11; Лук. 4:1-13)'
    assert xref_text('470 4:1', bmap) == 'Мат. 4:1'
    assert xref_text('230 118:1-2', bmap) == 'Пс. 118:1-2'
    assert xref_text('470 4:1-5:2', bmap) == 'Мат. 4:1-5:2'

    # координаты <a href='B:…'>/<a href='C:@…'> из комментариев: имя книги в тексте
    bm2 = {470: 'Мат.', 480: 'Мар.', 510: 'Иак.'}
    raw = ("(<a href='B:470 10:2-4'>10:2-4</a>; <a class='B' href='B:480 3:13-19'>3:13-19</a>; "
           "<a href='C:@510 1:13'>1:13</a>; <a href='S:H136'>136</a>)")
    assert href_ref('B:470 10:2') == '470 10:2' and href_ref('C:@10 12:3') == '10 12:3'
    assert note_to_plain(raw, bm2) == '(Мат. 10:2-4; Мар. 3:13-19; Иак. 1:13; 136)', \
        note_to_plain(raw, bm2)
    links = list(XREF_ANY_RE.finditer(raw))
    assert len(links) == 3 and [href_ref(m.group(2)) for m in links] == \
        ['470 10:2-4', '480 3:13-19', '510 1:13']

    # Стронг: номер отдельным сегментом, в текст не клеится
    segs = parse_markup('И нарек<S>7121</S> Адам<S>120</S> имя')
    sns = [s for s in segs if s[0] == 'sn']
    assert [s[1] for s in sns] == ['7121', '120'], sns
    assert all('7121' not in s[1] for s in segs if s[0] == 'text')
    assert note_to_plain('И нарек<S>7121</S> Адам', {}) == 'И нарек Адам'

    # токены Стронга в карточках
    assert split_strong_tokens('см. H7225, G26 и 1234') == [
        ('см. ', None), ('H7225', 'H7225'), (', ', None),
        ('G26', 'G26'), (' и ', None), ('1234', '1234')]

    # статья из «Стронга по стихам»: синонимы -> кликабельные номера, ссылки -> читаемые
    entry = ("<b>אֶרֶץ</b> - земля; <i>син.</i> <a href='S:H127'>127</a> (אֲדָמָה\u200e), "
             "<a href='S:H7704'>7704</a> (שָׂדֶה\u200e).<br/>LXX: <a href='B:480 2:6'>Мк 2:6</a>")
    body = strong_body_from_entry(entry, {480: 'Мар.'})
    assert 'H127' in body and 'H7704' in body and 'земля' in body, body
    assert 'Мар. 2:6' in body and '<a' not in body and 'син.' in body, body

    # формат копирования MyBible
    assert compress_ranges([1, 2, 3, 5, 8, 11, 12, 13, 14]) == '1-3, 5, 8, 11-14'
    assert compress_ranges([7]) == '7'
    single = build_copy('От Матфея', 1, {15: 'Текст стиха'})
    assert single == 'От Матфея 1:15\n15 Текст стиха', single
    multi = build_copy('От Матфея', 1, {1: 'а', 2: 'б', 3: 'в', 10: 'г'})
    assert multi == 'От Матфея 1:1-3, 10\n1 а\n2 б\n3 в\n10 г', multi
    one_line = build_copy('От Матфея', 1, {1: 'а', 2: 'б\nв'}, inline=True)
    assert one_line == 'От Матфея 1:1-2\n1 а 2 б в', one_line  # перенос внутри стиха тоже в пробел

    # разделы плиток книг: канонический порядок, без пересечений, вне заветов ничего нет
    sec_sets = [nums for _t, nums in BOOK_SECTIONS]
    joined = set().union(*sec_sets)
    assert len(BOOK_SECTIONS) == 9
    assert sum(len(s) for s in sec_sets) == len(joined), 'разделы книг пересекаются'
    assert not (joined - (BOOK_GROUPS['Ветхий Завет'] | BOOK_GROUPS['Новый Завет'])), \
        'разделы ушли за пределы заветов'

    # разбор ссылок на места Писания из произвольного текста
    fake = [(10, 'Быт.', 'Бытие'), (230, 'Пс.', 'Псалтирь'), (500, 'Ин.', 'От Иоанна'),
            (530, '1 Кор.', '1-е Коринфянам'), (730, 'Откр.', 'Откровение')]
    assert parse_ref('Ин 15:13', fake) == (500, 15, 13, 13)
    assert parse_ref('«Иоанна 15:13»', fake) == (500, 15, 13, 13)
    assert parse_ref('ин 15.13', fake) == (500, 15, 13, 13)
    assert parse_ref('Ин. 15:13-16', fake) == (500, 15, 13, 16)
    assert parse_ref('см. Ин 15:13 в тексте урока', fake) == (500, 15, 13, 13)
    assert parse_ref('Псалом 118', fake) == (230, 118, None, None)
    assert parse_ref('Пс 22', fake) == (230, 22, None, None)
    assert parse_ref('1 Кор 13:4-7', fake) == (530, 13, 4, 7)
    assert parse_ref('1Коринфянам 13', fake) == (530, 13, None, None)
    assert parse_ref('Быт 1:1-3', fake) == (10, 1, 1, 3)
    assert parse_ref('откр 3:20', fake) == (730, 3, 20, 20)
    assert parse_ref('Откровение 21:4', fake) == (730, 21, 4, 4)
    assert parse_ref('главе 15 сказано', fake) is None
    assert parse_ref('обычная строка без ссылок', fake) is None
    assert parse_ref('', fake) is None

    # таблица сокращений и формы записи
    assert parse_ref('Мф 5:3', fake) == (470, 5, 3, 3)
    assert parse_ref('Мтф 5', fake) == (470, 5, None, None)
    assert parse_ref('Мрк 5', fake) == (480, 5, None, None)
    assert parse_ref('Иона 1:4', fake) == (390, 1, 4, 4)
    assert parse_ref('Апок 21:1', fake) == (730, 21, 1, 1)
    assert parse_ref('1-Петра 2:24', fake) == (670, 2, 24, 24)
    assert parse_ref('1Петра 1:1', fake) == (670, 1, 1, 1)
    assert parse_ref('1 Петра 1:1', fake) == (670, 1, 1, 1)
    assert parse_ref('Ин глава 15 стих 13', fake) == (500, 15, 13, 13)
    assert parse_ref('Ин гл 15 ст 13', fake) == (500, 15, 13, 13)
    assert parse_ref('Пс гл. 22', fake) == (230, 22, None, None)
    assert parse_ref('Ин 15 13', fake) == (500, 15, 13, 13)  # глава и стих через пробел

    # расширенная таблица: английские аббревиатуры и дореволюционная орфография
    assert parse_ref('Jn 3:16', fake) == (500, 3, 16, 16)
    assert parse_ref('John 3:16', fake) == (500, 3, 16, 16)
    assert parse_ref('Gen 1:1', fake) == (10, 1, 1, 1)
    assert parse_ref('1Sam 17:45', fake) == (90, 17, 45, 45)
    assert parse_ref('Judg 2:1', fake) == (70, 2, 1, 1)
    assert parse_ref('Ezek 37:5', fake) == (330, 37, 5, 5)
    assert parse_ref('Phlm 4', fake) == (640, 4, None, None)
    assert parse_ref('Матѳея 5:3', fake) == (470, 5, 3, 3)
    assert parse_ref('Дѣянія 2:14', fake) == (510, 2, 14, 14)
    assert parse_ref('Екклесиаст 3:1', fake) == (250, 3, 1, 1)
    assert parse_ref('Дян 2', fake) == (510, 2, None, None)
    assert parse_ref('Песнь Песней 2:1', fake) == (260, 2, 1, 1)
    assert parse_ref('Windows 10 отлично работает', fake) is None  # латиница без ложных срабатываний

    # послания Иоанна — родительный «1Иоанна» (заголовки самого приложения), не евангелие
    assert parse_ref('1-Иоанна 4:9-10', fake) == (690, 4, 9, 10)
    assert parse_ref('1Иоанна 4:9', fake) == (690, 4, 9, 9)
    assert parse_ref('1-е Иоанна 1:1', fake) == (690, 1, 1, 1)
    assert parse_ref('2-е Иоанна 1:4', fake) == (700, 1, 4, 4)
    assert parse_ref('3-е Иоанна 1:4', fake) == (710, 1, 4, 4)
    assert parse_ref('1 Иоанна 4:9-10 — послание, не евангелие', fake) == (690, 4, 9, 10)

    # список ссылок: «; 12:1» и «, 13:5» наследуют книгу; голое число после «,» — не глава
    assert [r[2:] for r in parse_refs('Притчи 9:9; 12:1', fake)] == \
        [(240, 9, 9, 9), (240, 12, 1, 1)]
    assert [r[2:] for r in parse_refs('Притчи 9:9; 12:1, 13:5', fake)] == \
        [(240, 9, 9, 9), (240, 12, 1, 1), (240, 13, 5, 5)]
    assert [r[2:] for r in parse_refs('Притчи 9:9; 12:1-3', fake)] == \
        [(240, 9, 9, 9), (240, 12, 1, 3)]
    assert [r[2:] for r in parse_refs('Ин 15:13, 17', fake)] == [(500, 15, 13, 13)]

    # полная форма имени для заголовков карточки
    assert full_book_name('От Иоанна') == 'Иоанна'
    assert full_book_name('К Римлянам') == 'Римлянам'
    assert full_book_name('Послание римлянам') == 'Римлянам'
    assert full_book_name('1-е посл. Петра') == '1-Петра'
    assert full_book_name('3-е посл. Иоанна') == '3-Иоанна'
    assert full_book_name('1-я Царств') == '1-Царств'
    assert full_book_name('1-книга Царств') == '1-Царств'
    assert full_book_name('Песня Песней') == 'Песня Песней'
    assert full_book_name('Плач Иеремии') == 'Плач Иеремии'

    # установка модулей: тип по таблицам, файл в свою подпапку, мусор и дубли отбиваются
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        def mk(name, *tables):
            c = sqlite3.connect(td / name)
            for t in tables:
                c.execute(t)
            c.commit()
            c.close()
        mk('t.sqlite3',
           'CREATE TABLE info (name TEXT, value TEXT)',
           'CREATE TABLE books (book_number INT, short_name TEXT, long_name TEXT)',
           'CREATE TABLE verses (book_number INT, chapter INT, verse INT, text TEXT)')
        mk('c.sqlite3', 'CREATE TABLE commentaries (book_number INT)')
        mk('d.sqlite3', 'CREATE TABLE dictionaries (topic TEXT, definition TEXT)')
        mk('x.sqlite3', 'CREATE TABLE junk (a INT)')
        root = td / 'module'
        assert install_module(td / 't.sqlite3', root) == ('переводы', '')
        assert install_module(td / 'c.sqlite3', root) == ('комментарии', '')
        assert install_module(td / 'd.sqlite3', root) == ('словари', '')
        assert (root / 'переводы' / 't.sqlite3').is_file()
        k, err = install_module(td / 'x.sqlite3', root)
        assert k is None and 'не похож' in err, err
        k, err = install_module(td / 't.sqlite3', root)
        assert k is None and 'уже установлен' in err, err

    # каталог ph4.ru: разбор страницы (в т.ч. заэкранированный апостроф) и zip
    fix = ('<a href="_dl.php?back=bbl&a=NRTro&b=mybible&c" class=circle_dl></a>'
           '<td><nobr><b>NRT</b> 2023</nobr><br><span class=silver>[NRTro]</span></td>'
           '<td><div class=btl>Новый русский перевод</div></td>'
           "<a href='_dl.php?back=bbl&a=NRT\\'23&b=mybible&c' class=circle_dl></a>"
           '<td><div class=btl>Другой</div></td>')
    cat = web_catalog(fix)
    assert len(cat) == 2, cat
    assert cat[0][0] == 'NRT 2023 — Новый русский перевод', cat[0]
    assert cat[1][1].endswith("a=NRT'23&b=mybible&c"), cat[1]
    assert '%D0%94%D0%B5%D1%81%D0%BD' in \
        web_url('https://www.ph4.ru/_dl.php?back=bbl&a=Десн&b=mybible&c')
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / 't.sqlite3'
        c = sqlite3.connect(db)
        c.execute('CREATE TABLE books (book_number INT, short_name TEXT, long_name TEXT)')
        c.execute('CREATE TABLE verses (book_number INT, chapter INT, verse INT, text TEXT)')
        c.commit()
        c.close()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.write(db, 'webt.SQLite3')
            z.writestr('readme.txt', 'прочее')
        res = install_zip(buf.getvalue(), Path(td) / 'module')
        assert res == [('webt.SQLite3', 'переводы', '')], res

    if MODULE_DIR.is_dir() or (ROOT_DIR / 'переводы').is_dir():
        trans, comms, dicts, errors = load_modules()
        assert not errors, errors
        assert trans and comms, (len(trans), len(comms))
        for m in trans:
            # 66 — полный канон; VIN и пр. неполные переводы легальны (57 книг)
            assert 20 <= len(m.books) <= 66, (m.file_name, len(m.books))
        nrt = next(m for m in trans if 'NRT' in m.file_name and 'comment' not in m.file_name)
        intro = nrt.introduction(nrt.books[0][0])
        assert intro and len(intro) > 100
        nrt_comm = next(c for c in comms if 'NRT' in c.file_name)
        rows = nrt_comm.notes(10, 1)
        assert rows and any(len(note_to_plain(r[3], {})) > 10 for r in rows)
        # кэш поиска по комментариям: книги валидны, текст чистый
        cc = nrt_comm.commentary_cache({})
        assert cc, 'кэш комментариев пуст'
        assert all(10 <= b <= 730 and ch >= 0 for b, ch, _v, _p in cc)
        assert any('Быт' in p or 'Бог' in p for _b, _c, _v, p in cc)
        rst = next(m for m in trans if 'Синодальн' in m.description)
        v = rst.verses(rst.books[0][0], 1)
        assert v and all('<' not in note_to_plain(r[1], rst.short_map) for r in v)
        # группы книг для поиска покрывают каждую книгу модуля
        # (лишние номера-пустышки в диапазонах безвредны: стихей с ними нет)
        all_books = {b[0] for b in rst.books}
        covered = BOOK_GROUPS['Ветхий Завет'] | BOOK_GROUPS['Новый Завет']
        assert all_books <= covered, 'нумерация модуля не совпадает с группами книг'
        assert all_books <= joined, 'какая-то книга не попадает в раздел плиток'
        assert BOOK_GROUPS['Пятикнижие Моисея'] <= BOOK_GROUPS['Ветхий Завет']
        assert BOOK_GROUPS['Послания Павла'] <= BOOK_GROUPS['Послания'] <= BOOK_GROUPS['Новый Завет']
        ev = len([n for n in BOOK_GROUPS['Евангелия'] if n % 10 == 0])
        paul = len([n for n in BOOK_GROUPS['Послания Павла'] if n % 10 == 0])
        assert ev == 4 and paul == 14, (ev, paul)
        # поиск: индекс, регистронезависимость кириллицы
        cache = rst.search_cache()
        assert len(cache) > 30000
        hits = [r for r in cache if 'вооз' in r[3].lower()]
        assert hits and hits[0][0] == 80, hits[:1]
        # словари Стронга: грузятся, статьи ищутся с префиксом завета
        assert len(dicts) >= 4, len(dicts)
        lex = next(d for d in dicts if 'лексикон' in d.description.lower())
        assert lex.define('1', prefer='H') and 'отец' in note_to_plain(lex.define('1', prefer='H'), {})
        assert lex.define('7225', prefer='H')
        sym = next(d for d in dicts if 'Симфония' in d.description)
        sym_plain = note_to_plain(sym.define('G26', prefer='G') or '', {})
        assert '<style' not in sym_plain and '&#x' not in sym_plain and sym_plain.strip()
        # сборка урока: все ссылки из текста, разворот в цитаты с полными именами
        refs = parse_refs('Ин 15:13; Рим 5:8 и 1-Петра 2:24', rst.books)
        assert [r[2:] for r in refs] == [(500, 15, 13, 13), (520, 5, 8, 8), (670, 2, 24, 24)], refs
        lesson = build_lesson('Тема урока.\nСм. Ин 15:13 и Пс 1.', rst)
        assert 'Тема урока.' in lesson and 'Иоанна 15:13' in lesson, lesson[:200]
        assert 'любви' in lesson and 'Псалтирь 1' in lesson, lesson[:200]
        # конкорданс: стихи, где номер Стронга стоит в теге <S>
        raw0 = rst.verses(rst.books[0][0], 1)[0][1]
        sn = next((v for k, v, _ in parse_markup(raw0) if k == 'sn'), None)
        if sn:
            used = find_strong_verses(rst, sn)
            assert used and used[0][:2] == (rst.books[0][0], 1), used[:1]
        # поиск по словарям: слово в теме или тексте статьи
        hits = dict_search(dicts, 'отец')
        assert hits and all(isinstance(h[1], str) for h in hits), len(hits)
        print(f'OK: разметка + {len(trans)} перевод(а) + {len(comms)} комментария(ев) '
              f'+ {len(dicts)} словаря(ей) + поиск/введения/Стронг')
    else:
        print('OK: разметка (папка переводов не найдена, БД не проверялись)')
