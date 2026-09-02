# -*- coding: utf-8 -*-
"""Разбор разметки MyBible в поток токенов и чистый текст."""
import html
import re



TAG_RE = re.compile(r'</?(?:pb|br|t|f|x|J|i|e|S|m)\s*/?>', re.IGNORECASE)
RESIDUAL_RE = re.compile(r'<[^>]*>')
XREF_TAG_RE = re.compile(r'<x>(.*?)</x>', re.IGNORECASE | re.DOTALL)
# координаты в комментариях/словарях: <a href='B:480 3:13-19'>3:13-19</a>,
# иногда с class='B' и префиксом C:@ (10 12:3); кавычки всегда есть
A_REF_TAG_RE = re.compile(
    r"<a\b[^>]*href=['\"](B:[^'\"]+|C:@[^'\"]+)['\"][^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL)
XREF_ANY_RE = re.compile(rf"<x>(.*?)</x>|{A_REF_TAG_RE.pattern}", re.IGNORECASE | re.DOTALL)
XREF_RE = re.compile(r'^\s*(\d+)\s+(\d+):(\d+)(?:\s*-\s*(\d+):?(\d+)?)?\s*$')
FN_MARKER_ONLY_RE = re.compile(r'^[\[\]+*\s0-9—:-]*$')
STRONG_TOKEN_RE = re.compile(r'\b(?:[GH]\d{1,5}|\d{4,5})\b')  # ponytail: голое 4+значное число тоже ссылка; год в карточке Стронга станет кликабельным — редкий ложный плюс


def parse_markup(text):
    """Разбирает разметку MyBible в поток кортежей (kind, value, styles).

    kind: 'text' | 'nl' (перевод строки) | 'fn' (сноска целиком) |
    'xref' (ссылка вне сноски) | 'sn' (номер Стронга, например '7121').
    styles — frozenset из 'red' (слова Христа <J>), 'ital' (<i>/<e>), 'poetry' (<t>).
    <m>…</m> (морфология) выбрасывается целиком.
    """
    out = []
    d = {'j': 0, 'i': 0, 'e': 0, 't': 0}
    f_depth = f_start = 0
    x_depth = x_start = 0
    s_depth = s_start = 0
    skip_name = None

    def styles():
        s = set()
        if d['j']:
            s.add('red')
        if d['i'] or d['e']:
            s.add('ital')
        if d['t']:
            s.add('poetry')
        return frozenset(s)

    pos = 0
    for m in TAG_RE.finditer(text):
        tag = m.group(0)
        name = tag.strip('</>').lower()
        closing = tag.startswith('</')
        if f_depth:  # внутри <f>...</f>: копим сноску целиком
            if name == 'f' and closing:
                f_depth = 0
                out.append(('fn', text[f_start:m.start()], frozenset()))
        elif x_depth:
            if name == 'x' and closing:
                x_depth = 0
                out.append(('xref', text[x_start:m.start()], styles()))
        elif s_depth:
            if name == 's' and closing:
                s_depth = 0
                out.append(('sn', text[s_start:m.start()].strip(), styles()))
        elif skip_name:
            if name == skip_name and closing:
                skip_name = None
        else:
            if m.start() > pos:
                piece = RESIDUAL_RE.sub('', text[pos:m.start()])
                if piece:
                    out.append(('text', piece, styles()))
            if name in ('pb', 'br'):
                out.append(('nl', '', frozenset()))
            elif name == 't':
                out.append(('nl', '', frozenset()))  # поэтическая строка — с новой строки
                d['t'] = max(0, d['t'] + (-1 if closing else 1))
            elif name == 'f' and not closing:
                f_depth, f_start = 1, m.end()
            elif name == 'x' and not closing:
                x_depth, x_start = 1, m.end()
            elif name == 's' and not closing:
                s_depth, s_start = 1, m.end()
            elif name == 'm' and not closing:
                skip_name = name
            elif name in d:
                d[name] = max(0, d[name] + (-1 if closing else 1))
        pos = m.end()
    if pos < len(text) and not f_depth and not x_depth and not s_depth and not skip_name:
        piece = RESIDUAL_RE.sub('', text[pos:])
        if piece:
            out.append(('text', piece, styles()))
    return out


def xref_text(raw, books_map):
    """'470 4:1-11' -> 'Мат. 4:1-11' (номер книги -> краткое имя, если известно)."""
    m = XREF_RE.match(raw or '')
    if not m:
        return (raw or '').strip()
    book, ch, vs = int(m.group(1)), m.group(2), m.group(3)
    ref = f'{ch}:{vs}'
    if m.group(4):
        ref += '-' + (f'{m.group(4)}:{m.group(5)}' if m.group(5) else m.group(4))
    name = books_map.get(book)
    return f'{name} {ref}' if name else f'{book} {ref}'


def href_ref(href):
    """'B:470 10:25' / 'C:@10 12:3' -> '470 10:25' / '10 12:3', либо None."""
    h = (href or '').strip()
    if h[:3].upper() == 'C:@':
        return h[3:].strip()
    if h[:2].upper() == 'B:':
        return h[2:].strip()
    return None


def blink_text(href, label, books_map):
    """Отображение <a href='B:480 3:13-19'>3:13-19</a> -> 'Мар. 3:13-19':
    имя книги из href; если href — не координаты, остаётся текст ссылки."""
    ref = href_ref(href)
    return xref_text(ref, books_map) if ref and XREF_RE.match(ref) else label


def note_to_plain(raw, books_map):
    """Текст примечания/стиха в читаемый вид: <x>- и <a href='B:…'>-ссылки ->
    имена книг, теги вырезаются."""
    s = XREF_TAG_RE.sub(lambda m: xref_text(m.group(1), books_map), raw or '')
    s = A_REF_TAG_RE.sub(lambda m: blink_text(m.group(1), m.group(2), books_map), s)
    s = re.sub(r'<head>.*?</head>', '', s, flags=re.IGNORECASE | re.DOTALL)  # css-мусор словарей
    s = re.sub(r'</?(?:p|pb|br|t)\s*/?>', '\n', s, flags=re.IGNORECASE)
    s = re.sub(r'<[Smf]>.*?</[Smf]>', '', s, flags=re.IGNORECASE | re.DOTALL)  # f — сноски-маркеры («[143]»), в читалке их тоже нет
    s = RESIDUAL_RE.sub('', s).replace('\r', '').replace('&nbsp;', ' ')
    s = html.unescape(s)
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()


def compress_ranges(vs):
    """[1,2,3,5,8,11,12,13,14] -> '1-3, 5, 8, 11-14'."""
    vs = sorted(vs)
    parts, i = [], 0
    while i < len(vs):
        j = i
        while j + 1 < len(vs) and vs[j + 1] == vs[j] + 1:
            j += 1
        parts.append(str(vs[i]) if i == j else f'{vs[i]}-{vs[j]}')
        i = j + 1
    return ', '.join(parts)


def inline_body(text):
    """Многострочный текст стихов в одну строку: переводы строк -> пробелы."""
    return ' '.join(text.split())


def build_copy(book_name, chapter, verses, inline=False):
    """Формат MyBible: строка-ссылка, ниже стихи с номерами — каждый с новой
    строки, при inline — все стихи одной строкой через пробел."""
    vs = sorted(verses)
    if not vs:
        return ''
    rng = compress_ranges(vs)
    header = f'{book_name} {chapter}:{vs[0]}' if len(vs) == 1 else f'{book_name} {chapter}:{rng}'
    body = '\n'.join(f'{v} {verses[v]}' for v in vs)
    return header + '\n' + (inline_body(body) if inline else body)


def split_strong_tokens(text):
    """[(фрагмент, токен или None)] — токены вида G26/H7225/7225 кликабельны в карточках."""
    out, pos = [], 0
    for m in STRONG_TOKEN_RE.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], None))
        out.append((m.group(0), m.group(0)))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], None))
    return out
