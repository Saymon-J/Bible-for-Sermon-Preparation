# -*- coding: utf-8 -*-
"""Bible Reader — читалка модулей MyBible (*.sqlite3) для домашнего использования.

Запуск:  python bible.py   (или start.bat из корня проекта)
Самопроверка без GUI:  python bible.py --selftest
Только стандартная библиотека (tkinter + sqlite3).
"""
import sys

import tkinter as tk
from tkinter import ttk, messagebox

from application import App
from module import load_modules
from paths import APP_VERSION
from selftest import selftest


def main():
    if '--selftest' in sys.argv:
        selftest()
        return
    if '--selftest-gui' in sys.argv:
        from selftest_gui import selftest_gui
        selftest_gui()
        return
    if '--version' in sys.argv:
        print(f'Библия {APP_VERSION}')
        return
    root = tk.Tk()
    try:
        ttk.Style().theme_use('clam')
    except Exception:
        pass
    trans, comms, dicts, errors = load_modules()
    if not trans:
        root.withdraw()
        msg = 'В папке «module» (переводы/словари/комментарии) не найдено ни одного модуля MyBible (*.sqlite3).'
        if errors:
            msg += '\n\n' + '\n'.join(errors)
        messagebox.showerror('Библия', msg)
        return
    App(root, trans, comms, dicts, errors)
    if errors:
        messagebox.showwarning('Библия', 'Пропущены файлы:\n' + '\n'.join(errors))
    root.mainloop()


if __name__ == '__main__':
    main()
