# -*- coding: utf-8 -*-
"""Темы оформления (Fluent 2 + «библейские» из MyBible) и гарнитура интерфейса."""

from tkinter import font as tkfont

TEXT_FONT = 'Georgia'
UI_FONT_SIZE = 10  # размер элементов управления Fluent

# Именованные темы. window_bg — подложка (canvas), text_bg — карточка (card),
# accent — фирменный цвет, stroke — рамки 1px. «Пергамент» — по образцу MyBible
# (состаренная бумага, коричневый текст, красно-коричневые номера стихов).
THEMES = {
    'Светлая': {'window_bg': '#f5f5f5', 'text_bg': '#ffffff', 'fg': '#242424', 'fg2': '#616161',
                'vnum': '#00796B', 'chapter': '#0f6cbd', 'greek': '#9C5610',
                'red': '#d13438', 'selv': '#cce4f7', 'found': '#fff1b8',
                'xref': '#0f6cbd', 'strong': '#8764b8', 'stroke': '#d1d1d1', 'stroke2': '#ebebeb',
                'stroke_hover': '#b3b3b3', 'hover': '#ebebeb', 'press': '#e0e0e0',
                'menu_active': '#e5f1fb', 'thumb': '#c8c8c8',
                'green': '#107c10', 'green_bg': '#dff6dd', 'green_hover': '#cbe9c9',
                'accent': '#0f6cbd', 'accent_hover': '#115ea3', 'accent_press': '#0c3b5e',
                'accent_text': '#ffffff'},
    'Тёмная': {'window_bg': '#1f1f1f', 'text_bg': '#292929', 'fg': '#ffffff', 'fg2': '#b3b3b3',
               'vnum': '#4DB6AC', 'chapter': '#62abf5', 'greek': '#E0A96D',
               'red': '#e37d80', 'selv': '#115ea3', 'found': '#6e5f2c',
               'xref': '#62abf5', 'strong': '#b4a0e3', 'stroke': '#404040', 'stroke2': '#333333',
               'stroke_hover': '#616161', 'hover': '#333333', 'press': '#3d3d3d',
               'menu_active': '#333333', 'thumb': '#525252',
               'green': '#6ccb5f', 'green_bg': '#203627', 'green_hover': '#2a4530',
               'accent': '#479ef5', 'accent_hover': '#62abf5', 'accent_press': '#2899f5',
               'accent_text': '#000000'},
    # по фото MyBible: состаренный лист, тёмно-коричневый текст, терракотовые
    # номера стихов, оливково-бронзовые заголовки
    'Пергамент': {'window_bg': '#e2d3ae', 'text_bg': '#efe3c0', 'fg': '#4a3b2a', 'fg2': '#8a7a5f',
                  'vnum': '#b03a2e', 'chapter': '#6b5b1e', 'greek': '#8a4a10',
                  'red': '#c0392b', 'selv': '#e0cf9d', 'found': '#f7e398',
                  'xref': '#1f6f8b', 'strong': '#7a5aa0', 'stroke': '#c9b98f', 'stroke2': '#ddd0a8',
                  'stroke_hover': '#b3a276', 'hover': '#e2d4ae', 'press': '#d8c79c',
                  'menu_active': '#e9dcb4', 'thumb': '#c3b285',
                  'green': '#4f7a28', 'green_bg': '#e2e8c5', 'green_hover': '#d5dcb2',
                  'accent': '#7a5220', 'accent_hover': '#8f6430', 'accent_press': '#5f3f16',
                  'accent_text': '#ffffff'},
    # мягкая серо-бежевая («чтение вечером» без жёлтизны пергамента)
    'Сепия': {'window_bg': '#e7dfd0', 'text_bg': '#f4efe3', 'fg': '#3e3830', 'fg2': '#7d7568',
              'vnum': '#a0672f', 'chapter': '#77541f', 'greek': '#8a4a10',
              'red': '#b03a2e', 'selv': '#e2d8c4', 'found': '#ffe9a8',
              'xref': '#35678f', 'strong': '#7a5aa0', 'stroke': '#cfc4ac', 'stroke2': '#ded6c2',
              'stroke_hover': '#b8ab8e', 'hover': '#e8e1d1', 'press': '#ddd4bf',
              'menu_active': '#ece5d4', 'thumb': '#c5bba4',
              'green': '#4f7a28', 'green_bg': '#e3e8cf', 'green_hover': '#d6dcc0',
              'accent': '#6e5433', 'accent_hover': '#826641', 'accent_press': '#574226',
              'accent_text': '#ffffff'},
    # чистый чёрный (ночной режим без засветки, тёмная как в старой «Тёмной» палитра)
    'Ночь': {'window_bg': '#000000', 'text_bg': '#0d0d0d', 'fg': '#e0e0e0', 'fg2': '#8f8f8f',
             'vnum': '#4DB6AC', 'chapter': '#62abf5', 'greek': '#E0A96D',
             'red': '#e37d80', 'selv': '#1f3a5f', 'found': '#5f5524',
             'xref': '#62abf5', 'strong': '#b4a0e3', 'stroke': '#2a2a2a', 'stroke2': '#1c1c1c',
             'stroke_hover': '#454545', 'hover': '#1a1a1a', 'press': '#242424',
             'menu_active': '#1f1f1f', 'thumb': '#3d3d3d',
             'green': '#6ccb5f', 'green_bg': '#17301f', 'green_hover': '#1d3d26',
             'accent': '#479ef5', 'accent_hover': '#62abf5', 'accent_press': '#2899f5',
             'accent_text': '#000000'},
    # тёмно-синяя «ночная комната»
    'Полночь': {'window_bg': '#101828', 'text_bg': '#182236', 'fg': '#e8edf5', 'fg2': '#9aa8bf',
                'vnum': '#56c8d8', 'chapter': '#7ab8f5', 'greek': '#E0A96D',
                'red': '#e37d80', 'selv': '#24406b', 'found': '#6e5f2c',
                'xref': '#7ab8f5', 'strong': '#b4a0e3', 'stroke': '#2b3a52', 'stroke2': '#1f2c40',
                'stroke_hover': '#40536f', 'hover': '#202d44', 'press': '#28374f',
                'menu_active': '#22334d', 'thumb': '#43536e',
                'green': '#6ccb5f', 'green_bg': '#1c3326', 'green_hover': '#24402e',
                'accent': '#4f8ff5', 'accent_hover': '#6ba4f7', 'accent_press': '#336fd4',
                'accent_text': '#0b1220'},
}
DEFAULT_THEME = 'Светлая'


def ui_font_family(root):
    """Гарнитура интерфейса Fluent: Segoe UI Variable (Windows 11), иначе Segoe UI."""
    fams = set(tkfont.families(root))
    for f in ('Segoe UI Variable Text', 'Segoe UI Variable Display', 'Segoe UI'):
        if f in fams:
            return f
    return tkfont.nametofont('TkDefaultFont').actual('family')
