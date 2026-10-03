# Rawanga Trading Desk

Портативный кроссплатформенный терминал графиков, индикаторов и сигналов
(десктоп-приложение для Windows / macOS / Linux). Локальный сервер на
`127.0.0.1` + веб-интерфейс в браузере. Данные пользователя хранятся рядом с
приложением (`data/`).

- Сайт: https://rawanga.es
- Партнёрская ссылка (BingX): https://bingx.com/partner/rawa/

## Документация

- **Установка и работа (RTFM):** [English](docs/rtfm.en.md) · [Español](docs/rtfm.es.md) · [Русский](docs/rtfm.ru.md)
- **Написание стратегий:** [English](docs/strategies.en.md) · [Español](docs/strategies.es.md) · [Русский](docs/strategies.ru.md)

## Возможности

- Свечные графики, таймфреймы 15m–1M, индикаторы (MA/EMA/RSI/MACD/ATR/Supertrend и др.).
- Источники данных с каскадом фолбэков: BingX → Binance → Bybit → OKX для крипты,
  Yahoo Finance для акций/сырья.
- Редактор стратегий и движок бэктеста.
- Сигналы/вебхуки в Telegram (по желанию).
- Интеграция с биржей BingX (по умолчанию выключена; ключи хранятся зашифрованными).

## Запуск из исходников

```bash
python -m venv .venv
. .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.launcher
```

Откроется браузер на `http://127.0.0.1:<случайный_порт>/`.

Переменные окружения:
- `RAWANGA_DATA_DIR` — каталог данных (по умолчанию `./data`).
- `RAWANGA_HOST` / `RAWANGA_PORT` — адрес/порт (по умолчанию `127.0.0.1` и свободный порт).

## Сборка портативного билда

Локально:

```bash
pip install pyinstaller
pyinstaller rawanga_trading_desk.spec --clean --noconfirm
# результат: dist/RawangaTradingDesk/
```

Через GitHub Actions: пуш тега `v*` → собираются артефакты под Windows x64,
macOS (Intel и Apple Silicon) и Linux (см. `.github/workflows/build.yml`).

> Артефакты из CI **не подписаны**. Пользователю macOS может потребоваться
> `xattr -dr com.apple.quarantine <путь>`; Windows покажет предупреждение
> SmartScreen. Для чистой раздачи нужны сертификаты подписи.

## Структура

```
app/         бэкенд (FastAPI) + движок + лаунчер
static/      веб-интерфейс
strategies/  примеры стратегий
data/        пользовательские данные (создаётся при запуске; НЕ коммитить)
```

## Лицензия

Apache License 2.0 — см. `LICENSE`. Переиспользование разрешено при сохранении
указания авторства и файла `NOTICE`.

Сторонние компоненты — см. `THIRD-PARTY-NOTICES.txt` и `licenses/`.

## Правовые оговорки

⚠️ Проект **не связан** с TradingView, Inc., BingX и другими упомянутыми
сервисами. См. `TRADEMARKS.md`. ПО предоставляется «как есть», **не является
инвестиционной рекомендацией**; торговля — на риск пользователя.
