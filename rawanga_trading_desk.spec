# -*- mode: python ; coding: utf-8 -*-
# Copyright (c) 2026 Andrei Maltsev (Rawanga). All rights reserved.
#
# PyInstaller spec для Rawanga Trading Desk (portable, onedir).
# Сборка:  pyinstaller rawanga_trading_desk.spec --clean --noconfirm
# Результат: dist/RawangaTradingDesk/  (onedir). Данные пользователя — рядом, в data/.

import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Доп. скрытые импорты для uvicorn/fastapi/движка (динамическая загрузка "app.main:app").
hidden = (
    collect_submodules("uvicorn")
    + collect_submodules("fastapi")
    + collect_submodules("starlette")
    + collect_submodules("anyio")
    + collect_submodules("app")
    + ["app.main", "app.launcher", "aiosqlite", "websockets", "httpx", "certifi"]
)

datas = [
    ("static", "static"),
    ("strategies", "strategies"),
    ("docs", "docs"),
] + collect_data_files("certifi") + collect_data_files("fastapi") + collect_data_files("starlette")

a = Analysis(
    ["app/launcher.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "PIL.ImageQt"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RawangaTradingDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="RawangaTradingDesk",
)
