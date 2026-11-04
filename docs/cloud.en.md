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

# Running on a cloud server (VPS) — Rawanga Trading Desk

> **Read this before you start.** The application was designed for **individual,
> local, single-user** use. It has **no login, no password on the interface and
> no user separation**. Exposing it to the internet without the measures below
> gives anyone who finds the address full control — including the ability to
> enable real trading with your keys.
> Available in three languages: `cloud.en.md`, `cloud.es.md`, `cloud.ru.md`.

---

## 0. Do you actually need a server?

A cloud server makes sense if you want the terminal running **24/7** (signals and
alerts while your machine is off). If you only need it while you work, run it
locally — no firewall, no TLS, no exposure, nothing to harden.

If you do go to the cloud, the four measures below are **not optional**:

1. **Authentication** — put a login in front of it.
2. **Firewall** — expose only what is strictly needed.
3. **TLS** — HTTPS only, never plain HTTP.
4. **Backups + updates** — the machine now holds your keys.

---

## 1. Server requirements

- Linux x64 (Ubuntu 22.04 / 24.04 tested), 1 vCPU, 1 GB RAM, 10 GB disk.
- Outbound internet access (market data + exchange API).
- **No** inbound ports except SSH and HTTPS.

Python 3.11+ is required. The smallest instances are usually enough: the app is
a single FastAPI process plus SQLite.

---

## 2. Install

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip git
sudo useradd -m -s /bin/bash trader
sudo -iu trader
git clone https://github.com/rawa-anm/rawanga-trading-desk.git
cd rawanga-trading-desk
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
# optional — only for Hyperliquid trading:
pip install -r requirements-hl.txt
```

---

## 3. Bind to loopback only

**Never** bind the app to `0.0.0.0` on a public server. It must listen on
`127.0.0.1` and be reachable only through the reverse proxy.

```bash
export RAWANGA_PORT=3000
export RAWANGA_HOST=127.0.0.1
python -m app.launcher
```

For a permanent service, use the systemd unit from the RTFM guide
(`rtfm.*.md`, section "Running on a server"), which already binds to loopback.

---

## 4. Authentication — the part people skip

The app has no built-in login. Choose **one** of these:

### Option A — HTTP Basic auth in the reverse proxy (simplest)

```bash
sudo apt install -y nginx apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd you     # set a strong password
```

`/etc/nginx/sites-available/desk`:

```nginx
server {
    listen 443 ssl http2;
    server_name desk.example.com;

    ssl_certificate     /etc/letsencrypt/live/desk.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/desk.example.com/privkey.pem;

    # A long random path adds a second secret layer before the password.
    location /desk-<random-string>/ {
        auth_basic           "restricted";
        auth_basic_user_file /etc/nginx/.htpasswd;

        proxy_pass         http://127.0.0.1:3000/;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # WebSocket support (live updates)
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
    }
}
```

Then:
```bash
sudo ln -s /etc/nginx/sites-available/desk /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### Option B — WireGuard / Tailscale tunnel (strongest)

Do not expose the app at all: reach it over a private VPN. This is the option we
recommend — the interface is then invisible to the internet entirely, and only
your own devices can open it.

### What NOT to do

- Do not expose the port directly (`ufw allow 3000`) — no login means full control.
- Do not rely on a "secret URL" alone as authentication.
- Do not run it as `root`.
- Do not skip TLS because "it is just a chart".

---

## 5. Firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp        # SSH — better: restrict to your own IP
sudo ufw allow 443/tcp       # HTTPS only (port 80 for the ACME challenge, then close it)
sudo ufw enable
sudo ufw status verbose
```

The application port (3000) must **not** appear in the list.

Additionally, most cloud providers have a **security group / firewall in the
control panel** independent of `ufw`. Close everything there except 22 and 443 —
a rule forgotten in the panel bypasses the local firewall completely.

---

## 6. SSH hardening

```bash
# /etc/ssh/sshd_config.d/hardening.conf
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```

Copy your key first, verify you can log in **in a second session**, and only then
reload `sshd`. Losing SSH access on a cloud box means rebuilding it.

Optional but recommended: `fail2ban` for repeated SSH auth failures.

---

## 7. Keys and secrets on the server

- The data directory holds **encrypted** exchange keys plus the master key file.
- Set strict permissions: `chmod 700 <data-dir>`; the key files are created `0600`.
- **Encrypt the disk** if the provider supports it — otherwise anyone with
  physical/hypervisor access reads the database.
- Never put keys in environment variables of a shared host, in shell history, or
  in the repository.

If someone else has root on that server, they have your keys. That is not a bug
in this app — it is arithmetic.

---

## 8. Backups

Back up the **entire data directory** (database + encrypted keys + master keys).
Without the master key files the encrypted secrets are unreadable — back them up
together, and store the archive somewhere other than the server.

```bash
# example: nightly archive to a private location
tar czf /var/backups/desk-$(date +%F).tgz -C /home/trader/rawanga-trading-desk data
```

Test the restore once. An untested backup is a hope, not a backup.

---

## 9. Updates

```bash
cd ~/rawanga-trading-desk
git pull
. .venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart rawanga-desk
```

Read the changelog before updating: settings, data format or trading behaviour
may have changed.

---

## 10. Checklist before you call it done

- [ ] App is listening on `127.0.0.1` only (`ss -tlnp | grep 3000`)
- [ ] HTTPS works and HTTP redirects to it
- [ ] A login is required (test in a private window)
- [ ] Firewall: only 22 and 443 open, provider panel matches
- [ ] SSH: root login off, password auth off, key verified
- [ ] Runs as an unprivileged user
- [ ] Data directory is `700`, key files `600`
- [ ] Backup created **and restored once** into a scratch directory
- [ ] Real trading is OFF until you deliberately enable it

---

> **The honest summary:** this software is built for one person on their own
> machine. A public server turns it into a service that must be defended. If you
> are not prepared to maintain authentication, TLS and firewall rules, use a
> VPN tunnel (option B) or run it locally.
