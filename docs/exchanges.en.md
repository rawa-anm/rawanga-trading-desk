<!--
  Copyright 2026 Andrei Maltsev (Rawanga)

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
-->

# Switching between exchanges — Rawanga Trading Desk

> This document explains how the two trading backends (BingX and Hyperliquid)
> coexist, how to switch between them safely, and what happens to your
> positions when you do.
> Available in three languages: `exchanges.en.md`, `exchanges.es.md`,
> `exchanges.ru.md`.

---

## 0. The one rule that matters

**Exactly ONE exchange is active at any moment.**

The app always sits on one backend. There is no "trade on both" mode, and this
is deliberate: two exchanges mean two balances, two position sets and two
sources of truth for a single trade decision.

---

## 1. How the two backends differ

They are not variations of each other — the protocols are incompatible, which
is why there are two separate drivers rather than one with a switch inside.

| | BingX (`exchange.py`) | Hyperliquid (`exchange_hl.py`) |
|---|---|---|
| Signature | HMAC-SHA256 | EIP-712 + msgpack |
| Credentials | API key + secret key | Agent (API wallet) private key + master account address |
| Position mode | Hedge (LONG/SHORT) | One-way only |
| Order type | MARKET | Aggressive IOC limit (HL has no MARKET) |
| Min. notional | ~5 USDT | 10 USDT |
| Symbol | `BTC-USDT` | `BTC` + integer asset index |
| Balance source | `marginSummary.accountValue` | `spotClearinghouseState` when the account is unified |

The BingX driver is unchanged from the version that was proven in real trading.
The Hyperliquid driver is a separate module on purpose: editing the working
BingX code to accommodate a different protocol would put the proven path at
risk.

---

## 2. Where the keys live

Each exchange has its **own** encrypted file in the data directory:

| File | Contents |
|---|---|
| `bx_secrets.enc` + `bx_secret.key` | BingX API key, secret, fund password, alert settings |
| `hl_secrets.enc` + `hl_secret.key` | Hyperliquid master address, agent private key, environment |

They are separate on purpose: a leak of one file does not expose the other
exchange. Both are encrypted with Fernet; the master keys are created with mode
`0600` on first use.

Telegram and e-mail alert credentials are **shared** — they are stored in the
BingX file regardless of which exchange is active, because a notification is a
notification.

---

## 3. Setting up Hyperliquid keys (the common trap)

Trading on Hyperliquid does **not** use your account's private key. It uses an
**API wallet**, also called an agent wallet:

1. Go to `https://app.hyperliquid.xyz/API`.
2. Create an **API wallet / agent** and copy the private key it generates.
3. In the app: **Trading settings → Exchange = Hyperliquid**.
4. Paste:
   - **Master account address** — your main account (`0x…`), the one holding the funds;
   - **Agent wallet private key** — the key from step 2;
   - **Environment** — Mainnet or Testnet.
5. Press **Check connection**. It is read-only; no orders are sent.

> ⚠️ **The classic mistake:** pasting the *agent's* address instead of the
> master account's. The API then returns an empty account: no balance, no
> positions, no error. If "Check connection" reports an empty account, this is
> almost always why.

The private key is never logged and never shown in the interface — only a mask.

---

## 4. Installing the Hyperliquid SDK

The Hyperliquid driver needs an optional dependency set. The base app runs
without it; BingX-only users do not need it.

```bash
pip install -r requirements-hl.txt
```

Until it is installed, any attempt to place an HL order fails with a clear
message telling you to install it — the rest of the app keeps working.

---

## 5. Switching the exchange

In the app: **💹 Trading settings → Exchange** → pick the backend → **Save**.

### What happens on switch

- The selected driver becomes active immediately; no restart is required.
- The key panel changes to match the selected exchange.
- If **real trading is OFF**, the switch applies silently.

### If real trading is ON

Switching requires an explicit confirmation, and the app tells you why:

> **Close all positions on the current exchange before switching: positions on
> the inactive exchange are not tracked by the app.**

This is not a formality. The app watches positions only on the active exchange.
A position left open on the other one keeps running on the exchange, but the
journal, the balance card and the signal logic can no longer see it. Nothing
will close it for you.

**Correct order of operations:**

1. Close every open position on the current exchange (in the app or on the
   exchange itself).
2. Confirm that the position list is empty.
3. Switch the exchange.
4. Verify the balance and positions in **Trading settings**.

---

## 6. What stays and what does not

| | On switch |
|---|---|
| Trade journal (historical trades) | Stays — it is computed from price data, not from the exchange |
| Strategy parameters | Stays |
| Webhooks and alerts | Stay, shared by both |
| Traded ticker list | Stays, but symbols are re-derived for the new backend |
| Balance and PnL card | Shows the **new** exchange; the previous one's history is not merged |
| Open positions | **Not transferred, not closed, not tracked** |

PnL is computed per exchange from that exchange's own income history. The two
are never summed: different fee models and different funding schedules would
make the total meaningless.

---

## 7. Symbol mapping

Most tickers match across exchanges, but some do not:

- **PEPE** on Hyperliquid is `kPEPE` (price and size ×1000). The driver handles
  this internally; you keep entering `PEPE`.
- **GRAM** on Hyperliquid is `GRAM`, on BingX `GRAMTON`.
- Tokenised assets (e.g. gold as XAUT) exist on BingX's swap listing but have
  **no** Hyperliquid perp — such a ticker can be traded on BingX only.

If a symbol is unavailable on the active exchange, order placement fails with
an error naming the symbol. Nothing is sent silently.

---

## 8. Rolling back

To return to the previous exchange:

1. Close positions on the current one.
2. Switch back.
3. Save.

The previous exchange's keys were never deleted, so nothing needs to be
re-entered. If you want to remove them, **Delete keys** clears the keys of the
**active** exchange only.

---

## 9. Reference links

- BingX partner link: <https://bingx.com/partner/rawa/>
- Hyperliquid partner link: <https://app.hyperliquid.xyz/join/RAWA>
- Hyperliquid API wallet page: <https://app.hyperliquid.xyz/API>

> Both links are referral links. They do not change fees for the software and
> are not required for it to work.

---

*Real trading is disabled by default and is done entirely at your own risk.
The software is provided "as is" and is not investment advice.*
