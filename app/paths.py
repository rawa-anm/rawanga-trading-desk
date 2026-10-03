# Copyright 2026 Andrei Maltsev (Rawanga)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
paths.py — single source of paths and settings for the portable Rawanga Trading Desk build.

No absolute paths to the production host. Everything is resolved as follows:
  1) the RAWANGA_DATA_DIR environment variable (user data directory), if set;
  2) otherwise — the `data/` directory next to the application root (portable mode);
  3) otherwise — %APPDATA%/RawangaTradingDesk (Win) or ~/Library/Application Support/RawangaTradingDesk (Mac).

Copyright (c) 2026 Andrei Maltsev (Rawanga). All rights reserved.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # Frozen build (PyInstaller): resources inside the bundle, data — next to the exe.
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    APP_ROOT = Path(sys.executable).resolve().parent
    STATIC_DIR = BUNDLE_DIR / "static"
    PINE_DIR = BUNDLE_DIR / "strategies"
    DOCS_DIR = BUNDLE_DIR / "docs"
else:
    # Running from source: root — the directory above the app/ package.
    APP_ROOT = Path(__file__).resolve().parent.parent
    STATIC_DIR = APP_ROOT / "static"
    PINE_DIR = APP_ROOT / "strategies"
    DOCS_DIR = APP_ROOT / "docs"


def _default_data_dir() -> Path:
    env = os.environ.get("RAWANGA_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    # Portable: data/ next to the application, if the directory exists or is writable.
    portable = APP_ROOT / "data"
    try:
        portable.mkdir(parents=True, exist_ok=True)
        test = portable / ".write_test"
        test.write_text("ok")
        test.unlink()
        return portable
    except Exception:
        pass
    # Fallback — the OS user directory.
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "RawangaTradingDesk"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home())) / "RawangaTradingDesk"
    else:
        base = Path.home() / ".local" / "share" / "RawangaTradingDesk"
    base.mkdir(parents=True, exist_ok=True)
    return base


DATA_DIR = _default_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Data files.
DB_PATH = DATA_DIR / "tv.db"
SECRETS_PATH = DATA_DIR / "bx_secrets.enc"
SECRET_KEY_PATH = DATA_DIR / "bx_secret.key"
USDTD_HISTORY_PATH = DATA_DIR / "usdtd_history.json"

# ── Application links (About window / footer) ──
SITE_URL = "https://rawanga.es"
PARTNER_URL = "https://bingx.com/partner/rawa/"
COPYRIGHT = "© 2026 Andrei Maltsev · Rawanga AI"
