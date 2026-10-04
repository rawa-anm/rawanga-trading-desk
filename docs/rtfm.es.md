# RTFM — Rawanga Trading Desk

> Read The Friendly Manual. Este documento explica qué es el programa, cómo
> instalarlo en una máquina local, cómo ejecutarlo en un servidor y cómo usarlo.
> Existe en tres idiomas: `rtfm.en.md`, `rtfm.es.md`, `rtfm.ru.md`.

---

## 0. Qué es y para quién

**Rawanga Trading Desk** es una aplicación de escritorio portátil para:

- gráficos de velas (marcos temporales 15m, 1h, 4h, 1d, 1w, 1M);
- indicadores técnicos (MA/EMA, RSI, MACD, ATR, Supertrend, Bollinger, Donchian, ADX…);
- escribir y hacer back-test de tus propias estrategias en Python;
- señales de operaciones/tendencia con avisos opcionales (Telegram y/o correo);
- operativa automatizada opcional en BingX (futuros/swap) — **desactivada por defecto**.

Técnicamente es un pequeño servidor web local (FastAPI) más una interfaz en el
navegador. Al iniciar el programa, lanza el servidor **en tu propio ordenador** y
abre la interfaz en el navegador. Todo se ejecuta en local.

> ⚠️ **Uso previsto: individual, un solo usuario.** **No hay cuentas, ni inicio de
> sesión, ni contraseña para la interfaz, ni separación entre usuarios.** Quien
> pueda abrir la dirección web del programa tiene control total sobre él,
> incluida la activación de la operativa real, si la has configurado.

---

## 1. Requisitos

| | Build portátil (recomendado) | Desde el código fuente |
|---|---|---|
| Python | no hace falta | 3.10+ (probado con 3.12) |
| Otros | — | `pip` |
| SO | Windows 10/11 x64, macOS 12+, Linux x64 | igual |
| Red | internet para los datos de mercado | igual |

El build portátil es autocontenido: incluye su propio intérprete de Python y
todas las dependencias. No hay nada que instalar.

---

## 2. Instalación — build portátil (usuario normal, máquina propia)

Descarga el archivo correspondiente a tu SO desde la página de Releases del
proyecto:

- `RawangaTradingDesk-windows-x64.zip`
- `RawangaTradingDesk-macos-x64.tar.gz` (Intel) o `RawangaTradingDesk-macos-arm64.tar.gz` (Apple Silicon)
- `RawangaTradingDesk-linux-x64.tar.gz`

Descomprímelo donde quieras (Escritorio, USB, `D:\Apps`, `~/Apps`, …). La
carpeta contiene el ejecutable y su entorno.

### Windows

1. Descomprime el `.zip`.
2. Ejecuta `RawangaTradingDesk\RawangaTradingDesk.exe`.
3. Puede aparecer SmartScreen ("Windows protegió tu PC") porque el build no está
   firmado digitalmente. Pulsa **Más información → Ejecutar de todas formas**.
4. El navegador se abre solo con la interfaz.

### macOS

1. Descomprime el `.tar.gz`.
2. Como el build no está notarizado, macOS lo marca en cuarentena. Quítala:
   ```bash
   xattr -dr com.apple.quarantine /ruta/a/RawangaTradingDesk
   ```
3. Ejecuta el binario `RawangaTradingDesk` dentro de la carpeta.
   Si macOS sigue negándose: **Ajustes del Sistema → Privacidad y seguridad →
   Abrir de todas formas**.
4. El navegador se abre solo.

### Linux

```bash
tar xzf RawangaTradingDesk-linux-x64.tar.gz
cd RawangaTradingDesk
chmod +x RawangaTradingDesk
./RawangaTradingDesk
```
El navegador se abre solo.

> La ventana de consola que aparece **es** el programa. **Cerrarla detiene el
> programa.** Déjala abierta mientras trabajas.

---

## 3. Instalación — desde el código fuente (desarrolladores)

```bash
git clone <url-del-repositorio>
cd rawanga-trading-desk

python -m venv .venv
# Windows:  .venv\Scripts\activate
. .venv/bin/activate

pip install -r requirements.txt
python -m app.launcher
```

El navegador se abre en `http://127.0.0.1:<puerto_libre_aleatorio>/`.

Variables de entorno:

| Variable | Por defecto | Significado |
|---|---|---|
| `RAWANGA_HOST` | `127.0.0.1` | dirección de escucha (solo local) |
| `RAWANGA_PORT` | `0` (puerto libre aleatorio) | puerto fijo, si lo quieres |
| `RAWANGA_DATA_DIR` | `./data` (junto al programa), si no, carpeta de datos del SO | dónde se guardan tus datos |

---

## 4. Primer inicio y flujo de trabajo

1. Inicia el programa. La interfaz se abre en tu navegador.
2. Elige un instrumento a la derecha (p. ej. `BTC`) y un marco temporal en la
   barra superior del gráfico (por defecto **1h**).
3. El gráfico carga velas, volumen y los indicadores seleccionados.
4. Filas inferiores: botones de estrategias, conmutadores de indicadores,
   "Strategy editor", "Strategy docs", webhooks, ajustes de trading.
5. Haz clic en un instrumento para abrir su **diario de operaciones** a la
   derecha (operaciones por periodo, win rate, mejor/peor, P/L).
6. **Strategy editor** (botón 🧩): carga un ejemplo o escribe tu propia
   estrategia en Python → **Check** → **Compile** → **To chart**. La referencia
   completa está en el botón **Strategy docs** (📘), en tu idioma de interfaz.
7. **Idioma de la interfaz**: selector en la barra superior (EN / RU / ES). La
   elección se recuerda en tu máquina.

---

## 5. Dónde viven tus datos y copias de seguridad

Todos los datos de usuario están en el **directorio de datos** (por defecto
`./data` junto al programa; en una máquina donde esa carpeta no sea escribible,
en la carpeta de datos del SO: `%APPDATA%\RawangaTradingDesk` en Windows,
`~/Library/Application Support/RawangaTradingDesk` en macOS,
`~/.local/share/RawangaTradingDesk` en Linux).

| Archivo | Contenido |
|---|---|
| `tv.db` | base SQLite: instrumentos, velas en caché, parámetros, diario, ajustes |
| `bx_secrets.enc` | claves API de la exchange + credenciales de avisos (cifradas) |
| `bx_secret.key` | clave maestra del archivo anterior |
| `bot.key` | token del bot de Telegram (opcional) |
| `usdtd_history.json` | historial auxiliar de tendencia |

**Copia de seguridad:** copia toda la carpeta de datos. **Mover a otra máquina:**
copia la carpeta de datos junto con la del programa.

> Nunca subas ni compartas la carpeta de datos: contiene tus claves.

---

## 6. Avisos (opcional)

Los avisos están **desactivados** hasta que los configures. Ambos canales son
independientes: puedes usar Telegram, correo, ambos o ninguno.

### Telegram

1. Crea un bot con `@BotFather` y copia su token.
2. Envía cualquier mensaje a tu bot para que pueda responderte; obtén tu chat id
   con `@userinfobot` (o similar).
3. En la app: **Ajustes de trading → Bot token for trade alerts** y
   **Recipient TG id**. Guarda.
4. Pulsa **✈ Test alert** — deberías recibirlo en Telegram.

### Correo (a ti mismo)

El programa envía avisos **a una única dirección — la tuya**, a través de tu
propio buzón SMTP. Es un canal personal de avisos, no una herramienta de envío
masivo: un solo destinatario, sin listas, sin Cc/Bcc.

1. En la app: **Ajustes de trading → E-mail alerts**.
2. Rellena host / puerto / usuario / contraseña SMTP (para Gmail usa una
   **contraseña de aplicación**, no la normal) y la dirección de destino (tu
   propio buzón).
3. STARTTLS se usa para el puerto 587, SSL implícito para el 465.
4. Guarda y pulsa **✈ Test alert**.

---

## 7. Ejecución en un servidor (VPS / nube) — y la advertencia de seguridad

*Puedes* ejecutarlo en un servidor y abrirlo desde otra máquina. Pero antes lee
esto con atención.

> ⚠️ **Seguridad — leer antes de alojarlo en algo que no sea tu propio ordenador**
>
> 1. **La interfaz web no tiene autenticación.** Quien pueda alcanzar el puerto
>    puede ver tus gráficos, cambiar ajustes, enviar avisos de prueba y —si
>    configuraste claves— activar y dirigir **operativa real**.
> 2. **Tus credenciales viven en el host.** Las claves API y las credenciales de
>    avisos se guardan cifradas con Fernet en `bx_secrets.enc`, **pero la clave
>    maestra `bx_secret.key` está en la misma carpeta.** Para quien tenga acceso
>    al sistema de archivos (o quien obtenga una instantánea / copia del disco),
>    esto es, en la práctica, **ninguna protección** — trata las claves en un
>    host en la nube como guardadas en claro.
> 3. En consecuencia: **no expongas el puerto a internet abierto.** Si debes
>    alojarlo en remoto, como mínimo:
>    - mantenlo ligado a una red privada y accede por **VPN**
>      (p. ej. Tailscale/WireGuard) o por **túnel SSH**
>      (`ssh -L 8080:127.0.0.1:8080 user@server`);
>    - o ponlo detrás de un **proxy inverso con autenticación + TLS** y
>      restríngelo con un cortafuegos;
>    - cifra el disco del servidor y prefiere una clave dedicada en la exchange
>      con permisos mínimos / sin derecho de retiro.

### Ejemplo: ejecutar en un servidor con puerto fijo

```bash
# en el servidor, dentro del proyecto (instalación desde código)
RAWANGA_HOST=127.0.0.1 RAWANGA_PORT=8080 python -m app.launcher
```

Luego accede desde tu máquina mediante un túnel SSH:

```bash
ssh -L 8080:127.0.0.1:8080 user@tu-servidor
# ahora abre http://127.0.0.1:8080/ en local
```

### Ejemplo: servicio systemd (instalación desde código)

`/etc/systemd/system/rawanga-trading-desk.service`:

```ini
[Unit]
Description=Rawanga Trading Desk
After=network-online.target

[Service]
User=tuusuario
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

> Mantén `RAWANGA_HOST=127.0.0.1` y accede por VPN/túnel. Cámbialo a `0.0.0.0`
> solo si entiendes del todo que estás exponiendo un panel de control **sin
> autenticación**.

---

## 8. Editor de estrategias

- Se abre con el botón **🧩 Strategy editor**.
- Escribe Python; el código se ejecuta en una sandbox restringida (sin `import`,
  `eval`, `exec`, `open`, acceso a archivos/red, `for`/`while`, acceso a dunder).
- API disponible: series de precio `open/high/low/close/volume`; `inp(...)`;
  indicadores `sma, ema, rma, wma, stdev, highest, lowest, change, rsi, macd, bb,
  atr, supertrend, adx, donchian`; `crossover/crossunder`; `nz/na/series`;
  `entry/exit`; `plot/shape/hline`.
- Botones: **Check** (valida + prueba en seco), **Compile (strategy)** (registra
  en el motor), **To chart (indicator)** (dibuja en el gráfico), **Remove from
  chart**, **Export strategy**, **Import**.
- **Exportar/importar** usa el archivo `*.rwd.json` para compartir una estrategia.
- ⚠️ **Importa estrategias solo de fuentes en las que confíes y revisa primero el
  código del campo `source`.** El entorno aislado limita lo que puede hacer el código
  importado, pero no garantiza que sea seguro, correcto o rentable. Las estrategias
  de terceros no están escritas ni verificadas por el autor, que no se
  responsabiliza de ellas.
- Referencia completa: botón **📘 Strategy docs** (en EN/RU/ES).

---

## 9. Operativa real (BingX) — opcional y con riesgo

La operativa real está **desactivada por defecto**. Para activarla debes: guardar
las claves API, definir una contraseña de fondos y activar explícitamente el modo
real. Sin todo eso, nunca se envía ninguna orden.

- Usa una clave API dedicada con permisos mínimos.
- La app opera solo los tickers que añadas explícitamente a la lista de
  "traded tickers".
- La operativa es bajo **tu** responsabilidad y **tu** capital. El software se
  ofrece "tal cual"; **no es asesoramiento de inversión**.

---

## 10. Actualizar / desinstalar

- **Portátil:** reemplaza la carpeta del programa por una versión más nueva;
  conserva tu carpeta `data/`.
- **Código fuente:** `git pull` y `pip install -r requirements.txt`.
- **Desinstalar:** borra la carpeta del programa y (si quieres empezar de cero)
  la carpeta de datos.

---

## 11. Solución de problemas

| Síntoma | Solución |
|---|---|
| El navegador no se abrió | Abre manualmente la dirección impresa en la consola (`http://127.0.0.1:<puerto>/`). |
| Windows: "Windows protegió tu PC" | Más información → Ejecutar de todas formas (build sin firmar). |
| macOS: "no se puede abrir / está dañada" | `xattr -dr com.apple.quarantine <ruta>` (ver §2). |
| Sin datos para un instrumento | Comprueba la conexión; prueba **⟳ Refresh**. |
| Los avisos no llegan | Pulsa **✈ Test alert**; revisa token / chat id / ajustes SMTP. |
| El puerto ya está en uso | Define `RAWANGA_PORT` con un puerto libre. |
| ¿Dónde están mis datos? | La carpeta `data/` junto al programa (§5). |

---

## 12. Licencia y avisos legales

- Licencia **Apache License 2.0** — ver `LICENSE` / `NOTICE`.
- Componentes de terceros — ver `THIRD-PARTY-NOTICES.txt` y `licenses/`.
- Sin relación con TradingView, BingX ni ningún otro servicio mencionado — ver
  `TRADEMARKS.md`.
- El software se ofrece "tal cual", **sin garantía**; **no es asesoramiento de
  inversión**. Operar es bajo tu propio riesgo.
- **Las estrategias importadas (`.rwd.json`) son código de terceros**, no escritas
  ni verificadas por el autor — importa solo de fuentes de confianza y revisa el
  campo `source` antes de ejecutar. El autor no se responsabiliza de las estrategias
  de terceros ni de las pérdidas que causen. A medida que crezca la base de
  usuarios, analiza las estrategias importadas en busca de inyecciones maliciosas
  o virales.

---

© 2026 Andrei Maltsev · Rawanga AI · https://rawanga.es
