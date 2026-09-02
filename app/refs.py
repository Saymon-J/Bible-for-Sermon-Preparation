# -*- coding: utf-8 -*-
"""Ссылки на места Писания («Ин 15:13») и группы книг."""
import re

from markup import inline_body, note_to_plain, xref_text



# Русские сокращения книг (нумерация 10–730, единая во всех модулях пользователя).
# Точки нормализацией убираются — «Флп.» и «Флп» один ключ. Рискованные омоформы
# («на», «из», «нм») выброшены: слишком частые предлоги дают ложные срабатывания.
def _rng(a, b):
    return set(range(a, b + 1))


# Группы книг для области поиска (нумерация 10–730, единая во всех модулях пользователя;
# пропуски вроде 170/180 не мешают — стихей с такими номерами нет)
BOOK_GROUPS = {
    'Ветхий Завет': _rng(10, 460),
    'Пятикнижие Моисея': _rng(10, 50),
    'Исторические книги': _rng(60, 160) | {190},
    'Поэтические книги': _rng(220, 260),
    'Пророки': {290, 300, 310, 330, 340} | _rng(350, 460),
    'Большие пророки': {290, 300, 310, 330, 340},
    'Малые пророки': _rng(350, 460),
    'Новый Завет': _rng(470, 730),
    'Евангелия': _rng(470, 500),
    'Деяния': {510},
    'Послания': _rng(520, 720),
    'Послания Павла': _rng(520, 650),  # Римляне — Евреям (русская традиция включает Евр)
}
SEARCH_SCOPES = ['Текущая книга', 'Вся Библия'] + list(BOOK_GROUPS)

# Разделы для окна выбора книг плитками (порядок канонический; множества берём
# из BOOK_GROUPS, чтобы не плодить вторую нумерацию)
BOOK_SECTIONS = [
    ('Закон', BOOK_GROUPS['Пятикнижие Моисея']),
    ('История', BOOK_GROUPS['Исторические книги']),
    ('Псалмы и премудрость', BOOK_GROUPS['Поэтические книги']),
    ('Большие пророки', BOOK_GROUPS['Большие пророки']),
    ('Малые пророки', BOOK_GROUPS['Малые пророки']),
    ('Евангелия', BOOK_GROUPS['Евангелия']),
    ('Деяния', BOOK_GROUPS['Деяния']),
    ('Послания', BOOK_GROUPS['Послания']),
    ('Пророчество', {730}),
]



BOOK_ABBRS = {
    10: 'Ge Gen Gn Бт Быт Бытие Бытй', 20: 'Ex Exo Exod Исх Исхд Исход Исхт',
    30: 'Le Lev Lv Лвт Ле Лев Левит Левиты', 40: 'Nm Nu Num Чи Чис Числ Числа Чсл',
    50: 'De Deut Dt Вт Втор Второз Второзаконие Втр',
    60: 'Jos Josh Jsh ИисНав ИНав Нав Навина',
    70: 'Jdg Jdgs Judg Сд Суд Судеи Судей', 80: 'Rth Ru Ruth Руф Руфи Руфь Рф',
    90: '1S 1 Sa 1Sam 1Ц 1Цар 1Царств 1Цр', 100: '2S 2 Sa 2Sam 2Ц 2Цар 2Царств 2Цр',
    110: '1K 1Kgs 1 Ki 3Ц 3Цар 3Царств 3Цр', 120: '2K 2Kgs 2 Ki 4Ц 4Цар 4Царств 4Цр',
    130: '1Ch 1Chr 1Chron 1Лет 1П 1Пар 1Парал 1Паралип 1Паралипоменон 1Пр',
    140: '2Ch 2Chr 2Chron 2Лет 2П 2Пар 2Парал 2Паралип 2Паралипоменон 2Пр',
    150: 'Ez Ezr Ezra Ез Езд Ездр Ездра Ездры', 160: 'Ne Neh Нее Неем Неемия Неемя Нм',
    190: 'Es Est Esth Есф Есфирь Эсф Эсфирь',
    220: 'Jb Job Ив Иов Иова', 230: 'Ps Psa Pss Пс Псал Псалм Псалмы Псалом Псалтирь Псл',
    240: 'Pr Prov Prv Прит Притч Притчи Прт Прч',
    250: 'Ecc Eccl Qoh Екк Еккл Екклесиаст Эккл Экклезиаст',
    260: 'Sng Song Sos Песн Песни Песни Песней ПеснПесней Песнь Песней Пп',
    290: 'Is Isa Isai Ис Иса Исаии Исаия', 300: 'Je Jer Jr Иер Иерем Иеремии Ир',
    310: 'La Lam Lm Пл Плач Плача Плач Иеремии ПлИер',
    330: 'Eze Ezek Ezk Иез Иезек Иезекииль Иезк', 340: 'Da Dan Dn Дан Даниил Даниила Дн',
    350: 'Ho Hos Hs Ос Осии Осия', 360: 'Jl Joe Joel Ил Иоил Иоиль Иоиля',
    370: 'Am Amos Ам Амос Амоса Амс', 380: 'Ob Obad Obd Авд Авдий Авдия',
    390: 'Jnh Jon Jonah Ион Иона Ионы', 400: 'Mc Mi Mic Мих Михеи Михея Мх',
    410: 'Na Nah Наум Наума', 420: 'Hab Hk Авв Аввак Аввакума Аввк',
    430: 'Zep Zeph Zp Соф Софонии Софония Сф', 440: 'Hag Hg Аг Агг Аггей Аггея',
    450: 'Zc Zec Zech Зах Захарии Захария Зх', 460: 'Mal Ml Мал Малахии Малахия Мл',
    470: 'Mat Matt Matthew Mt Mth Мат Матф Матфея Матѳея Мт Мтф Мф',
    480: 'Mar Mark Mk Mr Mrk Мар Марк Марка Марко Мк Мр Мрк',
    490: 'Lk Lke Lu Luk Luke Лк Лук Лука Луки',
    500: 'Jhn Jn Joh John Ин Иоа Иоан Иоанн Иоанна Іоаннъ',
    510: 'Ac Act Acts Дея Деян Деяния Дя Дян Дѣянія',
    520: 'Rm Ro Rom Romans Ри Рим Римл Римлянам Рм',
    530: '1Co 1Cor 1Кор 1Коринф 1Коринфянам 1Кр 1Крины',
    540: '2Co 2Cor 2Кор 2Коринф 2Коринфянам 2Кр 2Крины',
    550: 'Ga Gal Gl Га Гал Галат Галатам Глт', 560: 'Ep Eph Еф Ефе Ефес Ефесян Ефесянам Ефс',
    570: 'Ph Phil Php Филип Филипп Филиппийцам Фл Флп Флпн',
    580: 'Co Col Кл Ко Кол Колос Колоссянам',
    590: '1Th 1Thes 1Thess 1Сол 1Солун 1Солунянам 1Фес 1Фесс 1Фессал 1Фессалоникийцам',
    600: '2Th 2Thes 2Thess 2Сол 2Солун 2Солунянам 2Фес 2Фесс 2Фессал 2Фессалоникийцам',
    610: '1Ti 1Tim 1Tm 1Ти 1Тим 1Тимоф 1Тимофею 1Тм', 620: '2Ti 2Tim 2Tm 2Ти 2Тим 2Тимоф 2Тимофею 2Тм',
    630: 'Ti Tit Titus Tt Ти Тит Титу Тт', 640: 'Phlm Phm Филим Филимону Флм Флмон',
    650: 'Hb He Heb Ев Евр Евреям Еврл Еврм', 660: 'Jam Jas Jm Иа Иак Иаков Иакова Ик',
    670: '1Pe 1Pet 1Pt 1Пе 1Пет 1Петр 1Петра 1Пт', 680: '2Pe 2Pet 2Pt 2Пе 2Пет 2Петр 2Петра 2Пт',
    # родительный «1Иоанна» обязателен: это форма из собственных заголовков приложения
    690: '1Jn 1Jo 1Joh 1John 1Ин 1Ио 1Иоан 1Иоанн 1Иоанна 1Ион',
    700: '2Jn 2Jo 2Joh 2John 2Ин 2Ио 2Иоан 2Иоанн 2Иоанна 2Ион',
    710: '3Jn 3Jo 3Joh 3John 3Ин 3Ио 3Иоан 3Иоанн 3Иоанна 3Ион',
    720: 'Jd Jud Jude Ид Иуд Иуда Иуды', 730: 'Re Rev Rv Апок Отк Откр Откровение Откровения',
}

# книга (цифра может быть через пробел, слитно или с тире: «1 Петра», «1Петра», «1-Петра»;
# имя — кириллица или латиница, допускается дореволюционная орфография ѣ/ѳ/і/ъ),
# глава, стих (через : . или пробел), необязательный диапазон стихов
REF_RE = re.compile(
    r'((?:[1-9][\s-]*)?[А-ЯЁа-яёA-Za-zѢѣѲѳІі]+(?:\s+[А-ЯЁа-яёA-Za-zѢѣѲѳІі]+)*)'
    r'[\s.]*(\d{1,3})((?:\s*[:.]\s*|\s+)(\d{1,3}))?(?:\s*[-–]\s*(\d{1,3})(?!:?\d))?')

# «глава/гл/стих/ст» — служебные слова, из имени книги убираются до разбора
KEYWORD_RE = re.compile(r'\b(?:глава|гл|стих|ст)\b\.?\s*', re.IGNORECASE)

# продолжение списка ссылок: «Притчи 9:9; 12:1» — после «;»/«,» новая глава:стих той же
# книги. Двоеточие обязательно: голое «, 17» после «Ин 15:13» — стих той же главы,
# а не глава, и не разворачивается (в уроке это дало бы главу целиком).
CONT_RE = re.compile(r'\s*[;,]\s*(\d{1,3})\s*[:.]\s*(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?')


_OLD = str.maketrans('ѣѳіѵ', 'ефии')  # дореволюционная орфография: «Дѣянія» -> «Деяния»


def _ref_norm(s):
    s = s.lower().replace('ё', 'е').translate(_OLD).replace('ъ', '')
    s = re.sub(r'[.\s\-\u200a]+', '', s)
    return re.sub(r'^(\d)е?', r'\1', s)  # «1-е Коринфянам» и «1Кор» -> один ключ


def full_book_name(long_name):
    """Отображаемая полная форма без «Послания», «книги», предлогов и порядковых суффиксов:
    «От Иоанна» -> «Иоанна», «Послание римлянам» -> «Римлянам», «1-е посл. Петра» -> «1-Петра»,
    «1-книга Царств» -> «1-Царств»."""
    s = re.sub(r'^(?:от|к)\s+', '', (long_name or '').strip(), flags=re.IGNORECASE)
    s = re.sub(r'\b(?:послание|посл|книга|кн)\b\.?\s*', '', s, flags=re.IGNORECASE)
    s = re.sub(r'^(\d)[-_ ]?[еёя]?\s+', r'\1-', s).strip()
    return (s[:1].upper() + s[1:]) if s else s


def ref_aliases(books):
    """Нормализованное имя книги -> номер: таблица сокращений + короткое/полное
    имя из модуля и полное без предлога («от Иоанна» -> «Иоанна»)."""
    out = {}
    for num, variants in BOOK_ABBRS.items():
        for v in variants.split():
            out.setdefault(_ref_norm(v), num)
    for num, short, long in books:
        for nm in {short, long}:
            out.setdefault(_ref_norm(nm), num)
            stripped = re.sub(r'^(?:от|к)\s+', '', nm.strip(), flags=re.IGNORECASE)
            if stripped != nm:
                out.setdefault(_ref_norm(stripped), num)
    return out


def parse_refs(text, books):
    """Все ссылки в тексте (в порядке появления, без пересечений):
    [(начало, конец, номер книги, глава, стих_от, стих_до|None), ...]."""
    text = KEYWORD_RE.sub(' ', text or '')
    out, aliases, pos = [], ref_aliases(books), 0
    while True:
        m = REF_RE.search(text, pos)
        if not m:
            return out
        name = _ref_norm(m.group(1))
        num = aliases.get(name)
        if num is None and len(name) >= 2:  # уникальный префикс: «Быти» -> «Бытие»
            hits = {v for k, v in aliases.items() if k.startswith(name)}
            if len(hits) == 1:
                num = hits.pop()
        if num is not None:
            vf = int(m.group(4)) if m.group(4) else None
            vt = int(m.group(5)) if m.group(5) else vf
            out.append((m.start(), m.end(), num, int(m.group(2)), vf, vt))
            pos = m.end()
            while True:  # «9:9; 12:1, 13:5» — продолжения наследуют книгу
                c = CONT_RE.match(text, pos)
                if not c:
                    break
                out.append((c.start(), c.end(), num, int(c.group(1)),
                            int(c.group(2)), int(c.group(3) or c.group(2))))
                pos = c.end()
        else:
            pos = m.start() + 1


def parse_ref(text, books):
    """Первая осмысленная ссылка (см. parse_refs) либо None."""
    refs = parse_refs(text, books)
    return refs[0][2:] if refs else None


def verse_block(module, book_number, chapter, vf, vt, peek=None, inline=False):
    """(заголовок с полным именем книги, текст выбранных стихов); peek ограничивает
    ссылку на главу без стиха: карточка показывает первые peek, сборка урока — всю главу.
    inline — стихи одной строкой через пробел (режим копирования «в строку»)."""
    verses = module.verses(book_number, chapter)
    if vf is None:
        sel = verses[:peek] if peek else verses
    else:
        sel = [r for r in verses if vf <= r[0] <= vt]
    long_name = full_book_name(next((b[2] for b in module.books if b[0] == book_number), ''))
    rng = '' if vf is None else (f':{vf}' if vf == vt else f':{vf}-{vt}')
    header = f'{long_name} {chapter}{rng}'
    body = '\n'.join(f'{v} {note_to_plain(raw, module.short_map)}' for v, raw in sel)
    return header, (inline_body(body) if inline else body)


def build_lesson(text, module, inline=False):
    """Текст со ссылками -> текст, где каждая ссылка развёрнута в цитату
    (полное имя книги + стихи). Ссылка без стихов в модуле остаётся как была."""
    out, pos = [], 0
    for s, e, num, ch, vf, vt in parse_refs(text, module.books):
        out.append(text[pos:s])
        header, body = verse_block(module, num, ch, vf, vt, inline=inline)
        out.append(f'{header}\n{body}\n' if body else text[s:e])
        pos = e
    out.append(text[pos:])
    return ''.join(out)


def find_strong_verses(module, num):
    """Стихи перевода, где номер Стронга стоит в теге <S> (конкорданс MyBible)."""
    num = str(num).lstrip('GHgh')
    pats = {f'<S>{num}</S>', f'<S>H{num}</S>', f'<S>G{num}</S>'}
    rows = []
    for pat in pats:
        rows += module.conn.execute(
            'SELECT book_number, chapter, verse FROM verses WHERE text LIKE ?',
            (f'%{pat}%',)).fetchall()
    return sorted(set(rows))


def dict_search(modules, word, limit=200):
    """Статьи словарей, где слово встречается в теме или тексте
    (регистронезависимо для кириллицы — фильтруем в python, не в SQLite)."""
    q = word.lower()
    out = []
    for dm in modules:
        for topic, definition in dm.conn.execute(
                f'SELECT topic, definition FROM {dm.dict_table}'):
            if q in (topic or '').lower() or q in (definition or '').lower():
                out.append((dm, topic))
                if len(out) >= limit:
                    return out
    return out


S_LINK_RE = re.compile(r"<a\s+href='S:([GH]?\d+)'[^>]*>[^<]*</a>", re.IGNORECASE)
B_LINK_RE = re.compile(r"<a\s+href='B:([^']+)'[^>]*>([^<]*)</a>", re.IGNORECASE)


def strong_body_from_entry(entry, books_map):
    """Статья из «Стронг-к» в текст для карточки: ссылки-синонимы -> кликабельные номера,
    библейские ссылки -> читаемый вид, остальная разметка вычищается."""
    s = S_LINK_RE.sub(lambda m: m.group(1).upper(), entry)
    s = B_LINK_RE.sub(lambda m: f'{m.group(2)} ({xref_text(m.group(1), books_map)})', s)
    return note_to_plain(s, books_map)
