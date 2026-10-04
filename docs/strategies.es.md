# Cómo escribir estrategias de trading — Rawanga Trading Desk

¡Bienvenido! Esta guía explica cómo escribir, probar y compartir tus propias
estrategias e indicadores en **Rawanga Trading Desk** — el terminal portátil de
gráficos y señales.

Una estrategia es simplemente **código Python vectorizado**. No instalas nada, no
importas nada: escribes unas pocas líneas en el editor integrado y el motor las
ejecuta sobre los datos de precio.

---

## 1. Introducción — ¿qué es una estrategia?

Una **estrategia** es un pequeño fragmento de **código Python vectorizado** que el
motor del terminal ejecuta en cada vela del gráfico.

- «Vectorizado» significa que trabajas con **columnas enteras de datos a la vez**, no
  con bucles. En lugar de *«para cada vela, haz…»* escribes expresiones que se
  aplican a toda la serie en una sola línea.
- El motor te da **series** ya preparadas: `open`, `high`, `low`, `close`, `volume`.
  Cada una es un `pandas.Series` alineado con las velas del gráfico.
- Describes **cuándo entrar** (`entry(...)`) y **cuándo salir** (`exit(...)`), y/o
  **qué dibujar** en el gráfico (`plot(...)`, `shape(...)`, `hline(...)`).

La salida de una estrategia es un conjunto de velas donde `long`, `short` y `exit`
son `True`. Esas mismas velas las usan el backtest y el planificador en vivo.

> En el editor puedes ejecutar dos tipos de código:
> - una **estrategia** — declara entradas/salidas (Compile → se registra en el motor);
> - un **indicador** — solo dibuja (To chart → superposición en el gráfico).
> El mismo código puede hacer ambas cosas.

---

## 2. Los nombres disponibles (API completa)

Estos nombres ya están definidos. No los importas: simplemente los usas.

### Series (datos de precio)

| Nombre | Tipo | Significado |
|--------|------|-------------|
| `open`   | `pandas.Series` | Precio de apertura de cada vela |
| `high`   | `pandas.Series` | Precio máximo |
| `low`    | `pandas.Series` | Precio mínimo |
| `close`  | `pandas.Series` | Precio de cierre |
| `volume` | `pandas.Series` | Volumen |

Todas las series comparten el mismo índice (las marcas de tiempo de las velas), así
que puedes compararlas y combinarlas directamente.

### Entradas (parámetros del usuario)

```python
value = inp(name, default, title='', type='float')
```

Declara un **parámetro ajustable por el usuario** que aparece en el panel de ajustes.
Devuelve el valor actual del parámetro.

- `name` — clave interna (cadena), p. ej. `'fast'`.
- `default` — valor por defecto.
- `title` — etiqueta legible que se muestra en la interfaz (opcional).
- `type` — uno de `'int'`, `'float'`, `'bool'`, `'string'` (por defecto `'float'`).

```python
fast  = inp('fast', 12, 'EMA rápida', 'int')
mult  = inp('mult', 1.5, 'Multiplicador de volumen', 'float')
enabled = inp('enabled', True, 'Usar filtro', 'bool')
label = inp('label', 'MACD', 'Etiqueta de la serie', 'string')
```

El editor analiza tu código y muestra cada `inp(...)` escrito en una sola línea como
un ajuste aparte. Asigna siempre el resultado a una variable:

```python
period = inp('period', 14, 'Longitud RSI', 'int')   # ✅ correcto
inp('period', 14, 'Longitud RSI', 'int')            # ❌ el valor se pierde
```

### Indicadores

Todos los indicadores devuelven `pandas.Series` (o una tupla de ellas) alineadas con
el gráfico.

| Función | Devuelve | Notas |
|---------|----------|-------|
| `sma(a, n)` | Series | Media móvil simple |
| `ema(a, n)` | Series | Media móvil exponencial |
| `rma(a, n)` | Series | Suavizado de Wilder (usado en RSI/ATR) |
| `wma(a, n)` | Series | Media móvil ponderada |
| `stdev(a, n)` | Series | Desviación estándar móvil |
| `highest(a, n)` | Series | Valor máximo en `n` velas |
| `lowest(a, n)` | Series | Valor mínimo en `n` velas |
| `change(a)` | Series | Diferencia con la vela anterior |
| `rsi(a, n=14)` | Series | Índice de Fuerza Relativa |
| `macd(a, fast=12, slow=26, signal=9)` | `(macd, signal, hist)` | Línea MACD, señal, histograma |
| `bb(a, n=20, k=2.0)` | `(upper, basis, lower)` | Bandas de Bollinger |
| `atr(n=14)` | Series | Average True Range (usa high/low/close) |
| `supertrend(period=7, mult=2.5)` | `(direction, line)` | `direction`: `+1` arriba / `-1` abajo |
| `adx(di_len=14, smooth=14)` | `(plus_di, minus_di, adx)` | Fuerza de tendencia |
| `donchian(n=10)` | `(upper, lower)` | Canal de Donchian |

Ejemplos:

```python
ma = sma(close, 50)
er = ema(close, 21)

# MACD -> (macd, signal, hist)
m = macd(close)
macd_line   = m[0]
macd_signal = m[1]
macd_hist   = m[2]

# Bollinger -> (upper, basis, lower)
b = bb(close, 20, 2.0)
bb_upper = b[0]
bb_basis = b[1]
bb_lower = b[2]

# Supertrend -> (direction, line)
st = supertrend(7, 2.5)
st_dir  = st[0]
st_line = st[1]

# ADX -> (plus_di, minus_di, adx)
a = adx(14, 14)
plus_di  = a[0]
minus_di = a[1]
adx_val  = a[2]

# Donchian -> (upper, lower)
d = donchian(10)
don_hi = d[0]
don_lo = d[1]
```

> `atr`, `supertrend`, `adx` y `donchian` leen `high`/`low`/`close` internamente —
> tú solo pasas los parámetros de longitud.

> ℹ️ **Los indicadores con varios valores devuelven una tupla.** Accede a las partes
> por **índice** — `m[0]`, `m[1]`, … — o en línea, p. ej. `macd(close)[2]`. El
> **desempaquetado de tuplas** (`a, b = f(...)`) **no está permitido** por el entorno
> aislado y se rechazará durante **Check** (ver «Errores comunes», §10).

### Comparaciones (cruces)

```python
crossover(a, b)   # True en la vela donde a cruza b HACIA ARRIBA
crossunder(a, b)  # True en la vela donde a cruza b HACIA ABAJO
```

`a` y `b` pueden ser una serie o un número. Devuelve una serie booleana.

```python
entry('long',  crossover(ema_fast, ema_slow))
entry('short', crossunder(ema_fast, ema_slow))
```

### Utilidades

| Función | Devuelve | Significado |
|---------|----------|-------------|
| `nz(x, repl=0)` | Series/escalar | Reemplaza `NaN` por `repl` |
| `na(x)` | bool / serie bool | `True` donde el valor es `NaN` |
| `series(x)` | Series | Convierte un escalar/array en Series alineada al gráfico |

```python
r_clean = nz(rsi(close, 14), 50)   # NaN al inicio → 50
is_missing = na(close)
```

### Señales

```python
entry(side, cond)   # side: 'long' o 'short'
exit(cond)
```

- `entry('long', cond)` — abre/cambia a **long** cuando `cond` es `True`.
- `entry('short', cond)` — abre/cambia a **short** cuando `cond` es `True`.
- `exit(cond)` — **cierra** la posición actual cuando `cond` es `True`.

`cond` debe ser una serie booleana (resultado de una comparación). No se envía nada
hasta que se dispara una condición.

```python
entry('long',  crossover(ema_fast, ema_slow))
entry('short', crossunder(ema_fast, ema_slow))
exit(crossunder(close, ema_slow))
```

### Dibujo (salida del indicador)

```python
plot(title, series, color='#2962ff', width=1, style='line')
shape(title, cond, color, location='abovebar', shape='circle')
hline(title, value, color)
```

| Función | Propósito |
|---------|-----------|
| `plot(...)` | Dibuja una línea (o histograma) de una serie |
| `shape(...)` | Dibuja un marcador en las velas donde `cond` es `True` |
| `hline(...)` | Dibuja un nivel horizontal (p. ej. 30 / 70 para el RSI) |

- `plot`: `style` puede ser `'line'` (por defecto) o `'histogram'`; `width` es el
  grosor de la línea (1–4).
- `shape`: `location` es `'abovebar'` o `'belowbar'` (también `'top'`/`'bottom'`);
  `shape` es `'circle'`, `'triangleup'`, `'triangledown'` o `'square'`.
- `hline`: `value` es el precio/nivel de la línea horizontal.

```python
plot('SMA 50', sma(close, 50), '#ff9800', 2, 'line')
plot('Hist. MACD', macd(close)[2], '#26a69a', 1, 'histogram')
hline('Cero', 0, '#787b86')
shape('Buy',  crossover(close, sma(close, 50)), '#26a69a', 'belowbar', 'triangleup')
shape('Sell', crossunder(close, sma(close, 50)), '#ef5350', 'abovebar', 'triangledown')
```

---

## 3. Cómo escribir condiciones

Una comparación entre series produce una **serie booleana** — un valor `True`/`False`
por vela:

```python
bull = ema_fast > ema_slow
oversold = rsi(close, 14) < 30
strong = atr(14) > 1.5
```

Para combinar condiciones, usa los **operadores bit a bit** — funcionan elemento a
elemento sobre toda la serie:

| Quieres | Usa | Ejemplo |
|---------|-----|---------|
| AND | `&` | `(ema_fast > ema_slow) & (volume > vol_ma)` |
| OR  | `\|` | `(r < 30) \| (r > 70)` |
| NOT | `~` | `~(ema_fast > ema_slow)` |

> ⚠️ **NO uses `and`, `or`, `not` con series.** Los operadores `and`/`or`/`not` de
> Python están pensados para un único valor de verdad y darán un error
> (*«The truth value of a Series is ambiguous»*). Encierra siempre cada comparación
> entre paréntesis y únelas con `&`, `|`, `~`:

```python
# ✅ correcto
cond = (ema_fast > ema_slow) & (rsi(close, 14) < 55)

# ❌ incorrecto — da error
cond = (ema_fast > ema_slow) and (rsi(close, 14) < 55)
```

Pon siempre paréntesis en cada comparación, porque en Python `&` tiene más prioridad
que `>`:

```python
# ✅
bull = (ema_fast > ema_slow) & (close > ema_fast)

# ❌ se interpreta como ema_fast > (ema_slow & close) > ema_fast
bull = ema_fast > ema_slow & close > ema_fast
```

Puedes comparar libremente una serie con un número, o dos series entre sí.

---

## 4. Reglas del entorno aislado (seguridad)

Tu código se ejecuta en un **entorno restringido**. Antes de ejecutarlo, el código se
inspecciona (lista blanca AST): debe ser seguro y puramente vectorizado.

**Prohibido — se rechazará antes de ejecutar:**

- `import` / `from ... import ...`
- `eval`, `exec`, `open`
- cualquier acceso a archivos o a la red
- bucles: `for`, `while`
- generadores y comprensiones de lista/conjunto/diccionario
  (`[... for ...]`, `(... for ...)`)
- definiciones de funciones/clases/lambda (`def`, `class`, `lambda`)
- `with`, `try`/`except`, `raise`, `yield`, `await`
- `global`, `nonlocal`, `del`
- **atributos dunder** — cualquier cosa que empiece por `__` (p. ej. `__class__`,
  `__globals__`)

**Permitido — bloques seguros y vectorizados:**

- Todos los nombres de la API de arriba (`sma`, `ema`, `rsi`, `entry`, `plot`, …).
- **Métodos seguros de Series/DataFrame**, incluidos (lista no exhaustiva):
  `shift`, `fillna`, `ffill`, `bfill`, `dropna`, `interpolate`,
  `rolling`, `ewm`, `expanding`, `mean`, `sum`, `std`, `var`, `min`, `max`,
  `median`, `abs`, `clip`, `where`, `diff`, `cumsum`, `cummax`, `cummin`,
  `cumprod`, `pct_change`, `astype`, `isna`, `notna`, `rank`, `round`,
  `pow`, `replace`, `any`, `all`, `count`, `first`, `last`, `head`, `tail`,
  `idxmin`, `idxmax`, y los métodos-operador `le`, `ge`, `lt`, `gt`, `eq`, `ne`,
  `add`, `sub`, `mul`, `div`, `mod`.
- Ayudas de **numpy** vía `np.`: `np.maximum`, `np.minimum`, `np.where`, `np.abs`,
  `np.log`, `np.log10`, `np.sqrt`, `np.exp`, `np.clip`, `np.sign`,
  `np.nan_to_num`, `np.isnan`, `np.isfinite`, `np.arange`.
- Integradas: `bool`, `float`, `int`, `abs`, `round`, `min`, `max`, `len`.
- `df` (el DataFrame OHLCV completo), `pd`, `np`.

**Conviene saber:**

- Como los valores son vectorizados, un `if` sobre una serie no funciona. Usa
  `np.where` / `.where(...)` en lugar de ramificar:

```python
# ❌ if sobre una serie — ambiguo
# if close > open: ...

# ✅ elección vectorizada
direction = np.where(close > open, 1, -1)
stop = np.minimum(close, ema(close, 20))   # mínimo elemento a elemento
```

- Solo acceso de lectura a los datos. Sin efectos secundarios, sin E/S, sin
  persistencia.

---

## 5. Ejemplo paso a paso n.º 1 — cruce de EMAs

Idea: ir **long** cuando la EMA rápida cruza por encima de la EMA lenta, ir **short**
cuando cruza por debajo.

```python
# ── Entradas ──────────────────────────────────────────────
fast = inp('fast', 12, 'EMA rápida', 'int')
slow = inp('slow', 26, 'EMA lenta', 'int')

# ── Indicadores ──────────────────────────────────────────
ema_fast = ema(close, fast)
ema_slow = ema(close, slow)

# ── Señales ──────────────────────────────────────────────
entry('long',  crossover(ema_fast, ema_slow))
entry('short', crossunder(ema_fast, ema_slow))
```

Línea por línea:

1. `fast` / `slow` — dos parámetros que puedes ajustar en el panel de ajustes.
2. `ema(...)` — calcula las dos medias sobre todo el gráfico a la vez.
3. `entry('long', ...)` — se dispara un long en la vela exacta donde la línea rápida
   cruza de abajo hacia arriba sobre la lenta.
4. `entry('short', ...)` — simétrico: un short en el cruce hacia abajo.

Añadidos opcionales:

```python
# Operar solo cuando la volatilidad es significativa
filter_ok = atr(14) > sma(atr(14), 20)

entry('long',  crossover(ema_fast, ema_slow) & filter_ok)
entry('short', crossunder(ema_fast, ema_slow) & filter_ok)

# Salida a plano cuando la tendencia se da la vuelta
exit(crossunder(ema_fast, ema_slow))
```

---

## 6. Ejemplo paso a paso n.º 2 — reversión con RSI

Idea: comprar cuando el RSI está sobrevendido, vender cuando está sobrecomprado.

```python
# ── Entradas ──────────────────────────────────────────────
n  = inp('n', 14, 'Longitud RSI', 'int')
lo = inp('lo', 30, 'Sobreventa', 'float')
hi = inp('hi', 70, 'Sobrecompra', 'float')

# ── Indicador ────────────────────────────────────────────
r = rsi(close, n)

# ── Señales ──────────────────────────────────────────────
entry('long',  r < lo)
entry('short', r > hi)
```

Explicación:

1. `rsi(close, n)` devuelve la serie del RSI.
2. `r < lo` es `True` en cada vela donde el RSI está por debajo de 30 → long.
3. `r > hi` es `True` en cada vela donde el RSI está por encima de 70 → short.

> `r < 30` se mantiene `True` en muchas velas seguidas mientras el RSI sigue
> sobrevendido. La capa de señales del motor «colapsa» una racha de señales iguales,
> así que no obtienes una operación nueva en cada vela. Si solo quieres la *primera*
> caída por debajo de 30, combínalo con un cruce:

```python
entry('long',  crossover(r, lo))
entry('short', crossunder(r, hi))
```

Añade un filtro de tendencia para no comprar «cuchillos cayendo»:

```python
uptrend = close > sma(close, 200)
entry('long',  (r < lo) & uptrend)
entry('short', (r > hi) & ~uptrend)
```

---

## 7. Ejemplo de indicador (solo dibujo)

Un indicador no opera — solo dibuja. Úsalo con **To chart**.

```python
# ── Entradas ──────────────────────────────────────────────
n = inp('n', 50, 'Longitud SMA', 'int')

# ── Cálculo ──────────────────────────────────────────────
ma = sma(close, n)

# ── Dibujo ───────────────────────────────────────────────
plot('SMA', ma, '#ff9800', 2, 'line')
hline('Cero', 0, '#787b86')
shape('Buy',  crossover(close, ma), '#26a69a', 'belowbar', 'triangleup')
shape('Sell', crossunder(close, ma), '#ef5350', 'abovebar', 'triangledown')
```

Qué aparece en el gráfico:

- una **línea** naranja con la SMA(50);
- una **línea horizontal** gris discontinua en 0;
- marcadores verdes de **triángulo hacia arriba** bajo las velas en los cruces
  ascendentes del cierre sobre la SMA;
- marcadores rojos de **triángulo hacia abajo** sobre las velas en los cruces
  descendentes.

Un panel de RSI se ve así:

```python
n = inp('n', 14, 'Longitud RSI', 'int')

r = rsi(close, n)

plot('RSI', r, '#9c27b0', 2, 'line')
hline('Sobrecompra', 70, '#ef5350')
hline('Sobreventa', 30, '#26a69a')
```

---

## 8. Exportar / importar — compartir estrategias

Cada estrategia compilada se puede descargar como un único archivo **`.rwd.json`** y
compartir con quien quieras; el destinatario lo importa con un clic.

- Botón **Export** → descarga `<Title>.rwd.json` de la estrategia seleccionada.
- Botón **Import** → eliges un archivo `.rwd.json` → la estrategia se valida y se
  registra al instante.

El archivo es JSON plano con esta estructura:

```json
{
  "kind": "rawanga-trading-desk-strategy",
  "version": 1,
  "key": "my_strategy",
  "title": "My Strategy",
  "source": "fast = inp('fast', 12, 'Fast EMA', 'int')\n...",
  "inputs": [
    { "var": "fast", "kind": "int", "name": "Fast EMA", "default": "12", "_val": 12 }
  ],
  "author": "Andrei Maltsev (Rawanga)",
  "license": "Apache-2.0",
  "homepage": "https://rawanga.es"
}
```

| Campo | Significado |
|-------|-------------|
| `kind` | Marca del tipo de archivo (siempre `rawanga-trading-desk-strategy`) |
| `version` | Versión del formato (actualmente `1`) |
| `key` | Id interno (derivado del título) |
| `title` | Nombre mostrado |
| `source` | **El código completo de la estrategia** (la parte importante) |
| `inputs` | Parámetros detectados automáticamente |
| `author` | Línea de autor |
| `license` | Licencia del código compartido |
| `homepage` | Enlace al proyecto |

**Cómo compartir:**

1. Escribe y **Check** tu estrategia.
2. Pulsa **Export** → se guarda `MyStrategy.rwd.json`.
3. Envía el archivo (chat, correo, repositorio, gist).
4. El destinatario pulsa **Import**, selecciona el archivo — listo. La estrategia
   aparece en su lista, lista para ejecutar.

> La máquina del destinatario revalida el código en el mismo entorno aislado, que
> bloquea `import`/`eval`/`exec` y el acceso a archivos y red — así que un archivo
> compartido no puede ejecutar código de sistema arbitrario. Eso limita lo que puede
> hacer una estrategia, pero **no** garantiza la seguridad (ver la advertencia
> abajo). Para la lógica solo importa el campo `source` — los demás campos son
> metadatos.

> ⚠️ **Importar estrategias de terceros conlleva riesgo: importa solo de fuentes en
> las que confíes.** El entorno aislado bloquea el acceso directo al sistema, a los
> archivos y a la red, pero no juzga la intención: una estrategia compartida puede
> seguir siendo defectuosa, engañosa o abusar del cómputo permitido. **Revisa siempre
> el código del campo `source` antes de importar** y trata cada `.rwd.json` importado
> como entrada no confiable. El autor no escribe ni revisa estrategias de terceros y
> no se responsabiliza de ellas ni de las pérdidas que causen. A medida que crezca la
> base de usuarios, analiza las estrategias importadas en busca de inyecciones
> maliciosas o virales antes de ejecutarlas.

---

## 9. Compilación

Tres botones gobiernan el flujo en el editor:

| Botón | Qué hace |
|-------|----------|
| 🔎 **Check** | Valida el código (seguridad + sintaxis) **y ejecuta un backtest de prueba** sobre velas reales. Informa de errores y un resumen: velas, recuento de `long`/`short`/`exit`, número de operaciones. |
| ⚙ **Compile** | La misma validación y luego **registra la estrategia en el motor** bajo una clave. Queda disponible para el planificador y el backtester al instante (sin reinicio). |
| 🧷 **To chart** | Ejecuta el código como **indicador** y superpone su salida `plot`/`shape`/`hline` en el gráfico actual. No registra operaciones. |

Flujo recomendado:

1. Pega tu código.
2. Pulsa **Check** → corrige los errores hasta que diga *«check passed»* y el
   backtest de prueba se vea razonable.
3. Pulsa **Compile** → la estrategia se guarda (ponle nombre antes en el campo
   *Strategy name*). La clave se deriva del nombre, p. ej. `My Strategy` → `my_strategy`.
4. Para visualizar un indicador, pulsa **To chart** en su lugar.

Notas:

- El nombre debe ser único; las claves reservadas `stv3`, `rawa_system` y `trend`
  están ocupadas por estrategias integradas.
- Las estrategias compiladas se guardan y se vuelven a registrar automáticamente al
  arrancar.
- Puedes eliminar una estrategia compilada de la lista de guardadas.

---

## 10. Errores comunes y consejos

**1. Usar `and` / `or` / `not` con series**

```python
# ❌ "The truth value of a Series is ambiguous"
cond = (r < 30) and (close > ma)

# ✅
cond = (r < 30) & (close > ma)
```

**2. Olvidar paréntesis en las comparaciones**

```python
# ❌ error de precedencia de operadores
cond = close > ema_fast & volume > vol_ma

# ✅
cond = (close > ema_fast) & (volume > vol_ma)
```

**3. Usar bucles**

```python
# ❌ for ... no está permitido
for i in range(len(close)):
    ...

# ✅ exprésalo vectorizado
mom = close / close.shift(10) - 1
```

**4. Olvidar asignar `inp(...)`**

```python
# ❌ la entrada se declara pero no se usa
inp('len', 14, 'Longitud', 'int')

# ✅
length = inp('len', 14, 'Longitud', 'int')
```

**5. `if` sobre una serie**

```python
# ❌ ambiguo
# if close > open: side = 1

# ✅
side = np.where(close > open, 1, -1)
```

**6. Comparar una zona inicial / vacía**

Indicadores como `sma(close, 200)` son `NaN` en las primeras velas. Las comparaciones
con `NaN` dan `False`, que es lo que quieres; pero si necesitas sustituir, usa `nz`:

```python
ma = nz(sma(close, 200), close)
```

**7. Ajustar parámetros**

Prefiere `inp(...)` a números fijos, así puedes optimizar sin editar el código. Los
parámetros aparecen en el panel de ajustes tras la compilación.

**8. Mantener entradas y salidas coherentes**

`entry('long', …)` también **invierte** un short. Si quieres una salida a plano en
lugar de una inversión, usa `exit(...)`. Decide conscientemente cuál necesitas.

**9. Dibujar solo cuando es un indicador**

`plot`/`shape`/`hline` son inofensivos en una estrategia, pero solo afectan al
gráfico al pulsar **To chart**. Las señales vienen de `entry`/`exit`.

**10. Prueba en varios instrumentos y marcos temporales**

Una estrategia que se ve genial en un instrumento puede ser ruido en otro. Usa
**Check** (y el backtester) en varios mercados y marcos temporales antes de confiar
en ella.

**11. El desempaquetado de tuplas (`a, b = f(...)`) no está permitido**

El entorno aislado rechaza las asignaciones con desempaquetado de tuplas durante
**Check**. Los indicadores con varios valores devuelven una tupla — indízala:

```python
# ❌ error 'unknown name' durante Check
macd_line, macd_signal, macd_hist = macd(close)

# ✅
m = macd(close)
macd_line   = m[0]
macd_signal = m[1]
macd_hist   = m[2]

# en línea también funciona:
hist = macd(close)[2]
```

**Bloques útiles**

```python
# Distancia de stop basada en ATR como serie
stop_dist = atr(14) * 2

# Momento normalizado
roc = close / close.shift(20) - 1

# Filtro de volatilidad
calm = stdev(close, 20) < sma(stdev(close, 20), 50)

# Dirección de Supertrend
st = supertrend(10, 3.0)
st_dir = st[0]
entry('long',  (st_dir == 1) & (st_dir.shift(1) == -1))
entry('short', (st_dir == -1) & (st_dir.shift(1) == 1))

# Ruptura de Bandas de Bollinger
b = bb(close, 20, 2.0)
upper = b[0]
lower = b[2]
entry('long',  crossover(close, upper))
entry('short', crossunder(close, lower))
```

---

## Aviso legal

**No es una recomendación de inversión. Operar es bajo tu propio riesgo.**

El software se proporciona «tal cual», sin garantía de ningún tipo. El rendimiento
pasado no garantiza resultados futuros. Prueba siempre tus estrategias y nunca
arriesgues más de lo que puedas permitirte perder.

**Las estrategias de terceros son tu responsabilidad.** Las estrategias que importas
de otros (`.rwd.json`) no están escritas, revisadas ni verificadas por el autor.
Importa solo de fuentes de confianza y revisa primero el código del campo `source`:
el entorno aislado limita lo que puede hacer el código importado, pero no garantiza
que sea seguro, correcto o rentable. El autor no se responsabiliza de las estrategias
de terceros ni de los daños y pérdidas causados por importarlas o ejecutarlas.

---

© 2026 Andrei Maltsev · Rawanga AI · https://rawanga.es
