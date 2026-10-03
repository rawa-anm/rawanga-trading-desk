# Rawanga Trading Desk

Portable, cross-platform charting / indicator / signal terminal (desktop app for
Windows / macOS / Linux). A local server on `127.0.0.1` plus a browser UI. Your
data is stored next to the application (`data/`).

- Website: https://rawanga.es
- Partner link (BingX): https://bingx.com/partner/rawa/
- **Download (prebuilt, portable):** [latest release](https://github.com/rawa-anm/rawanga-trading-desk/releases/latest)
  — Windows x64 (`.zip`), macOS Intel / Apple Silicon (`.tar.gz`), Linux x64 (`.tar.gz`).

> Intended use: **individual, single-user**. There is no authentication and no
> multi-user separation — see the RTFM guide before hosting anywhere.

## Documentation

- **Installation & usage (RTFM):** [English](docs/rtfm.en.md) · [Español](docs/rtfm.es.md) · [Русский](docs/rtfm.ru.md)
- **Writing strategies:** [English](docs/strategies.en.md) · [Español](docs/strategies.es.md) · [Русский](docs/strategies.ru.md)

## Features

- Candlestick charts, timeframes 15m–1M, indicators (MA/EMA/RSI/MACD/ATR/Supertrend and more).
- Data sources with a fallback cascade: BingX → Binance → Bybit → OKX for crypto,
  Yahoo Finance for stocks/commodities.
- Strategy editor and back-testing engine (Python, sandboxed).
- Signals / webhooks to Telegram (optional).
- Optional e-mail alerts to your own mailbox (SMTP; personal, single recipient).
- BingX exchange integration (disabled by default; keys are stored encrypted).

## Run from source

```bash
python -m venv .venv
. .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.launcher
```

The browser opens at `http://127.0.0.1:<random free port>/`.

Environment variables:

- `RAWANGA_DATA_DIR` — data directory (default `./data`).
- `RAWANGA_HOST` / `RAWANGA_PORT` — address/port (default `127.0.0.1` and a free port).

## Build the portable bundle

Locally:

```bash
pip install pyinstaller
pyinstaller rawanga_trading_desk.spec --clean --noconfirm
# result: dist/RawangaTradingDesk/
```

Prebuilt portable bundles are published on the [Releases](https://github.com/rawa-anm/rawanga-trading-desk/releases)
page for every `v*` tag: Windows x64, macOS Intel, macOS Apple Silicon, Linux x64
(built by GitHub Actions — see `.github/workflows/build.yml`). Download, unpack, run.

> CI artifacts are **not code-signed**. macOS users may need
> `xattr -dr com.apple.quarantine <path>`; Windows will show a SmartScreen
> warning. Clean distribution requires signing certificates.

## Layout

```
app/         backend (FastAPI) + engine + launcher
static/      web interface
strategies/  sample strategies
docs/        installation guide (RTFM) and strategy docs (EN/ES/RU)
data/        user data (created at runtime; do NOT commit)
```

## License

Apache License 2.0 — see `LICENSE`. Reuse is permitted provided you keep the
attribution and the `NOTICE` file.

Third-party components — see `THIRD-PARTY-NOTICES.txt` and `licenses/`.

## Legal notes

⚠️ This project is **not affiliated** with TradingView, Inc., BingX or any other
mentioned service. See `TRADEMARKS.md`. The software is provided "as is", is
**not investment advice**; trading is at the user's own risk.
