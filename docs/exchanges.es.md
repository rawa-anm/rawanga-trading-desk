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

# Cambiar entre exchanges — Rawanga Trading Desk

> Este documento explica cómo conviven los dos backends de operativa (BingX y
> Hyperliquid), cómo cambiar entre ellos de forma segura y qué ocurre con tus
> posiciones al hacerlo.
> Disponible en tres idiomas: `exchanges.en.md`, `exchanges.es.md`,
> `exchanges.ru.md`.

---

## 0. La regla que importa

**En cada momento hay exactamente UN exchange activo.**

La app siempre trabaja con un único backend. No existe un modo "operar en los
dos", y es deliberado: dos exchanges significan dos balances, dos conjuntos de
posiciones y dos fuentes de verdad para una misma decisión.

---

## 1. En qué se diferencian los backends

No son variantes del mismo protocolo — son incompatibles, y por eso hay dos
drivers separados en lugar de uno con un conmutador dentro.

| | BingX (`exchange.py`) | Hyperliquid (`exchange_hl.py`) |
|---|---|---|
| Firma | HMAC-SHA256 | EIP-712 + msgpack |
| Credenciales | API key + secret key | clave privada del agente (API wallet) + dirección de la cuenta maestra |
| Modo de posición | hedge (LONG/SHORT) | solo one-way |
| Tipo de orden | MARKET | límite IOC agresivo (HL no tiene MARKET) |
| Nocional mínimo | ~5 USDT | 10 USDT |
| Símbolo | `BTC-USDT` | `BTC` + índice entero del activo |
| Origen del balance | `marginSummary.accountValue` | `spotClearinghouseState` si la cuenta es unified |

El driver de BingX está intacto respecto a la versión probada en operativa real.
El de Hyperliquid es un módulo aparte a propósito: editar el código de BingX que
ya funciona para acomodar otro protocolo pondría en riesgo el camino probado.

---

## 2. Dónde viven las claves

Cada exchange tiene su **propio** archivo cifrado en el directorio de datos:

| Archivo | Contenido |
|---|---|
| `bx_secrets.enc` + `bx_secret.key` | BingX: api key, secret, contraseña de fondos, ajustes de avisos |
| `hl_secrets.enc` + `hl_secret.key` | Hyperliquid: dirección maestra, clave privada del agente, entorno |

Están separados a propósito: filtrar uno no expone el otro exchange. Ambos se
cifran con Fernet; las claves maestras se crean con permisos `0600` al primer uso.

Las credenciales de Telegram y e-mail son **compartidas**: se guardan en el
archivo de BingX sea cual sea el exchange activo, porque un aviso es un aviso.

---

## 3. Configurar las claves de Hyperliquid (la trampa habitual)

En Hyperliquid **no** se opera con la clave privada de la cuenta, sino con una
**API wallet** (agent wallet):

1. Abre `https://app.hyperliquid.xyz/API`.
2. Crea una **API wallet / agente** y copia la clave privada que genera.
3. En la app: **Ajustes de operativa → Exchange = Hyperliquid**.
4. Pega:
   - **Dirección de la cuenta maestra** — tu cuenta principal (`0x…`), la que tiene los fondos;
   - **Clave privada del agente** — la del paso 2;
   - **Entorno** — Mainnet o Testnet.
5. Pulsa **Comprobar conexión**. Es solo lectura; no se envían órdenes.

> ⚠️ **El error clásico:** pegar la dirección del *agente* en lugar de la de la
> cuenta maestra. La API devuelve una cuenta vacía: sin balance, sin posiciones,
> sin error. Si "Comprobar conexión" informa de una cuenta vacía, casi siempre
> es por esto.

La clave privada nunca se registra en logs ni se muestra en la interfaz — solo
una máscara.

---

## 4. Instalar el SDK de Hyperliquid

El driver necesita un conjunto opcional de dependencias. La app base funciona sin
él; quien opere solo en BingX no lo necesita.

```bash
pip install -r requirements-hl.txt
```

Mientras no esté instalado, cualquier intento de enviar una orden a HL falla con
un mensaje claro pidiendo instalarlo — el resto de la app sigue funcionando.

---

## 5. Cambiar de exchange

En la app: **💹 Ajustes de operativa → Exchange** → elegir el backend → **Guardar**.

### Qué ocurre al cambiar

- El driver elegido pasa a estar activo de inmediato; no hace falta reiniciar.
- El panel de claves cambia al exchange seleccionado.
- Si la **operativa real está DESACTIVADA**, el cambio se aplica en silencio.

### Si la operativa real está ACTIVADA

El cambio exige una confirmación explícita, y la app explica por qué:

> **Cierra todas las posiciones en el exchange actual antes de cambiar: la app no
> sigue las posiciones del exchange inactivo.**

No es una formalidad. La app vigila las posiciones solo en el exchange activo.
Una posición dejada en el otro sigue viva en el exchange, pero el diario, la
tarjeta de balance y la lógica de señales ya no la ven. Nadie la cerrará por ti.

**Orden correcto de los pasos:**

1. Cierra todas las posiciones abiertas en el exchange actual (en la app o en el exchange).
2. Comprueba que la lista de posiciones está vacía.
3. Cambia el exchange.
4. Verifica balance y posiciones en **Ajustes de operativa**.

---

## 6. Qué se conserva y qué no

| | Al cambiar |
|---|---|
| Diario de operaciones (histórico) | Se conserva — se calcula con datos de precio, no con el exchange |
| Parámetros de estrategias | Se conservan |
| Webhooks y avisos | Se conservan, compartidos por ambos |
| Lista de tickers operados | Se conserva, pero los símbolos se recalculan para el nuevo backend |
| Tarjeta de balance y PnL | Muestra el **nuevo** exchange; el histórico del anterior no se mezcla |
| Posiciones abiertas | **No se transfieren, no se cierran, no se siguen** |

El PnL se calcula por exchange, a partir de su propio histórico de income. No se
suman: distintos modelos de comisión y distintos calendarios de funding harían
que el total careciera de sentido.

---

## 7. Mapeo de símbolos

La mayoría de tickers coinciden, pero no todos:

- **PEPE** en Hyperliquid es `kPEPE` (precio y tamaño ×1000). El driver lo
  gestiona internamente; tú sigues escribiendo `PEPE`.
- **GRAM** en Hyperliquid es `GRAM`, en BingX es `GRAMTON`.
- Los activos tokenizados (p. ej. oro como XAUT) existen en el listado swap de
  BingX pero **no** tienen perpetuo en Hyperliquid — ese ticker solo se opera en BingX.

Si un símbolo no existe en el exchange activo, el envío de la orden falla con un
error que nombra el símbolo. Nada se envía en silencio.

---

## 8. Volver atrás

Para regresar al exchange anterior:

1. Cierra las posiciones en el actual.
2. Vuelve a cambiar.
3. Guarda.

Las claves del exchange anterior nunca se borraron, así que no hay que
reintroducirlas. Si quieres eliminarlas, **Eliminar claves** borra las del
exchange **activo** únicamente.

---

## 9. Enlaces de referencia

- Enlace de socio de BingX: <https://bingx.com/partner/rawa/>
- Enlace de socio de Hyperliquid: <https://app.hyperliquid.xyz/join/RAWA>
- Página de API wallets de Hyperliquid: <https://app.hyperliquid.xyz/API>

> Ambos enlaces son de referido. No cambian las comisiones del software y no son
> necesarios para que funcione.

---

*La operativa real está desactivada por defecto y corre enteramente bajo tu
responsabilidad. El software se ofrece "tal cual" y no es asesoramiento financiero.*
