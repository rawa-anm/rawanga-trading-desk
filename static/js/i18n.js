/*
 * Copyright 2026 Andrei Maltsev (Rawanga)
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * i18n.js — interface localisation. Default: English. Switchable to Russian
 * or Spanish; the choice is stored in localStorage and re-applied on load.
 */
(function () {
  'use strict';

  const DICT = {
    en: {
      'lang.label': 'Language',
      'status.loading': 'loading…',
      'brand.trade': 'Trade on BingX',
      'btn.refresh': '⟳ Refresh',
      'tt.theme': 'Day/Night',
      'tt.about': 'About',

      'ind.candles': 'candles',
      'ind.volume': 'volume',
      'ind.hvol': 'volume (horiz.)',
      'ind.vma': 'Vol MA20',
      'ind.supertrend': 'Supertrend',
      'ind.donchian': 'Donchian',
      'ind.bollinger': 'Bollinger',

      'bar.trades': 'trades:',
      'bar.strategy': 'strategy:',
      'btn.params': '⚙ parameters',
      'btn.webhooks': '🔔 webhooks',
      'btn.editor': '🧩 Strategy editor',
      'btn.docs': '📘 Strategy docs',

      'bar.trading': 'trading:',
      'trade.live': 'real BingX trading',
      'btn.tradeSettings': '💹 settings',
      'btn.tickers': '📋 traded tickers',
      'acct.balance': 'balance: —',

      'btn.cancel': 'Cancel',
      'btn.save': 'Save',
      'btn.close': 'Close',
      'btn.add': 'Add',
      'btn.ok': 'OK',

      'params.title': 'Strategy parameters',
      'params.scope': 'Saved for: {scope}  (★ — save for this instrument only)',
      'params.main': 'strategy parameters',
      'params.risk': 'exits (optional): stop always on · TP and trailing by checkbox',
      'params.tp': 'Take-profit %',
      'params.trail': 'Trailing stop %',

      'wh.title': 'Webhooks',
      'wh.strategy': 'Strategy',
      'wh.symbol': 'Instrument ("*" — all)',
      'wh.chatId': 'Chat ID (empty — your private)',
      'wh.chatPh': 'your Chat ID',
      'wh.thread': 'Thread ID (optional, for topics)',
      'wh.enabled': 'On',
      'wh.yes': 'yes',
      'wh.no': 'no',
      'wh.none': 'no webhooks',
      'wh.edit': 'Edit',
      'wh.del': 'Delete',
      'wh.delConfirm': 'Delete webhook #{id} ({strategy} · {symbol})?',
      'wh.saved': 'Saved',
      'wh.tf': 'TF',

      'editor.title': 'Strategy editor (Python)',
      'editor.hint': 'Available: open/high/low/close/volume · inputs inp(name, default, title, type) · indicators sma/ema/rma/rsi/macd/atr/supertrend/adx/donchian/bb · crossover/crossunder · signals entry(\'long\'|\'short\', cond) and exit(cond) · drawing plot/shape/hline. Combine conditions with & | ~.',
      'editor.name': 'Strategy name',
      'editor.namePh': 'My Strategy',
      'editor.code': 'Strategy code (Python)',
      'editor.check': '🔎 Check',
      'editor.compile': '⚙ Compile (strategy)',
      'editor.toChart': '🧷 To chart (indicator)',
      'editor.clear': '✖ Remove from chart',
      'editor.export': '⬇ Export strategy',
      'editor.import': '⬆ Import',
      'editor.sample': 'Sample:',
      'editor.saved': 'Saved strategies:',
      'editor.choose': '— choose —',
      'editor.samplePh': '— sample —',
      'editor.checkOk': '✓ check passed',
      'editor.line': 'line {n}: {msg}',
      'editor.dryrun': 'dry run: {symbol} {tf}, {bars} bars · long={longs} short={shorts} exit={exits} · trades {trades}{open}',
      'editor.open': ' (open position)',
      'editor.params': 'parameters: {list}',
      'editor.compiled': '✅ strategy “{title}” compiled and registered (key <b>{key}</b>)',
      'editor.imported': '✅ imported: “{title}” (key {key})',
      'editor.checkFail': 'Check failed — compilation cancelled',
      'editor.needName': 'Please enter a strategy name.',
      'editor.noBars': 'no bars for dry run',
      'editor.added': '✅ added to chart: lines {lines}, markers {shapes}, levels {hlines}',
      'editor.importBad': 'File not recognised (expected .rwd.json)',
      'editor.importNoSource': 'No "source" field in file',
      'editor.importErr': 'Import error',

      'docs.title': 'Writing trading strategies',

      'tickers.title': 'Traded tickers (trading only for added ones)',
      'tickers.add': 'Add',
      'tickers.choose': '— choose instrument —',
      'tickers.empty': 'list is empty — no instrument is traded',
      'tickers.toggle': 'on/off',
      'tickers.remove': 'Remove {sym} from traded?',
      'tickers.notAdded': 'Not added: ',

      'inst.title': 'Add instrument',
      'inst.ticker': 'Ticker',
      'inst.name': 'Name',
      'inst.category': 'Category',
      'inst.dataType': 'Data type',
      'inst.kindCrypto': 'crypto (BingX/Binance/Bybit/OKX)',
      'inst.kindStock': 'exchange/commodity (Yahoo)',
      'inst.yahoo': 'Yahoo symbol (for stocks/commodities)',
      'cat.crypto': 'Cryptocurrencies',
      'cat.stocks': 'Stocks',
      'cat.energy': 'Energy',
      'cat.metals': 'Metals',
      'cat.indices': 'Indices',

      'trade.title': 'BingX trading (futures / swap)',
      'trade.apiKey': 'API Key',
      'trade.secret': 'Secret Key',
      'trade.fundPw': 'Fund password (required for real trading)',
      'trade.fundPwPh': 'confirmation to enable live',
      'trade.env': 'Environment',
      'trade.envLive': 'Live',
      'trade.envVst': 'Simulation (testnet VST)',
      'trade.lev': 'Leverage (1–125)',
      'trade.pct': '% of balance per position',
      'trade.notifyToken': 'Bot token for trade alerts',
      'trade.notifyChat': 'Recipient TG id (private)',
      'trade.mailTitle': 'E-mail alerts (optional)',
      'trade.mailNote': 'Personal alerts only — e-mails go to this single address.',
      'trade.smtpHostPh': 'smtp.example.com',
      'trade.smtpTls': 'STARTTLS',
      'trade.smtpUser': 'SMTP login',
      'trade.smtpPass': 'SMTP password / app password',
      'trade.mailTo': 'Send alerts to (e-mail)',
      'trade.testMailSent': 'E-mail sent to {to}',
      'trade.keepPh': 'leave empty to keep unchanged',
      'trade.clearKeys': 'Delete keys',
      'trade.testNotify': '✈ Test alert',
      'trade.keysOk': '✅ keys set ({mask}){fund}',
      'trade.fundPwSet': ' · fund password set',
      'trade.keysNo': '⚠️ keys NOT set',
      'trade.testSent': 'Test sent to {chat}',
      'trade.testFail': 'Not sent: {err}',
      'trade.clearConfirm': 'Delete BingX API keys? Real trading will be stopped.',
      'acct.balanceLine': 'balance: {eq} USDT · PnL(real): {pnl}',
      'acct.tooltip': 'unrealized PnL: {pnl} · available margin: {margin}',

      'about.tagline': 'Portable charting and signals terminal.',
      'about.site': 'Site:',
      'about.partner': 'Partner link:',
      'about.license': 'License: Apache License 2.0. Software is provided “as is”, not investment advice.',
      'about.importrisk': '⚠️ Imported strategies (.rwd.json) are third-party code, not vetted by the author. Import only from trusted sources and review the source first — the sandbox limits what imported code can do, but does not guarantee it is safe, correct or profitable.',
      'about.thirdparty': 'Third-party components: TradingView Lightweight Charts™ (Apache-2.0) and others — see THIRD-PARTY-NOTICES.txt.',

      'misc.loading': '{sym} · loading…',
      'misc.loadingOpt': '— loading —',
      'misc.bars': '{symbol} · {title} · {count} candles',
      'misc.source': 'source: {src}',
      'misc.lastSignal': 'last signal: {side} @ {close} · entry {entry} · stop {stop}',
      'misc.entry': 'entry',
      'misc.exit': 'exit',
      'misc.add': 'add',
      'misc.delete': 'delete',
      'misc.delConfirm': 'Delete {sym}?',
      'misc.noSave': 'Not saved: ',
      'misc.failed': 'failed: ',

      'journal.title': 'Journal: {sym}',
      'journal.loadErr': 'load error',
      'journal.openPos': '📌 OPEN:',
      'journal.entry': 'entry: {dt} · stop {stop} ({pct}%)',
      'journal.noTrades': 'no trades for the period',
      'journal.plPeriod': 'P/L for the period',
      'journal.trades': '{n} trades',
      'journal.winrate': 'win rate',
      'journal.bestWorst': 'best / worst',
      'period.current_month': 'current month',
      'period.month': 'last month',
      'period.year': 'year',
      'period.all': 'all',
    },

    ru: {
      'lang.label': 'Язык',
      'status.loading': 'загрузка…',
      'brand.trade': 'Торговать на BingX',
      'btn.refresh': '⟳ Обновить',
      'tt.theme': 'День/ночь',
      'tt.about': 'О программе',

      'ind.candles': 'свечи',
      'ind.volume': 'объём',
      'ind.hvol': 'объём (гор.)',
      'ind.vma': 'Vol MA20',
      'ind.supertrend': 'Supertrend',
      'ind.donchian': 'Donchian',
      'ind.bollinger': 'Bollinger',

      'bar.trades': 'сделки:',
      'bar.strategy': 'стратегия:',
      'btn.params': '⚙ параметры',
      'btn.webhooks': '🔔 вебхуки',
      'btn.editor': '🧩 Редактор стратегий',
      'btn.docs': '📘 Документация',

      'bar.trading': 'торговля:',
      'trade.live': 'реальная торговля BingX',
      'btn.tradeSettings': '💹 настройки',
      'btn.tickers': '📋 торгуемые тикеры',
      'acct.balance': 'баланс: —',

      'btn.cancel': 'Отмена',
      'btn.save': 'Сохранить',
      'btn.close': 'Закрыть',
      'btn.add': 'Добавить',
      'btn.ok': 'OK',

      'params.title': 'Параметры стратегии',
      'params.scope': 'сохраняется для: {scope}  (★ — сохранить только для этого)',
      'params.main': 'основные параметры стратегии',
      'params.risk': 'выходы (опционально):  стоп всегда вкл. · ТП и трейлинг — по галочке',
      'params.tp': 'Тейк-профит %',
      'params.trail': 'Трейлинг-стоп %',

      'wh.title': 'Вебхуки',
      'wh.strategy': 'Стратегия',
      'wh.symbol': 'Инструмент ("*" — все)',
      'wh.chatId': 'Chat ID (пусто — твой приват)',
      'wh.chatPh': 'ваш Chat ID',
      'wh.thread': 'Thread ID (опционально, для тредов)',
      'wh.enabled': 'Вкл',
      'wh.yes': 'да',
      'wh.no': 'нет',
      'wh.none': 'вебхуков нет',
      'wh.edit': 'Редактировать',
      'wh.del': 'Удалить',
      'wh.delConfirm': 'Удалить вебхук #{id} ({strategy} · {symbol})?',
      'wh.saved': 'Сохранить',
      'wh.tf': 'ТФ',

      'editor.title': 'Редактор стратегий (Python)',
      'editor.hint': 'Доступно: open/high/low/close/volume · входы inp(name, default, title, type) · индикаторы sma/ema/rma/rsi/macd/atr/supertrend/adx/donchian/bb · crossover/crossunder · сигналы entry(\'long\'|\'short\', cond) и exit(cond) · графики plot/shape/hline. Условия соединяйте через & | ~.',
      'editor.name': 'Имя стратегии',
      'editor.namePh': 'My Strategy',
      'editor.code': 'Код стратегии (Python)',
      'editor.check': '🔎 Проверить',
      'editor.compile': '⚙ Компилировать (стратегия)',
      'editor.toChart': '🧷 На график (индикатор)',
      'editor.clear': '✖ Убрать с графика',
      'editor.export': '⬇ Экспорт стратегии',
      'editor.import': '⬆ Импорт',
      'editor.sample': 'Сэмпл:',
      'editor.saved': 'Сохранённые стратегии:',
      'editor.choose': '— выбрать —',
      'editor.samplePh': '— сэмпл —',
      'editor.checkOk': '✓ проверка пройдена',
      'editor.line': 'строка {n}: {msg}',
      'editor.dryrun': 'пробный прогон: {symbol} {tf}, {bars} бар · long={longs} short={shorts} exit={exits} · сделок {trades}{open}',
      'editor.open': ' (есть открытая)',
      'editor.params': 'параметры: {list}',
      'editor.compiled': '✅ стратегия «{title}» скомпилирована и зарегистрирована (ключ <b>{key}</b>)',
      'editor.imported': '✅ импортировано: «{title}» (ключ {key})',
      'editor.checkFail': 'Проверка не пройдена — компиляция отменена',
      'editor.needName': 'Укажите имя стратегии.',
      'editor.noBars': 'нет баров для пробного прогона',
      'editor.added': '✅ на график добавлено: линий {lines}, маркеров {shapes}, горизонтов {hlines}',
      'editor.importBad': 'Файл не распознан (ожидается .rwd.json)',
      'editor.importNoSource': 'В файле нет поля source',
      'editor.importErr': 'ошибка импорта',

      'docs.title': 'Написание торговых стратегий',

      'tickers.title': 'Торгуемые тикеры (торговля только по добавленным)',
      'tickers.add': 'Добавить',
      'tickers.choose': '— выбрать инструмент —',
      'tickers.empty': 'список пуст — торговля ни по чему не идёт',
      'tickers.toggle': 'вкл/выкл',
      'tickers.remove': 'Убрать {sym} из торгуемых?',
      'tickers.notAdded': 'Не добавлено: ',

      'inst.title': 'Добавить инструмент',
      'inst.ticker': 'Тикер',
      'inst.name': 'Название',
      'inst.category': 'Категория',
      'inst.dataType': 'Тип данных',
      'inst.kindCrypto': 'крипта (BingX/Binance/Bybit/OKX)',
      'inst.kindStock': 'биржа/сырьё (Yahoo)',
      'inst.yahoo': 'Yahoo-символ (для акций/сырья)',
      'cat.crypto': 'Криптовалюты',
      'cat.stocks': 'Акции',
      'cat.energy': 'Энергия',
      'cat.metals': 'Металлы',
      'cat.indices': 'Индексы',

      'trade.title': 'Торговля BingX (фьючерсы / swap)',
      'trade.apiKey': 'API Key',
      'trade.secret': 'Secret Key',
      'trade.fundPw': 'Фонд-пароль (обязателен для реальной торговли)',
      'trade.fundPwPh': 'подтверждение включения реала',
      'trade.env': 'Среда',
      'trade.envLive': 'Реальная (live)',
      'trade.envVst': 'Симуляция (testnet VST)',
      'trade.lev': 'Плечо (1–125)',
      'trade.pct': '% входа от баланса на одну позицию',
      'trade.notifyToken': 'Токен бота для оповещений о сделках',
      'trade.notifyChat': 'TG id получателя оповещений (приват)',
      'trade.mailTitle': 'Email-оповещения (опционально)',
      'trade.mailNote': 'Только личные оповещения — письма идут на этот единственный адрес.',
      'trade.smtpHostPh': 'smtp.example.com',
      'trade.smtpTls': 'STARTTLS',
      'trade.smtpUser': 'Логин SMTP',
      'trade.smtpPass': 'Пароль SMTP / app-пароль',
      'trade.mailTo': 'Слать оповещения на email',
      'trade.testMailSent': 'Письмо отправлено на {to}',
      'trade.keepPh': 'оставь пустым, чтобы не менять',
      'trade.clearKeys': 'Удалить ключи',
      'trade.testNotify': '✈ Тест оповещения',
      'trade.keysOk': '✅ ключи заданы ({mask}){fund}',
      'trade.fundPwSet': ' · фонд-пароль есть',
      'trade.keysNo': '⚠️ ключи НЕ заданы',
      'trade.testSent': 'Тест отправлен в {chat}',
      'trade.testFail': 'Не отправлено: {err}',
      'trade.clearConfirm': 'Удалить API-ключи BingX? Реальная торговля будет остановлена.',
      'acct.balanceLine': 'баланс: {eq} USDT · PnL(реал.): {pnl}',
      'acct.tooltip': 'нереал. PnL: {pnl} · доступно маржи: {margin}',

      'about.tagline': 'Портативный терминал графиков и сигналов.',
      'about.site': 'Сайт:',
      'about.partner': 'Партнёрская ссылка:',
      'about.license': 'Лицензия: Apache License 2.0. ПО предоставляется «как есть», не является инвестиционной рекомендацией.',
      'about.importrisk': '⚠️ Импортированные стратегии (.rwd.json) — чужой код, не проверенный автором. Импортируй только из источников, которым доверяешь, и сначала изучи поле source — песочница ограничивает возможности импортированного кода, но не гарантирует его безопасность, корректность или прибыльность.',
      'about.thirdparty': 'Сторонние компоненты: TradingView Lightweight Charts™ (Apache-2.0) и др. — см. THIRD-PARTY-NOTICES.txt.',

      'misc.loading': '{sym} · загрузка…',
      'misc.bars': '{symbol} · {title} · {count} свечей',
      'misc.source': 'источник: {src}',
      'misc.lastSignal': 'посл. сигнал: {side} @ {close} · вход {entry} · стоп {stop}',
      'misc.entry': 'вход',
      'misc.exit': 'выход',
      'misc.add': 'добавить',
      'misc.delete': 'удалить',
      'misc.delConfirm': 'Удалить {sym}?',
      'misc.noSave': 'Не сохранилось: ',
      'misc.failed': 'не удалось: ',

      'journal.title': 'Журнал: {sym}',
      'journal.loadErr': 'ошибка загрузки',
      'journal.openPos': '📌 ОТКРЫТА:',
      'journal.entry': 'вход: {dt} · стоп {stop} ({pct}%)',
      'journal.noTrades': 'сделок за период нет',
      'journal.plPeriod': 'P/L за период',
      'journal.trades': '{n} сделок',
      'journal.winrate': 'винрейт',
      'journal.bestWorst': 'лучшая / худшая',
      'period.current_month': 'текущий мес',
      'period.month': 'прошлый мес',
      'period.year': 'год',
      'period.all': 'всё',
    },

    es: {
      'lang.label': 'Idioma',
      'status.loading': 'cargando…',
      'brand.trade': 'Operar en BingX',
      'btn.refresh': '⟳ Actualizar',
      'tt.theme': 'Día/Noche',
      'tt.about': 'Acerca de',

      'ind.candles': 'velas',
      'ind.volume': 'volumen',
      'ind.hvol': 'volumen (horiz.)',
      'ind.vma': 'Vol MA20',
      'ind.supertrend': 'Supertrend',
      'ind.donchian': 'Donchian',
      'ind.bollinger': 'Bollinger',

      'bar.trades': 'operaciones:',
      'bar.strategy': 'estrategia:',
      'btn.params': '⚙ parámetros',
      'btn.webhooks': '🔔 webhooks',
      'btn.editor': '🧩 Editor de estrategias',
      'btn.docs': '📘 Documentación',

      'bar.trading': 'operativa:',
      'trade.live': 'operativa real en BingX',
      'btn.tradeSettings': '💹 ajustes',
      'btn.tickers': '📋 tickers operados',
      'acct.balance': 'saldo: —',

      'btn.cancel': 'Cancelar',
      'btn.save': 'Guardar',
      'btn.close': 'Cerrar',
      'btn.add': 'Añadir',
      'btn.ok': 'OK',

      'params.title': 'Parámetros de la estrategia',
      'params.scope': 'Guardado para: {scope}  (★ — guardar solo para este instrumento)',
      'params.main': 'parámetros de la estrategia',
      'params.risk': 'salidas (opcional): stop siempre activo · TP y trailing por casilla',
      'params.tp': 'Take-profit %',
      'params.trail': 'Trailing stop %',

      'wh.title': 'Webhooks',
      'wh.strategy': 'Estrategia',
      'wh.symbol': 'Instrumento ("*" — todos)',
      'wh.chatId': 'Chat ID (vacío — tu privado)',
      'wh.chatPh': 'tu Chat ID',
      'wh.thread': 'Thread ID (opcional, para temas)',
      'wh.enabled': 'Act',
      'wh.yes': 'sí',
      'wh.no': 'no',
      'wh.none': 'sin webhooks',
      'wh.edit': 'Editar',
      'wh.del': 'Eliminar',
      'wh.delConfirm': '¿Eliminar webhook #{id} ({strategy} · {symbol})?',
      'wh.saved': 'Guardar',
      'wh.tf': 'TF',

      'editor.title': 'Editor de estrategias (Python)',
      'editor.hint': 'Disponible: open/high/low/close/volume · entradas inp(name, default, title, type) · indicadores sma/ema/rma/rsi/macd/atr/supertrend/adx/donchian/bb · crossover/crossunder · señales entry(\'long\'|\'short\', cond) y exit(cond) · dibujo plot/shape/hline. Combina condiciones con & | ~.',
      'editor.name': 'Nombre de la estrategia',
      'editor.namePh': 'Mi Estrategia',
      'editor.code': 'Código de la estrategia (Python)',
      'editor.check': '🔎 Comprobar',
      'editor.compile': '⚙ Compilar (estrategia)',
      'editor.toChart': '🧷 Al gráfico (indicador)',
      'editor.clear': '✖ Quitar del gráfico',
      'editor.export': '⬇ Exportar estrategia',
      'editor.import': '⬆ Importar',
      'editor.sample': 'Ejemplo:',
      'editor.saved': 'Estrategias guardadas:',
      'editor.choose': '— elegir —',
      'editor.samplePh': '— ejemplo —',
      'editor.checkOk': '✓ comprobación superada',
      'editor.line': 'línea {n}: {msg}',
      'editor.dryrun': 'prueba: {symbol} {tf}, {bars} barras · long={longs} short={shorts} exit={exits} · operaciones {trades}{open}',
      'editor.open': ' (posición abierta)',
      'editor.params': 'parámetros: {list}',
      'editor.compiled': '✅ estrategia «{title}» compilada y registrada (clave <b>{key}</b>)',
      'editor.imported': '✅ importada: «{title}» (clave {key})',
      'editor.checkFail': 'Comprobación fallida — compilación cancelada',
      'editor.needName': 'Introduce un nombre de estrategia.',
      'editor.noBars': 'sin barras para la prueba',
      'editor.added': '✅ añadido al gráfico: líneas {lines}, marcadores {shapes}, niveles {hlines}',
      'editor.importBad': 'Archivo no reconocido (se espera .rwd.json)',
      'editor.importNoSource': 'El archivo no tiene campo "source"',
      'editor.importErr': 'error de importación',

      'docs.title': 'Cómo escribir estrategias de trading',

      'tickers.title': 'Tickers operados (solo se opera con los añadidos)',
      'tickers.add': 'Añadir',
      'tickers.choose': '— elegir instrumento —',
      'tickers.empty': 'la lista está vacía — no se opera con nada',
      'tickers.toggle': 'act/des',
      'tickers.remove': '¿Quitar {sym} de los operados?',
      'tickers.notAdded': 'No añadido: ',

      'inst.title': 'Añadir instrumento',
      'inst.ticker': 'Ticker',
      'inst.name': 'Nombre',
      'inst.category': 'Categoría',
      'inst.dataType': 'Tipo de datos',
      'inst.kindCrypto': 'cripto (BingX/Binance/Bybit/OKX)',
      'inst.kindStock': 'bolsa/materias primas (Yahoo)',
      'inst.yahoo': 'Símbolo Yahoo (para acciones/materias primas)',
      'cat.crypto': 'Criptomonedas',
      'cat.stocks': 'Acciones',
      'cat.energy': 'Energía',
      'cat.metals': 'Metales',
      'cat.indices': 'Índices',

      'trade.title': 'Operativa en BingX (futuros / swap)',
      'trade.apiKey': 'API Key',
      'trade.secret': 'Secret Key',
      'trade.fundPw': 'Contraseña de fondos (obligatoria para operar en real)',
      'trade.fundPwPh': 'confirmación para activar real',
      'trade.env': 'Entorno',
      'trade.envLive': 'Real (live)',
      'trade.envVst': 'Simulación (testnet VST)',
      'trade.lev': 'Apalancamiento (1–125)',
      'trade.pct': '% del saldo por posición',
      'trade.notifyToken': 'Token de bot para avisos de operación',
      'trade.notifyChat': 'TG id del destinatario (privado)',
      'trade.mailTitle': 'Avisos por e-mail (opcional)',
      'trade.mailNote': 'Solo avisos personales — los correos van a esta única dirección.',
      'trade.smtpHostPh': 'smtp.example.com',
      'trade.smtpTls': 'STARTTLS',
      'trade.smtpUser': 'Usuario SMTP',
      'trade.smtpPass': 'Contraseña SMTP / de aplicación',
      'trade.mailTo': 'Enviar avisos a (e-mail)',
      'trade.testMailSent': 'Correo enviado a {to}',
      'trade.keepPh': 'dejar vacío para no cambiar',
      'trade.clearKeys': 'Eliminar claves',
      'trade.testNotify': '✈ Probar aviso',
      'trade.keysOk': '✅ claves configuradas ({mask}){fund}',
      'trade.fundPwSet': ' · contraseña de fondos definida',
      'trade.keysNo': '⚠️ claves NO configuradas',
      'trade.testSent': 'Prueba enviada a {chat}',
      'trade.testFail': 'No enviado: {err}',
      'trade.clearConfirm': '¿Eliminar las claves API de BingX? Se detendrá la operativa real.',
      'acct.balanceLine': 'saldo: {eq} USDT · PnL(real): {pnl}',
      'acct.tooltip': 'PnL no realizado: {pnl} · margen disponible: {margin}',

      'about.tagline': 'Terminal portátil de gráficos y señales.',
      'about.site': 'Sitio:',
      'about.partner': 'Enlace de socio:',
      'about.license': 'Licencia: Apache License 2.0. El software se ofrece «tal cual», no es asesoramiento de inversión.',
      'about.importrisk': '⚠️ Las estrategias importadas (.rwd.json) son código de terceros, no verificadas por el autor. Importa solo de fuentes de confianza y revisa primero el campo source — el entorno aislado limita lo que puede hacer el código importado, pero no garantiza que sea seguro, correcto o rentable.',
      'about.thirdparty': 'Componentes de terceros: TradingView Lightweight Charts™ (Apache-2.0) y otros — ver THIRD-PARTY-NOTICES.txt.',

      'misc.loading': '{sym} · cargando…',
      'misc.bars': '{symbol} · {title} · {count} velas',
      'misc.source': 'fuente: {src}',
      'misc.lastSignal': 'última señal: {side} @ {close} · entrada {entry} · stop {stop}',
      'misc.entry': 'entrada',
      'misc.exit': 'salida',
      'misc.add': 'añadir',
      'misc.delete': 'eliminar',
      'misc.delConfirm': '¿Eliminar {sym}?',
      'misc.noSave': 'No se guardó: ',
      'misc.failed': 'falló: ',

      'journal.title': 'Diario: {sym}',
      'journal.loadErr': 'error de carga',
      'journal.openPos': '📌 ABIERTA:',
      'journal.entry': 'entrada: {dt} · stop {stop} ({pct}%)',
      'journal.noTrades': 'sin operaciones en el período',
      'journal.plPeriod': 'P/L del período',
      'journal.trades': '{n} operaciones',
      'journal.winrate': 'tasa de acierto',
      'journal.bestWorst': 'mejor / peor',
      'period.current_month': 'mes actual',
      'period.month': 'mes pasado',
      'period.year': 'año',
      'period.all': 'todo',
    },
  };

  const LANGS = ['en', 'ru', 'es'];
  const STORE_KEY = 'rtd_lang';
  let current = 'en';

  function detect() {
    let l = null;
    try { l = localStorage.getItem(STORE_KEY); } catch (e) {}
    if (l && LANGS.includes(l)) return l;
    const nav = (navigator.language || 'en').slice(0, 2).toLowerCase();
    return LANGS.includes(nav) ? nav : 'en';
  }

  function t(key, vars) {
    const table = DICT[current] || DICT.en;
    let s = table[key];
    if (s == null) s = DICT.en[key];
    if (s == null) return key;
    if (vars) {
      s = s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] != null ? vars[k] : m));
    }
    return s;
  }

  function apply(root) {
    root = root || document;
    root.querySelectorAll('[data-i18n]').forEach(el => {
      el.textContent = t(el.getAttribute('data-i18n'));
    });
    root.querySelectorAll('[data-i18n-ph]').forEach(el => {
      el.setAttribute('placeholder', t(el.getAttribute('data-i18n-ph')));
    });
    root.querySelectorAll('[data-i18n-title]').forEach(el => {
      el.setAttribute('title', t(el.getAttribute('data-i18n-title')));
    });
    document.documentElement.lang = current;
    const sel = document.getElementById('langsel');
    if (sel) sel.value = current;
  }

  function setLang(lang) {
    if (!LANGS.includes(lang)) lang = 'en';
    current = lang;
    try { localStorage.setItem(STORE_KEY, lang); } catch (e) {}
    apply();
    if (typeof window.onLangChange === 'function') window.onLangChange(lang);
  }

  window.RTD_I18N = {
    t, apply, setLang,
    get lang() { return current; },
    langs: LANGS,
  };
  window.t = t;

  function init() {
    current = detect();
    apply();
    const sel = document.getElementById('langsel');
    if (sel) sel.addEventListener('change', () => setLang(sel.value));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
