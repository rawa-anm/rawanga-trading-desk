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

# Установка на облачный сервер (VPS) — Rawanga Trading Desk

> **Прочитай это до того, как начнёшь.** Приложение спроектировано для
> **индивидуального, локального, однопользовательского** использования. В нём
> **нет входа, нет пароля на интерфейс и нет разделения пользователей**. Выставление
> его в интернет без мер ниже означает, что любой, кто узнает адрес, получает
> полный контроль — включая возможность включить реальную торговлю твоими ключами.
> Есть на трёх языках: `cloud.en.md`, `cloud.es.md`, `cloud.ru.md`.

---

## 0. Нужен ли тебе сервер

Облачный сервер имеет смысл, если терминал должен работать **24/7** (сигналы и
оповещения, когда твой компьютер выключен). Если он нужен только пока ты
работаешь — запускай локально: ни файрвола, ни TLS, ни выставления наружу,
ничего защищать не надо.

Если всё же идёшь в облако, четыре меры ниже **не опциональны**:

1. **Аутентификация** — логин перед приложением.
2. **Файрвол** — открыто только строго необходимое.
3. **TLS** — только HTTPS, никакого открытого HTTP.
4. **Бэкапы и обновления** — теперь на этой машине лежат твои ключи.

---

## 1. Требования к серверу

- Linux x64 (проверено на Ubuntu 22.04 / 24.04), 1 vCPU, 1 ГБ RAM, 10 ГБ диска.
- Исходящий доступ в интернет (рыночные данные + API биржи).
- **Никаких** входящих портов, кроме SSH и HTTPS.

Нужен Python 3.11+. Самых маленьких инстансов обычно хватает: приложение — это
один процесс FastAPI плюс SQLite.

---

## 2. Установка

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip git
sudo useradd -m -s /bin/bash trader
sudo -iu trader
git clone https://github.com/rawa-anm/rawanga-trading-desk.git
cd rawanga-trading-desk
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
# опционально — только для торговли на Hyperliquid:
pip install -r requirements-hl.txt
```

---

## 3. Слушать только loopback

**Никогда** не бинди приложение на `0.0.0.0` на публичном сервере. Оно должно
слушать `127.0.0.1` и быть доступным только через обратный прокси.

```bash
export RAWANGA_PORT=3000
export RAWANGA_HOST=127.0.0.1
python -m app.launcher
```

Для постоянной службы используй systemd-юнит из RTFM (`rtfm.*.md`, раздел
«Running on a server» / «Запуск на сервере») — он уже биндится на loopback.

---

## 4. Аутентификация — то, что обычно пропускают

Встроенного логина в приложении нет. Выбери **один** вариант:

### Вариант A — HTTP Basic в обратном прокси (проще всего)

```bash
sudo apt install -y nginx apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd you     # задай сильный пароль
```

`/etc/nginx/sites-available/desk`:

```nginx
server {
    listen 443 ssl http2;
    server_name desk.example.com;

    ssl_certificate     /etc/letsencrypt/live/desk.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/desk.example.com/privkey.pem;

    # Длинный случайный путь — второй слой секретности перед паролем.
    location /desk-<random-string>/ {
        auth_basic           "restricted";
        auth_basic_user_file /etc/nginx/.htpasswd;

        proxy_pass         http://127.0.0.1:3000/;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # WebSocket (живые обновления)
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
    }
}
```

Затем:
```bash
sudo ln -s /etc/nginx/sites-available/desk /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### Вариант B — туннель WireGuard / Tailscale (самый надёжный)

Не выставлять приложение наружу вообще: заходить в него через частный VPN.
Рекомендую именно это — тогда интерфейс невидим из интернета, и открыть его
могут только твои устройства.

### Чего делать НЕЛЬЗЯ

- Не открывай порт напрямую (`ufw allow 3000`) — без логина это полный контроль.
- Не рассчитывай на «секретный URL» как на аутентификацию.
- Не запускай от `root`.
- Не пропускай TLS, потому что «это же просто график».

---

## 5. Файрвол

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp        # SSH — лучше ограничить своим IP
sudo ufw allow 443/tcp       # только HTTPS (80 — на время ACME-проверки, потом закрыть)
sudo ufw enable
sudo ufw status verbose
```

Порт приложения (3000) в этом списке появляться **не должен**.

Дополнительно: у большинства облачных провайдеров есть **свой файрвол
(security group) в панели управления**, независимый от `ufw`. Закрой там всё,
кроме 22 и 443 — правило, забытое в панели, полностью обходит локальный файрвол.

---

## 6. Усиление SSH

```bash
# /etc/ssh/sshd_config.d/hardening.conf
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```

Сначала скопируй свой ключ, проверь вход **во второй сессии**, и только потом
перезагружай `sshd`. Потерять SSH на облачной машине означает её пересоздание.

Опционально, но полезно: `fail2ban` против повторных попыток входа по SSH.

---

## 7. Ключи и секреты на сервере

- Каталог данных содержит **зашифрованные** ключи бирж плюс файл мастер-ключа.
- Поставь строгие права: `chmod 700 <каталог-данных>`; файлы ключей создаются `0600`.
- **Шифруй диск**, если провайдер это поддерживает — иначе любой с доступом к
  гипервизору прочитает базу.
- Никогда не клади ключи в переменные окружения общего хоста, в историю шелла
  или в репозиторий.

Если у кого-то есть root на этом сервере — у него есть твои ключи. Это не баг
приложения, это арифметика.

---

## 8. Бэкапы

Бэкапь **весь каталог данных** (база + зашифрованные ключи + мастер-ключи).
Без файлов мастер-ключей зашифрованные секреты нечитаемы — сохраняй их вместе,
а архив держи вне сервера.

```bash
# пример: ночной архив в приватное место
tar czf /var/backups/desk-$(date +%F).tgz -C /home/trader/rawanga-trading-desk data
```

Один раз проверь восстановление. Непроверенный бэкап — это надежда, а не бэкап.

---

## 9. Обновления

```bash
cd ~/rawanga-trading-desk
git pull
. .venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart rawanga-desk
```

Перед обновлением прочитай ченджлог: могли измениться настройки, формат данных
или поведение торговли.

---

## 10. Чеклист перед тем, как считать готовым

- [ ] Приложение слушает только `127.0.0.1` (`ss -tlnp | grep 3000`)
- [ ] HTTPS работает, HTTP перенаправляется на него
- [ ] Требуется логин (проверь в приватном окне)
- [ ] Файрвол: открыты только 22 и 443, панель провайдера совпадает
- [ ] SSH: root-вход выключен, парольный вход выключен, ключ проверен
- [ ] Работает от непривилегированного пользователя
- [ ] Каталог данных `700`, файлы ключей `600`
- [ ] Бэкап создан **и один раз восстановлен** в отдельный каталог
- [ ] Реальная торговля ВЫКЛЮЧЕНА, пока ты осознанно её не включишь

---

> **Честно:** этот софт сделан для одного человека на его собственной машине.
> Публичный сервер превращает его в службу, которую надо защищать. Если ты не
> готов поддерживать аутентификацию, TLS и правила файрвола — используй
> VPN-туннель (вариант B) или запускай локально.
