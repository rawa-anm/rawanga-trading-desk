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
"""instruments.py — list of instruments and categories (extended, 85).

kind:
  crypto    -> cascade BingX -> Binance -> Bybit -> OKX (+Yahoo)
  stock     -> Yahoo Finance (stocks/ETF/futures/forex)
  index     -> Yahoo Finance (indices)
  dominance -> CoinGecko /global (dominance, accumulating points in JSON)
"""

INSTRUMENTS = {
    # ── CRYPTO (BingX first) ──────────────────────────────────────
    "BTC":  ("crypto", "BTC-USD",  "crypto", "Bitcoin"),
    "ETH":  ("crypto", "ETH-USD",  "crypto", "Ethereum"),
    "SOL":  ("crypto", "SOL-USD",  "crypto", "Solana"),
    "BNB":  ("crypto", "BNB-USD",  "crypto", "BNB"),
    "XRP":  ("crypto", "XRP-USD",  "crypto", "XRP"),
    "DOGE": ("crypto", "DOGE-USD", "crypto", "Dogecoin"),
    "ADA":  ("crypto", "ADA-USD",  "crypto", "Cardano"),
    "AVAX": ("crypto", "AVAX-USD", "crypto", "Avalanche"),
    "LINK": ("crypto", "LINK-USD", "crypto", "Chainlink"),
    "DOT":  ("crypto", "DOT-USD",  "crypto", "Polkadot"),
    "TRX":  ("crypto", "TRX-USD",  "crypto", "TRON"),
    "LTC":  ("crypto", "LTC-USD",  "crypto", "Litecoin"),
    "XMR":  ("crypto", "XMR-USD",  "crypto", "Monero"),
    "ZEC":  ("crypto", "ZEC-USD",  "crypto", "Zcash"),
    "DASH": ("crypto", "DASH-USD", "crypto", "Dash"),
    "SUI":  ("crypto", "SUI-USD",  "crypto", "Sui"),
    "AAVE": ("crypto", "AAVE-USD", "crypto", "Aave"),
    "STRK": ("crypto", "STRK-USD", "crypto", "Starknet"),
    "OP":   ("crypto", "OP-USD",   "crypto", "Optimism"),
    "POL":  ("crypto", "POL-USD",  "crypto", "Polygon"),
    "UNI":  ("crypto", "UNI-USD",  "crypto", "Uniswap"),
    "FET":  ("crypto", "FET-USD",  "crypto", "Artificial Superintelligence"),
    "PEPE": ("crypto", "PEPE-USD", "crypto", "Pepe"),
    "ENS":  ("crypto", "ENS-USD",  "crypto", "Ethereum Name Service"),
    "PUMP": ("crypto", "PUMP-USD", "crypto", "Pump.fun"),
    "TIA":  ("crypto", "TIA-USD",  "crypto", "Celestia"),
    "JUP":  ("crypto", "JUP-USD",  "crypto", "Jupiter"),
    "ARB":  ("crypto", "ARB-USD",  "crypto", "Arbitrum"),
    "NEAR": ("crypto", "NEAR-USD", "crypto", "NEAR Protocol"),
    "WLD":  ("crypto", "WLD-USD",  "crypto", "Worldcoin"),
    "GRAM": ("crypto", "GRAM-USD", "crypto", "Gram"),
    # ── FUTURES / FOREX (Yahoo) ──────────────────────────────────
    "GOLD":   ("stock", "GC=F",     "futures", "Gold Futures"),
    "SILVER": ("stock", "SI=F",     "futures", "Silver Futures"),
    "NGAS":   ("stock", "NG=F",     "futures", "US Natural Gas"),
    "COPPER": ("stock", "HG=F",     "futures", "Copper Futures"),
    "COCOA":  ("stock", "CC=F",     "futures", "Cocoa Futures"),
    "SUGAR":  ("stock", "SB=F",     "futures", "Sugar #11"),
    "EUR":    ("stock", "EURUSD=X", "futures", "Euro / USD"),
    "JPY":    ("stock", "JPY=X",    "futures", "Japanese Yen / USD"),
    "BRENT":  ("stock", "BZ=F",     "futures", "Brent Crude Oil"),
    "WTI":    ("stock", "CL=F",     "futures", "WTI Crude Oil"),
    # ── STOCKS AND ETF (Yahoo) ────────────────────────────────────────
    "TLT":  ("stock", "TLT",  "stocks", "iShares 20+ Treasury"),
    "IBIT": ("stock", "IBIT", "stocks", "iShares Bitcoin Trust"),
    "ECAT": ("stock", "ECAT", "stocks", "Ecolab?"),
    "MSFT": ("stock", "MSFT", "stocks", "Microsoft"),
    "NVDA": ("stock", "NVDA", "stocks", "NVIDIA"),
    "AMZN": ("stock", "AMZN", "stocks", "Amazon"),
    "GOOGL":("stock", "GOOGL","stocks", "Alphabet"),
    "META": ("stock", "META", "stocks", "Meta Platforms"),
    "TSLA": ("stock", "TSLA", "stocks", "Tesla"),
    "BBVA": ("stock", "BBVA", "stocks", "Banco Bilbao Vizcaya"),
    "SQ":   ("stock", "XYZ",  "stocks", "Block Inc (SQ)"),
    "MSTR": ("stock", "MSTR", "stocks", "MicroStrategy"),
    "BMNR": ("stock", "BMNR", "stocks", "BitMine Immersion"),
    "CRCL": ("stock", "CRCL", "stocks", "Circle Internet"),
    "QUBT": ("stock", "QUBT", "stocks", "Quantum Computing"),
    "IBM":  ("stock", "IBM",  "stocks", "IBM"),
    "CRM":  ("stock", "CRM",  "stocks", "Salesforce"),
    "NBIS": ("stock", "NBIS", "stocks", "Nebius Group"),
    "INTC": ("stock", "INTC", "stocks", "Intel"),
    "AMD":  ("stock", "AMD",  "stocks", "AMD"),
    "PLTR": ("stock", "PLTR", "stocks", "Palantir"),
    "CROX": ("stock", "CROX", "stocks", "Crocs"),
    "RIO":  ("stock", "RIO",  "stocks", "Rio Tinto"),
    "ALB":  ("stock", "ALB",  "stocks", "Albemarle"),
    "UEC":  ("stock", "UEC",  "stocks", "Uranium Energy"),
    "FCX":  ("stock", "FCX",  "stocks", "Freeport-McMoRan"),
    "APA":  ("stock", "APA",  "stocks", "APA Corp"),
    "VLO":  ("stock", "VLO",  "stocks", "Valero Energy"),
    "XOM":  ("stock", "XOM",  "stocks", "Exxon Mobil"),
    "RUN":  ("stock", "RUN",  "stocks", "Sunrun"),
    "NFLX": ("stock", "NFLX", "stocks", "Netflix"),
    "UAL":  ("stock", "UAL",  "stocks", "United Airlines"),
    "BIIB": ("stock", "BIIB", "stocks", "Biogen"),
    "MRNA": ("stock", "MRNA", "stocks", "Moderna"),
    "AMGN": ("stock", "AMGN", "stocks", "Amgen"),
    "BABA": ("stock", "BABA", "stocks", "Alibaba"),
    "JD":   ("stock", "JD",   "stocks", "JD.com"),
    "BIDU": ("stock", "BIDU", "stocks", "Baidu"),
    "AAPL": ("stock", "AAPL", "stocks", "Apple"),
    # ── INDICES ────────────────────────────────────────────────────
    "NDX":  ("index", "^NDX",  "index", "Nasdaq 100"),
    "DJI":  ("index", "^DJI",  "index", "Dow Jones"),
    # ── TREND INDICATOR (Supertrend) ───────────────────────────
    "VIX":   ("index",     "^VIX",   "trend", "VIX Volatility Index"),
    "SPX":   ("index",     "^GSPC",  "trend", "S&P 500"),
    "USDTD": ("dominance", "USDT.D", "trend", "USDT Dominance"),
}


def resolve(symbol: str) -> dict:
    s = symbol.upper()
    if s not in INSTRUMENTS:
        raise KeyError(f"unknown instrument {symbol}")
    kind, ysym, cat, title = INSTRUMENTS[s]
    return {"symbol": s, "kind": kind, "yahoo": ysym, "category": cat, "title": title}


def all_instruments() -> list[dict]:
    return [resolve(s) for s in INSTRUMENTS]
