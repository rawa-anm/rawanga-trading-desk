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

# Instalar en un servidor en la nube (VPS) — Rawanga Trading Desk

> **Lee esto antes de empezar.** La aplicación está diseñada para uso
> **individual, local y de un solo usuario**. **No tiene inicio de sesión, ni
> contraseña en la interfaz, ni separación de usuarios.** Exponerla a internet
> sin las medidas de abajo da control total a cualquiera que descubra la
> dirección — incluida la posibilidad de activar la operativa real con tus claves.
> Disponible en tres idiomas: `cloud.en.md`, `cloud.es.md`, `cloud.ru.md`.

---

## 0. ¿De verdad necesitas un servidor?

Un servidor en la nube tiene sentido si quieres el terminal funcionando **24/7**
(señales y avisos con tu equipo apagado). Si solo lo necesitas mientras trabajas,
ejecútalo en local: sin firewall, sin TLS, sin exposición, nada que endurecer.

Si vas a la nube, las cuatro medidas siguientes **no son opcionales**:

1. **Autenticación** — un login delante de la app.
2. **Firewall** — expuesto solo lo estrictamente necesario.
3. **TLS** — solo HTTPS, nunca HTTP en claro.
4. **Copias y actualizaciones** — ahora esa máquina guarda tus claves.

---

## 1. Requisitos del servidor

- Linux x64 (probado en Ubuntu 22.04 / 24.04), 1 vCPU, 1 GB RAM, 10 GB disco.
- Salida a internet (datos de mercado + API del exchange).
- **Ningún** puerto de entrada salvo SSH y HTTPS.

Se requiere Python 3.11+. Las instancias más pequeñas suelen bastar: la app es un
único proceso FastAPI más SQLite.

---

## 2. Instalación

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip git
sudo useradd -m -s /bin/bash trader
sudo -iu trader
git clone https://github.com/rawa-anm/rawanga-trading-desk.git
cd rawanga-trading-desk
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
# opcional — solo para operar en Hyperliquid:
pip install -r requirements-hl.txt
```

---

## 3. Escuchar solo en loopback

**Nunca** enlaces la app a `0.0.0.0` en un servidor público. Debe escuchar en
`127.0.0.1` y ser accesible solo a través del proxy inverso.

```bash
export RAWANGA_PORT=3000
export RAWANGA_HOST=127.0.0.1
python -m app.launcher
```

Para un servicio permanente usa la unidad systemd de la guía RTFM
(`rtfm.*.md`, sección "Running on a server" / "Ejecutar en un servidor"), que ya
enlaza a loopback.

---

## 4. Autenticación — la parte que se suele omitir

La app no tiene login integrado. Elige **una** opción:

### Opción A — HTTP Basic en el proxy inverso (lo más simple)

```bash
sudo apt install -y nginx apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd you     # pon una contraseña fuerte
```

`/etc/nginx/sites-available/desk`:

```nginx
server {
    listen 443 ssl http2;
    server_name desk.example.com;

    ssl_certificate     /etc/letsencrypt/live/desk.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/desk.example.com/privkey.pem;

    # Una ruta aleatoria larga añade una segunda capa de secreto.
    location /desk-<random-string>/ {
        auth_basic           "restricted";
        auth_basic_user_file /etc/nginx/.htpasswd;

        proxy_pass         http://127.0.0.1:3000/;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # Soporte WebSocket (actualizaciones en vivo)
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
    }
}
```

Luego:
```bash
sudo ln -s /etc/nginx/sites-available/desk /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### Opción B — túnel WireGuard / Tailscale (lo más seguro)

No exponer la app en absoluto: acceder por VPN privada. Es la opción
recomendada — la interfaz queda invisible desde internet y solo tus dispositivos
pueden abrirla.

### Lo que NO hay que hacer

- No expongas el puerto directamente (`ufw allow 3000`) — sin login es control total.
- No confíes en una "URL secreta" como autenticación.
- No lo ejecutes como `root`.
- No omitas TLS porque "es solo un gráfico".

---

## 5. Firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp        # SSH — mejor: restríngelo a tu IP
sudo ufw allow 443/tcp       # solo HTTPS (80 para el reto ACME, luego ciérralo)
sudo ufw enable
sudo ufw status verbose
```

El puerto de la aplicación (3000) **no** debe aparecer en la lista.

Además, la mayoría de proveedores tienen un **firewall propio (security group) en
el panel**, independiente de `ufw`. Cierra allí todo salvo 22 y 443 — una regla
olvidada en el panel se salta por completo el firewall local.

---

## 6. Endurecer SSH

```bash
# /etc/ssh/sshd_config.d/hardening.conf
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```

Copia tu clave primero, verifica que puedes entrar **en una segunda sesión**, y
solo entonces recarga `sshd`. Perder el SSH en una máquina en la nube significa
recrearla.

Opcional pero recomendable: `fail2ban` contra intentos repetidos de SSH.

---

## 7. Claves y secretos en el servidor

- El directorio de datos guarda las claves **cifradas** de los exchanges más el
  archivo de clave maestra.
- Permisos estrictos: `chmod 700 <dir-datos>`; los archivos de clave se crean `0600`.
- **Cifra el disco** si el proveedor lo permite — si no, cualquiera con acceso al
  hipervisor lee la base de datos.
- Nunca pongas claves en variables de entorno de un host compartido, en el
  historial del shell ni en el repositorio.

Si alguien tiene root en ese servidor, tiene tus claves. No es un fallo de la
app: es aritmética.

---

## 8. Copias de seguridad

Copia **todo el directorio de datos** (base + claves cifradas + claves maestras).
Sin los archivos de clave maestra los secretos cifrados son ilegibles — guárdalos
juntos y mantén el archivo fuera del servidor.

```bash
# ejemplo: archivo nocturno en una ubicación privada
tar czf /var/backups/desk-$(date +%F).tgz -C /home/trader/rawanga-trading-desk data
```

Prueba la restauración una vez. Una copia sin probar es una esperanza, no una copia.

---

## 9. Actualizaciones

```bash
cd ~/rawanga-trading-desk
git pull
. .venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart rawanga-desk
```

Lee el changelog antes de actualizar: pueden haber cambiado ajustes, formato de
datos o el comportamiento de la operativa.

---

## 10. Lista de comprobación antes de darlo por hecho

- [ ] La app escucha solo en `127.0.0.1` (`ss -tlnp | grep 3000`)
- [ ] HTTPS funciona y HTTP redirige a él
- [ ] Se exige login (pruébalo en una ventana privada)
- [ ] Firewall: solo 22 y 443, el panel del proveedor coincide
- [ ] SSH: root desactivado, contraseña desactivada, clave verificada
- [ ] Se ejecuta como usuario sin privilegios
- [ ] Directorio de datos `700`, archivos de clave `600`
- [ ] Copia creada **y restaurada una vez** en un directorio aparte
- [ ] Operativa real DESACTIVADA hasta que la actives a propósito

---

> **Resumen honesto:** este software está hecho para una persona en su propia
> máquina. Un servidor público lo convierte en un servicio que hay que defender.
> Si no vas a mantener autenticación, TLS y reglas de firewall, usa un túnel VPN
> (opción B) o ejecútalo en local.
