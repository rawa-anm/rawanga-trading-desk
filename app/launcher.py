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
launcher.py — entry point of the portable Rawanga Trading Desk application.

Starts a local server (uvicorn) on 127.0.0.1 with a random free port
and opens a browser window/tab. Works both from source and from a frozen
build (PyInstaller). Data — next to the application (data/), see app/paths.py.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _open_when_ready(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", int(url.rsplit(":", 1)[1].split("/")[0])), timeout=1):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(0.3)
    webbrowser.open(url)


def main() -> int:
    # The application is imported as the app.* package — make sure the root is in sys.path.
    host = os.environ.get("RAWANGA_HOST", "127.0.0.1")
    port = int(os.environ.get("RAWANGA_PORT", "0")) or _free_port()
    url = f"http://{host}:{port}/"

    print(f"Rawanga Trading Desk — starting on {url}")
    print("To exit, close this window (Ctrl+C).")

    threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()

    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
