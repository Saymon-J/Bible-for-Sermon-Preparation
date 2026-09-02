# -*- coding: utf-8 -*-
"""Версия и пути приложения (общее состояние у скрипта и exe)."""
import sys
from pathlib import Path


APP_VERSION = '1.7.0'
FROZEN = getattr(sys, 'frozen', False)  # PyInstaller exe: пути — от файла exe, не от распаковки
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
ROOT_DIR = APP_DIR if FROZEN else APP_DIR.parent
MODULE_DIR = ROOT_DIR / 'module'
MODULE_SUBS = ('переводы', 'словари', 'комментарии')
CONFIG_PATH = ROOT_DIR / 'app' / 'config.json'  # общее состояние у скрипта и exe
LOGO_PATH = ROOT_DIR / 'src' / 'logo2.png'