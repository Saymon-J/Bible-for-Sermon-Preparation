# -*- coding: utf-8 -*-
"""Иконка приложения: PNG-кодек, обрезка фона, бокс-ресемпл, ICO 16-256."""
import base64
import struct
import zlib

import tkinter as tk

from paths import APP_DIR, FROZEN, LOGO_PATH



PNG_SIG = b'\x89PNG\r\n\x1a\n'
ICON_SIZES = (256, 128, 64, 48, 32, 24, 16)


def png_decode(data):
    """PNG (8 бит, без interlace; серый/RGB/палитра/RGBA) → (w, h, RGBA-байты), иначе None."""
    if data[:8] != PNG_SIG:
        return None
    pos, idat, w = 8, [], 0
    depth = ctype = interlace = 0
    plte = trns = b''
    while pos + 12 <= len(data):
        ln = int.from_bytes(data[pos:pos + 4], 'big')
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if typ == b'IHDR':
            w, h, depth, ctype, _c, _f, interlace = struct.unpack('>IIBBBBB', body)
        elif typ == b'PLTE':
            plte = body
        elif typ == b'tRNS':
            trns = body
        elif typ == b'IDAT':
            idat.append(body)
        elif typ == b'IEND':
            break
        pos += 12 + ln
    if depth != 8 or interlace or ctype not in (0, 2, 3, 6):
        return None
    bpp = {0: 1, 2: 3, 3: 1, 6: 4}[ctype]
    stride = w * bpp
    try:
        raw = zlib.decompress(b''.join(idat))
        out = bytearray(w * h * 4)
        prev = bytes(stride)
        p = 0
        for y in range(h):
            f = raw[p]
            p += 1
            line = bytearray(raw[p:p + stride])
            p += stride
            if f == 1:
                for i in range(bpp, stride):
                    line[i] = (line[i] + line[i - bpp]) & 255
            elif f == 2:
                for i in range(stride):
                    line[i] = (line[i] + prev[i]) & 255
            elif f == 3:
                for i in range(stride):
                    a = line[i - bpp] if i >= bpp else 0
                    line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
            elif f == 4:
                for i in range(stride):
                    a = line[i - bpp] if i >= bpp else 0
                    b = prev[i]
                    c = prev[i - bpp] if i >= bpp else 0
                    pa, pb, pc = b - c, a - c, a + b - 2 * c
                    pr = a if (abs(pa) <= abs(pb) and abs(pa) <= abs(pc)) else \
                        (b if abs(pb) <= abs(pc) else c)
                    line[i] = (line[i] + pr) & 255
            o = y * w * 4
            if ctype == 6:
                out[o:o + stride] = line
            elif ctype == 2:
                for x in range(w):
                    q4, q3 = o + x * 4, x * 3
                    out[q4:q4 + 3] = line[q3:q3 + 3]
                    out[q4 + 3] = 255
            elif ctype == 0:
                for x in range(w):
                    q4 = o + x * 4
                    out[q4] = out[q4 + 1] = out[q4 + 2] = line[x]
                    out[q4 + 3] = 255
            else:  # палитра
                for x in range(w):
                    idx = line[x]
                    q4 = o + x * 4
                    out[q4:q4 + 3] = plte[idx * 3:idx * 3 + 3]
                    out[q4 + 3] = trns[idx] if idx < len(trns) else 255
            prev = bytes(line)
        return w, h, bytes(out)
    except Exception:
        return None


def png_encode(w, h, rgba):
    """RGBA → PNG (без построчных фильтров, zlib-9)."""
    stride = w * 4
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(typ, body):
        return len(body).to_bytes(4, 'big') + typ + body + \
            struct.pack('>I', zlib.crc32(typ + body))

    return (PNG_SIG + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b''))


def resample_rgba(rgba, w, h, tw, th):
    """Бокс-фильтр с учётом альфы: цвет усредняется весом альфы, прозрачный фон
    не подтекает в контент. Апскейл — ближайшим пикселем (ящик шириной 1)."""
    out = bytearray(tw * th * 4)
    for ty in range(th):
        y0 = ty * h // th
        y1 = max(y0 + 1, (ty + 1) * h // th)
        for tx in range(tw):
            x0 = tx * w // tw
            x1 = max(x0 + 1, (tx + 1) * w // tw)
            sr = sg = sb = sa = 0
            for y in range(y0, y1):
                base = (y * w + x0) * 4
                for _ in range(x0, x1):
                    a = rgba[base + 3]
                    if a:
                        sr += rgba[base] * a
                        sg += rgba[base + 1] * a
                        sb += rgba[base + 2] * a
                        sa += a
                    base += 4
            o = (ty * tw + tx) * 4
            if sa:
                out[o] = sr // sa
                out[o + 1] = sg // sa
                out[o + 2] = sb // sa
                out[o + 3] = sa // ((x1 - x0) * (y1 - y0))
    return bytes(out)


def icon_from_logo(png_bytes):
    """Логотип → {размер: PNG 16..256}: фон отрезается заливкой от краёв изображения,
    контент обрезается по рамке и вписывается в квадрат 256 без искажений, уменьшение —
    бокс-фильтром. None, если PNG не декодировался.
    ponytail: заливка от рамки не трогает светлые пятна внутри рисунка, но «протечёт»
    сквозь белый штрих, пересекающий весь логотип, — потолок метода, апгрейд: flood
    с запретом узких проходов."""
    dec = png_decode(png_bytes)
    if not dec:
        return None
    w, h, rgba = dec
    bg = rgba[:4]  # фон = цвет угла
    tol = 40       # сумма |ΔR|+|ΔG|+|ΔB|, при которой пиксель считаем фоном

    def is_bg(i):
        if rgba[i + 3] == 0:
            return True
        return (abs(rgba[i] - bg[0]) + abs(rgba[i + 1] - bg[1]) +
                abs(rgba[i + 2] - bg[2])) <= tol

    n = w * h
    mask = bytearray(n)  # 1 = фон
    stack = [x for x in range(w)] + [(h - 1) * w + x for x in range(w)]
    stack += [y * w for y in range(h)] + [y * w + w - 1 for y in range(h)]
    while stack:
        i = stack.pop()
        if mask[i] or not is_bg(i * 4):
            continue
        mask[i] = 1
        x, y = i % w, i // w
        if x:
            stack.append(i - 1)
        if x < w - 1:
            stack.append(i + 1)
        if y:
            stack.append(i - w)
        if y < h - 1:
            stack.append(i + w)
    xs = [i % w for i in range(n) if not mask[i]]
    if not xs:
        return None
    ys = [i // w for i in range(n) if not mask[i]]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    crop = bytearray(bw * bh * 4)  # контент с альфой: фон → 0
    for yy in range(bh):
        so, do = ((y0 + yy) * w + x0) * 4, yy * bw * 4
        crop[do:do + bw * 4] = rgba[so:so + bw * 4]
        row_mask = mask[(y0 + yy) * w + x0:(y0 + yy) * w + x0 + bw]
        for xx in range(bw):
            if row_mask[xx]:
                crop[do + xx * 4 + 3] = 0
    # вписать в квадрат 256 без искажений, остальное — прозрачно
    k = 256 / max(bw, bh)
    tw, th = max(1, round(bw * k)), max(1, round(bh * k))
    inner = resample_rgba(crop, bw, bh, tw, th)
    canvas = bytearray(256 * 256 * 4)
    ox, oy = (256 - tw) // 2, (256 - th) // 2
    for yy in range(th):
        do = ((oy + yy) * 256 + ox) * 4
        canvas[do:do + tw * 4] = inner[yy * tw * 4:(yy + 1) * tw * 4]
    images = {256: png_encode(256, 256, canvas)}
    for s in ICON_SIZES[1:]:
        images[s] = png_encode(s, s, resample_rgba(canvas, 256, 256, s, s))
    return images


def make_ico(images):
    """{размер: PNG} → ICO с PNG-слоями (Windows Vista+); 256 записывается байтом 0."""
    sizes = sorted(images)
    head = struct.pack('<HHH', 0, 1, len(sizes))
    entries, offs = [], 6 + 16 * len(sizes)
    for s in sizes:
        d = images[s]
        entries.append(struct.pack('<BBBBHHII', s % 256, s % 256, 0, 0, 1, 32,
                                   len(d), offs))
        offs += len(d)
    return head + b''.join(entries) + b''.join(images[s] for s in sizes)


def ensure_icon_files():
    """Готовит app/icon.png (256px) и app/icon.ico (16–256, PNG-слои) из logo2.png.
    Пересборка только когда логотип новее файлов; в exe не пишется. Возвращает
    {размер: PNG} или None."""
    if FROZEN:
        return None
    ico_path, png_path = APP_DIR / 'icon.ico', APP_DIR / 'icon.png'
    logo_mtime = LOGO_PATH.stat().st_mtime if LOGO_PATH.is_file() else 0
    if not logo_mtime or (ico_path.is_file() and png_path.is_file()
                          and ico_path.stat().st_mtime > logo_mtime):
        return None
    images = icon_from_logo(LOGO_PATH.read_bytes())
    if images is None:
        return None
    try:
        png_path.write_bytes(images[256])
        ico_path.write_bytes(make_ico(images))
    except OSError:
        return None
    return images


def _read_ico_pngs(ico_path):
    """ICO → {размер: PNG-байты} (то, что сами записали); None при любой ошибке."""
    try:
        data = ico_path.read_bytes()
        cnt = int.from_bytes(data[4:6], 'little')
        out = {}
        for i in range(cnt):
            e = data[6 + 16 * i:6 + 16 * i + 16]
            s = e[0] or 256
            out[s] = data[int.from_bytes(e[12:16], 'little'):
                          int.from_bytes(e[12:16], 'little') + int.from_bytes(e[8:12], 'little')]
        return out or None
    except Exception:
        return None


def load_app_icons():
    """Фото-иконки для iconphoto (Tk сам выбирает ближайший размер): 256/48/32/16
    из обработанного logo2; запасной путь — целочисленное уменьшение Tk,
    последний — программный рисунок."""
    images = None
    try:
        images = ensure_icon_files()
    except Exception:
        images = None
    if images is None and (APP_DIR / 'icon.ico').is_file():
        images = _read_ico_pngs(APP_DIR / 'icon.ico')  # файлы свежее логотипа — из кэша
    if images:
        try:
            out = [tk.PhotoImage(data=base64.b64encode(images[s]))
                   for s in (256, 48, 32, 16) if s in images]
            if out:
                return out
        except Exception:
            pass
    if LOGO_PATH.is_file():
        try:
            img = tk.PhotoImage(file=str(LOGO_PATH))
            f = max(1, -(-max(img.width(), img.height()) // 64))  # ceil
            if f > 1:
                img = img.subsample(f, f)
            return [img]
        except Exception:
            pass
    return [make_icon()]


def make_icon():
    """Рисует 48x48 иконку (синий квадрат, раскрытая книга, золотой крест)."""
    img = tk.PhotoImage(width=48, height=48)
    bg, edge, page, gold = '#31567d', '#24405d', '#f2efe6', '#e8c56a'
    r = 9

    def rect(x0, y0, x1, y1, color):
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                img.put(color, (x, y))

    for x in range(48):
        for y in range(48):
            if ((x < r and y < r and (x - r) ** 2 + (y - r) ** 2 > r * r) or
                    (x >= 48 - r and y < r and (x - (47 - r)) ** 2 + (y - r) ** 2 > r * r) or
                    (x < r and y >= 48 - r and (x - r) ** 2 + (y - (47 - r)) ** 2 > r * r) or
                    (x >= 48 - r and y >= 48 - r and (x - (47 - r)) ** 2 + (y - (47 - r)) ** 2 > r * r)):
                continue
            img.put(bg, (x, y))
    rect(22, 4, 25, 13, gold)   # крест
    rect(18, 7, 29, 9, gold)
    for x in range(6, 23):      # левая страница
        dy = (x - 6) * 6 // 17
        rect(x, 20 - dy, x, 42 - dy, page)
    for x in range(25, 42):     # правая страница
        dy = (41 - x) * 6 // 17
        rect(x, 20 - dy, x, 42 - dy, page)
    rect(23, 19, 24, 42, edge)  # корешок
    return img
