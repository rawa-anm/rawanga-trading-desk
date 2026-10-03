# RTFM — Rawanga Trading Desk

> Read The Friendly Manual. This document explains what the program is, how to
> install it on a local machine, how to run it on a server, and how to work with
> it. It exists in three languages: `rtfm.en.md`, `rtfm.es.md`, `rtfm.ru.md`.

---

## 0. What this is, and who it is for

**Rawanga Trading Desk** is a portable desktop application for:

- candlestick charts (timeframes 15m, 1h, 4h, 1d, 1w, 1M);
- technical indicators (MA/EMA, RSI, MACD, ATR, Supertrend, Bollinger, Donchian, ADX…);
- writing and back-testing your own strategies in Python;
- trade/trend signals with optional alerts (Telegram and/or e-mail);
- optional automated trading on BingX (futures/swap) — **disabled by default**.

Technically it is a small local web server (FastAPI) plus a browser interface.
When you start the program, it launches the server **on your own computer** and
opens the interface in your browser. Everything runs locally.

> ⚠️ **Intended use: individual, single-user.** There are **no accounts, no
> login, no password for the interface, no separation between users.** Whoever
> can open the program's web address has full control over it — including
> enabling real trading, if you configured it.

---

## 1. Requirements

| | Portable build (recommended) | From source |
|---|---|---|
| Python | not needed | 3.10+ (3.12 tested) |
| Other | — | `pip` |
| OS | Windows 10/11 x64, macOS 12+, Linux x64 | same |
| Network | internet for market data | same |

The portable build is self-contained: it bundles its own Python runtime and all
dependencies. Nothing to install.

---

## 2. Install — portable build (a normal user, own machine)

Download the archive for your OS from the project's Releases page:

- `RawangaTradingDesk-windows-x64.zip`
- `RawangaTradingDesk-macos-x64.tar.gz` (Intel) or `RawangaTradingDesk-macos-arm64.tar.gz` (Apple Silicon)
- `RawangaTradingDesk-linux-x64.tar.gz`

Unpack it anywhere (Desktop, USB stick, `D:\Apps`, `~/Apps`, …). The folder
contains the executable and its runtime.

### Windows

1. Unpack the `.zip`.
2. Run `RawangaTradingDesk\RawangaTradingDesk.exe`.
3. Windows SmartScreen may show "Windows protected your PC" (the build is not
   code-signed). Click **More info → Run anyway**.
4. Your browser opens the interface automatically.

### macOS

1. Unpack the `.tar.gz`.
2. Because the build is not notarized, macOS marks it as quarantined. Clear it:
   ```bash
   xattr -dr com.apple.quarantine /path/to/RawangaTradingDesk
   ```
3. Run the `RawangaTradingDesk` binary inside the folder.
   If macOS still refuses: **System Settings → Privacy & Security → Open Anyway**.
4. The browser opens automatically.

### Linux

```bash
tar xzf RawangaTradingDesk-linux-x64.tar.gz
cd RawangaTradingDesk
chmod +x RawangaTradingDesk
./RawangaTradingDesk
```
The browser opens automatically.

> The console window that appears is the program itself. **Closing it stops the
> program.** Leave it open while you work.

---

## 3. Install — from source (developers)

```bash
git clone <repository-url>
cd rawanga-trading-desk

python -m venv .venv
# Windows:  .venv\Scripts\activate
. .venv/bin/activate

pip install -r requirements.txt
python -m app.launcher
```

The browser opens at `http://127.0.0.1:<random free port>/`.

Environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `RAWANGA_HOST` | `127.0.0.1` | address to bind (localhost only) |
| `RAWANGA_PORT` | `0` (random free port) | fixed port, if you want one |
| `RAWANGA_DATA_DIR` | `./data` (next to the app), else OS app-data dir | where your data is stored |

---

## 4. First run & basic workflow

1. Start the program. The interface opens in your browser.
2. Pick an instrument on the right (e.g. `BTC`), pick a timeframe in the bar
   above the chart (default is **1h**).
3. The chart loads with candles, volume and the selected indicators.
4. Bottom rows: strategy buttons, indicator toggles, "Strategy editor",
   "Strategy docs", webhooks, trading settings.
5. Click an instrument to open its **trade journal** on the right (trades per
   period, win rate, best/worst, P/L).
6. **Strategy editor** (🧩 button): load a sample or write your own Python
   strategy → **Check** → **Compile** → **To chart**. Full reference is in the
   **Strategy docs** button (📘), in your selected interface language.
7. **Interface language**: selector in the top bar (EN / RU / ES). The choice is
   remembered on your machine.

---

## 5. Where your data lives, and backups

All user data is in the **data directory** (by default `./data` next to the
program; on a machine where that folder is not writable, in the OS app-data
folder: `%APPDATA%\RawangaTradingDesk` on Windows,
`~/Library/Application Support/RawangaTradingDesk` on macOS,
`~/.local/share/RawangaTradingDesk` on Linux).

| File | Contents |
|---|---|
| `tv.db` | SQLite database: instruments, cached bars, parameters, journal, settings |
| `bx_secrets.enc` | exchange API keys + alert credentials (encrypted) |
| `bx_secret.key` | the master key for the file above |
| `bot.key` | Telegram bot token (optional) |
| `usdtd_history.json` | auxiliary trend history |

**Backup:** copy the whole data directory. **Move to another machine:** copy the
data directory together with the program folder.

> Never commit or share the data directory: it contains your keys.

---

## 6. Alerts (optional)

Alerts are **off** until you configure them. Both channels are independent; you
can use Telegram, e-mail, both, or none.

### Telegram

1. Create a bot via `@BotFather`, copy its token.
2. Send your bot any message, so it can reply to you; get your chat id via
   `@userinfobot` (or similar).
3. In the app: **Trading settings → Bot token for trade alerts** and
   **Recipient TG id**. Save.
4. Press **✈ Test alert** — you should receive it in Telegram.

### E-mail (to yourself)

The program sends alerts **to a single address — yours**, through your own SMTP
mailbox. It is a personal alert pipe, not a mailing tool: one recipient only,
no lists, no Cc/Bcc.

1. In the app: **Trading settings → E-mail alerts**.
2. Fill SMTP host / port / login / password (for Gmail use an **app password**,
   not your normal password) and the recipient address (your own mailbox).
3. STARTTLS is used for port 587, implicit SSL for port 465.
4. Save, then **✈ Test alert**.

---

## 7. Running on a server (VPS / cloud) — and the security warning

You *can* run it on a server and open it from another machine. But first, read
this carefully.

> ⚠️ **Security — read before hosting anywhere but your own computer**
>
> 1. **The web interface has no authentication.** Anyone who can reach the
>    port can see your charts, change settings, send test alerts, and — if you
>    configured keys — enable and drive **real trading**.
> 2. **Your credentials live on the host.** Exchange API keys and alert
>    credentials are stored Fernet-encrypted in `bx_secrets.enc`, **but the
>    master key `bx_secret.key` sits in the same folder.** For anyone with
>    filesystem access (or anyone who gets a disk snapshot / backup), this is
>    effectively **no protection at all** — treat the keys on a cloud host as
>    stored in the clear.
> 3. Consequently: **do not expose the port to the open internet.** If you must
>    host it remotely, at minimum:
>    - keep it bound to a private network and reach it through a **VPN**
>      (e.g. Tailscale/WireGuard) or an **SSH tunnel**
>      (`ssh -L 8080:127.0.0.1:8080 user@server`);
>    - or put it behind a **reverse proxy with authentication + TLS** and
>      restrict it with a firewall;
>    - encrypt the server disk, and prefer a dedicated key on the exchange with
>      the minimum permissions / no withdrawal right.

### Example: run on a server bound to a fixed port

```bash
# on the server, inside the project (source install)
RAWANGA_HOST=127.0.0.1 RAWANGA_PORT=8080 python -m app.launcher
```

Then reach it from your machine through an SSH tunnel:

```bash
ssh -L 8080:127.0.0.1:8080 user@your-server
# now open http://127.0.0.1:8080/ locally
```

### Example: systemd service (source install)

`/etc/systemd/system/rawanga-trading-desk.service`:

```ini
[Unit]
Description=Rawanga Trading Desk
After=network-online.target

[Service]
User=youruser
WorkingDirectory=/opt/rawanga-trading-desk
Environment=RAWANGA_HOST=127.0.0.1
Environment=RAWANGA_PORT=8080
Environment=RAWANGA_DATA_DIR=/opt/rawanga-trading-desk/data
ExecStart=/opt/rawanga-trading-desk/.venv/bin/python -m app.launcher
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rawanga-trading-desk
```

> Keep `RAWANGA_HOST=127.0.0.1` and reach it via VPN/tunnel. Only change it to
> `0.0.0.0` if you fully understand that you are exposing an **unauthenticated**
> control panel.

---

## 8. Strategy editor

- Open with the **🧩 Strategy editor** button.
- Write Python; the code runs in a restricted sandbox (no `import`, `eval`,
  `exec`, `open`, file/network access, `for`/`while`, dunder access).
- Available API: price series `open/high/low/close/volume`; `inp(...)`;
  indicators `sma, ema, rma, wma, stdev, highest, lowest, change, rsi, macd, bb,
  atr, supertrend, adx, donchian`; `crossover/crossunder`; `nz/na/series`;
  `entry/exit`; `plot/shape/hline`.
- Buttons: **Check** (validate + dry run), **Compile (strategy)** (register in
  the engine), **To chart (indicator)** (draw on the chart), **Remove from
  chart**, **Export strategy**, **Import**.
- **Export/import** uses the `*.rwd.json` file so you can share a strategy.
- Full reference: the **📘 Strategy docs** button (in EN/RU/ES).

---

## 9. Real trading (BingX) — optional, and risky

Real trading is **disabled by default**. To enable it you must: save API keys,
set a fund password, and explicitly toggle live mode. Without all of these, no
order is ever sent.

- Use a dedicated API key with minimal permissions.
- The app trades only the tickers you explicitly add to the "traded tickers" list.
- Trading is on **your** responsibility and **your** capital. The software is
  provided "as is"; it is **not investment advice**.

---

## 10. Update / uninstall

- **Portable:** replace the program folder with a newer version; keep your
  `data/` directory.
- **Source:** `git pull` and `pip install -r requirements.txt`.
- **Uninstall:** delete the program folder and (if you want a clean slate) the
  data directory.

---

## 11. Troubleshooting

| Symptom | Fix |
|---|---|
| Browser didn't open | Open the address printed in the console window manually (`http://127.0.0.1:<port>/`). |
| Windows: "Windows protected your PC" | More info → Run anyway (unsigned build). |
| macOS: "cannot be opened / damaged" | `xattr -dr com.apple.quarantine <path>` (see §2). |
| No data for an instrument | Check your internet connection; try **⟳ Refresh**. |
| Alerts not arriving | Press **✈ Test alert**; check token / chat id / SMTP settings. |
| Port already in use | Set `RAWANGA_PORT` to a free port. |
| Where is my data? | The `data/` folder next to the program (§5). |

---

## 12. License & disclaimers

- Licensed under **Apache License 2.0** — see `LICENSE` / `NOTICE`.
- Third-party components — see `THIRD-PARTY-NOTICES.txt` and `licenses/`.
- Not affiliated with TradingView, BingX or any other mentioned service — see
  `TRADEMARKS.md`.
- The software is provided "as is", **without warranty**; it is **not
  investment advice**. Trading is at your own risk.

---

© 2026 Andrei Maltsev · Rawanga AI · https://rawanga.es
