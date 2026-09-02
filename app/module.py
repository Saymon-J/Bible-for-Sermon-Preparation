# -*- coding: utf-8 -*-
"""Модуль MyBible (*.sqlite3): перевод, комментарий, словарь."""
import io
import re
import shutil
import sqlite3
import tempfile
import urllib.parse
import urllib.request
import zipfile
from html import unescape
from pathlib import Path

from markup import note_to_plain
from paths import MODULE_DIR, MODULE_SUBS, ROOT_DIR



class Module:
    def __init__(self, path):
        self.path = Path(path)
        self.file_name = Path(path).name
        self.conn = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
        try:
            self._detect()
        except Exception:
            self.conn.close()  # иначе файл останется занятым на Windows
            raise

    def _detect(self):
        tabs = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        info = dict(self.conn.execute('SELECT name, value FROM info')) if 'info' in tabs else {}
        self.description = (info.get('description') or self.file_name).strip()
        self.is_commentary = self.is_dictionary = False
        self._cache = None
        self._ccache = None

        if 'verses' in tabs and 'books' in tabs:
            self.chapter_string = info.get('chapter_string') or 'Глава'
            self.chapter_string_ps = info.get('chapter_string_ps') or self.chapter_string
            self.has_stories = 'stories' in tabs
            self.has_introductions = 'introductions' in tabs
            cols = [r[1] for r in self.conn.execute('PRAGMA table_info(books)')]
            # порядок книг: sorting_order, а где её нет (MDR, RST+, РСП) — по book_number
            order = 'sorting_order, book_number' if 'sorting_order' in cols else 'book_number'
            self.books = self.conn.execute(
                f'SELECT book_number, short_name, long_name FROM books ORDER BY {order}').fetchall()
            self.chapters = dict(self.conn.execute(
                'SELECT book_number, MAX(chapter) FROM verses GROUP BY book_number'))
            self.short_map = {num: sn.replace('\u200a', ' ') for num, sn, _ in self.books}
        elif 'commentaries' in tabs:
            self.is_commentary = True
            self.books, self.chapters, self.short_map = [], {}, {}
        elif 'dictionaries' in tabs or 'dictionary' in tabs:
            # таблица бывает в ед. и мн. числе; темы вида 'H7225'/'G26'
            self.is_dictionary = True
            self.dict_table = 'dictionaries' if 'dictionaries' in tabs else 'dictionary'
            self.books, self.chapters, self.short_map = [], {}, {}
        else:
            raise ValueError('не похож на модуль MyBible (нет verses/books, commentaries или dictionaries)')

    def verses(self, book_number, chapter):
        return self.conn.execute(
            'SELECT verse, text FROM verses '
            'WHERE book_number=? AND chapter=? ORDER BY verse',
            (book_number, chapter)).fetchall()

    def stories(self, book_number, chapter):
        if not self.has_stories:
            return {}
        st = {}
        for v, title in self.conn.execute(
                'SELECT verse, title FROM stories WHERE book_number=? AND chapter=? '
                'ORDER BY verse, order_if_several', (book_number, chapter)):
            st.setdefault(v, []).append(title)
        return st

    def introduction(self, book_number):
        if not getattr(self, 'has_introductions', False):
            return None
        row = self.conn.execute(
            'SELECT introduction FROM introductions WHERE book_number=?',
            (book_number,)).fetchone()
        return row[0] if row else None

    def notes(self, book_number, chapter):
        """Записи комментария на главу: [(стих_от, стих_до, маркер, текст), ...]."""
        if not self.is_commentary:
            return []
        cols = [r[1] for r in self.conn.execute('PRAGMA table_info(commentaries)')]
        marker_sel = 'marker' if 'marker' in cols else "''"  # у Баркли/МакАртура колонки marker нет
        rows = self.conn.execute(
            f"SELECT verse_number_from, verse_number_to, {marker_sel}, text FROM commentaries "
            "WHERE CAST(book_number AS INTEGER)=? "
            "AND CAST(chapter_number_from AS INTEGER)<=? "
            "AND CAST(CASE WHEN chapter_number_to IS NULL OR chapter_number_to='' "
            "OR chapter_number_to='0' THEN chapter_number_from "
            "ELSE chapter_number_to END AS INTEGER)>=? "
            "ORDER BY CAST(chapter_number_from AS INTEGER), CAST(verse_number_from AS INTEGER)",
            (book_number, chapter, chapter)).fetchall()
        out = []
        for vf, vt, marker, text in rows:
            try:
                vf = int(vf)
            except (TypeError, ValueError):
                vf = 0
            try:
                vt = int(vt) if vt not in (None, '', 'None', '0') else vf
            except (TypeError, ValueError):
                vt = vf
            out.append((vf, vt, marker or '', text or ''))
        return out

    def define(self, topic, prefer=None):
        """Статья словаря по теме (номеру Стронга), либо None.
        prefer='H'/'G' — какой завет иметь в виду для голого номера (темы H/G пересекаются)."""
        t = str(topic)
        variants = []
        if prefer:
            variants.append(prefer + t.lstrip('GHgh'))
        variants += [t, t.lstrip('GHgh'), t.lstrip('0'), t.zfill(4)]
        for pat in variants:
            row = self.conn.execute(
                f'SELECT definition FROM {self.dict_table} WHERE topic=?', (pat,)).fetchone()
            if row:
                return row[0]
        return None

    def search_cache(self):
        """Индекс для поиска: [(книга, глава, стих, чистый текст)]. Строится один раз (~2 c)."""
        if self._cache is None:
            self._cache = [
                (bn, ch, v, note_to_plain(txt, self.short_map))
                for bn, ch, v, txt in self.conn.execute(
                    'SELECT book_number, chapter, verse, text FROM verses')]
        return self._cache

    def commentary_cache(self, short_map):
        """Все заметки комментария для поиска: [(книга, глава, стих_от|None, чистый текст)].
        Строится один раз; карта книг запекается при первой сборке (берётся у перевода)."""
        if not self.is_commentary:
            return []
        if self._ccache is None:
            self._ccache = []
            for bn, cf, vf, text in self.conn.execute(
                    'SELECT book_number, chapter_number_from, verse_number_from, text '
                    'FROM commentaries'):
                try:
                    b, ch = int(bn), int(cf)
                except (TypeError, ValueError):
                    continue
                try:
                    v = int(vf) if vf not in (None, '') else None
                except (TypeError, ValueError):
                    v = None
                plain = note_to_plain(text or '', short_map)
                if plain:
                    self._ccache.append((b, ch, v, plain))
        return self._ccache


def migrate_old_layout():
    """Старая плоская «переводы» -> module/{переводы,словари,комментарии} по типу модуля.
    Занятые другим процессом файлы остаются в старой папке — она продолжает сканироваться."""
    old = ROOT_DIR / 'переводы'
    if not old.is_dir():
        return []
    todo = [p for p in old.iterdir()
            if p.is_file() and p.suffix.lower() in ('.sqlite3', '.db')]
    if not todo:
        return []
    errors = []
    for sub in MODULE_SUBS:
        (MODULE_DIR / sub).mkdir(parents=True, exist_ok=True)
    for p in sorted(todo):
        m = None
        try:
            m = Module(p)
            kind = 'словари' if m.is_dictionary else \
                'комментарии' if m.is_commentary else 'переводы'
            dest = MODULE_DIR / kind / p.name
            if not dest.exists():
                m.conn.close()  # Windows: открытый файл может не переименоваться
                p.rename(dest)
        except Exception as ex:  # занят/не читается — оставляем на месте
            errors.append(f'{p.name}: {ex}')
        finally:
            if m is not None:
                try:
                    m.conn.close()
                except Exception:
                    pass
    try:
        old.rmdir()  # пустую убираем; с посторонними файлами останется — не страшно
    except OSError:
        pass
    return errors


def install_module(src, dest_root=MODULE_DIR):
    """Поставить файл модуля в module/<тип>/ (тип — по таблицам внутри файла).
    Возвращает (тип, '') при успехе или (None, сообщение об ошибке).
    Уже установленное имя не перезаписывается: старый файл может быть открыт приложением."""
    src = Path(src)
    m = None
    try:
        m = Module(src)
        kind = 'словари' if m.is_dictionary else \
            'комментарии' if m.is_commentary else 'переводы'
        dest = dest_root / kind / src.name
        if dest.exists():
            return None, f'{src.name}: уже установлен в «module/{kind}»'
        dest.parent.mkdir(parents=True, exist_ok=True)
        m.conn.close()  # Windows: свой хэндл мешает копированию
        shutil.copy2(src, dest)
        return kind, ''
    except Exception as ex:
        return None, f'{src.name}: {ex}'
    finally:
        if m is not None:
            try:
                m.conn.close()
            except Exception:
                pass


def load_modules():
    errors = migrate_old_layout()
    scan_dirs = [MODULE_DIR / s for s in MODULE_SUBS] + [ROOT_DIR / 'переводы']
    paths = sorted({p for d in scan_dirs if d.is_dir()
                    for p in list(d.glob('*.sqlite3')) + list(d.glob('*.db'))})
    trans, comms, dicts = [], [], []
    for p in paths:
        try:
            m = Module(p)
            if m.is_commentary:
                comms.append(m)
            elif m.is_dictionary:
                dicts.append(m)
            else:
                trans.append(m)
        except Exception as ex:
            errors.append(f'{p.name}: {ex}')
    return trans, comms, dicts, errors


# ---------- каталог модулей MyBible на ph4.ru ----------
PH4_BASE = 'https://www.ph4.ru/'
PH4_PAGE = PH4_BASE + 'b4_1.php?q=mybible'
# ссылка скачивания: _dl.php?back=bbl&a=<имя>&b=mybible&c; имя бывает с кириллицей
# и с заэкранированным апострофом (NRT\'23); кавычки в атрибуте — обе
PH4_DL_RE = re.compile(
    r"""href=["'](_dl\.php\?back=\w+&a=(?:[^"'\\]|\\.)*?&b=mybible&c)["']""")


def web_url(raw):
    """Кириллица/апостроф в параметрах -> percent-encoding, иначе urllib не примет."""
    return urllib.parse.quote(raw, safe=":/?&=%'")


def web_catalog(html=None):
    """Каталог ph4.ru: [(подпись, ссылка)]. html — готовая страница (для тестов)."""
    if html is None:
        req = urllib.request.Request(PH4_PAGE, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')
    out, seen = [], set()
    matches = list(PH4_DL_RE.finditer(html))
    for i, m in enumerate(matches):
        url = PH4_BASE + m.group(1).replace("\\'", "'")
        if url in seen:
            continue
        seen.add(url)
        mid = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get('a', [''])[0]
        # подпись — в ячейках той же строки: <b>ИМЯ</b> ГОД и <div class=btl>Название</div>
        nxt = matches[i + 1].start() if i + 1 < len(matches) else len(html)
        win = html[m.end():nxt]
        tm = re.search(r'<div class=btl>([^<]+)</div>', win)
        nm = re.search(r'<nobr><b>([^<]+)</b>\s*([^<]*)</nobr>', win)
        title = unescape(tm.group(1)).strip() if tm else ''
        name = (nm.group(1) + ' ' + nm.group(2).strip()).strip() if nm else ''
        label = ' — '.join(x for x in (name, title) if x) or mid
        out.append((label, url))
    return out


def install_zip(data, dest_root=MODULE_DIR):
    """Все модули из zip-архива (ph4.ru кладёт туда .SQLite3): [(имя, тип, ошибка)]."""
    results = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if name.lower().endswith(('.sqlite3', '.db')):
                with tempfile.TemporaryDirectory() as td:
                    p = Path(td) / Path(name).name
                    p.write_bytes(z.read(name))
                    kind, err = install_module(p, dest_root)
                results.append((Path(name).name, kind, err))
    return results


def web_install(url):
    """Скачать zip модуля из каталога и поставить всё его содержимое."""
    req = urllib.request.Request(web_url(url), headers={'User-Agent': 'Mozilla/5.0'})
    return install_zip(urllib.request.urlopen(req, timeout=180).read())
