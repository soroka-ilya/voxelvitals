# 📋 Project Handoff — VoxelVitals

**Дата обновления:** 2026-11-05 22:50  
**Текущая цель:** Развертывание (деплой) проекта VoxelVitals на купленный VPS сервер FirstByte с привязкой домена `voxelvitals.ru` (Timeweb) и выпуском бесплатного SSL-сертификата (HTTPS).

---

## 1. Контекст инфраструктуры для деплоя

| Параметр | Значение | Примечания |
|---|---|---|
| **Домен** | `voxelvitals.ru` | Куплен на **Timeweb** |
| **Хостинг VPS** | **FirstByte** | Тариф: MSK-KVM-SSD VL |
| **IP-адрес сервера** | `45.144.65.27` | Белый статический IPv4 |
| **Имя хоста ВМ** | `vm4863308.firstbyte.club` | ОС: Ubuntu (22.04/24.04 LTS) |
| **SSH доступ** | `root` / `ClBkh4u$/,1~X?:,` | Порт: `22` (стандартный) |
| **Репозиторий GitHub** | `https://github.com/soroka-ilya/voxelvitals.git` | Ветка: `master` (актуальна, протестирована) |

---

## 2. Что сделано в проекте (Текущее состояние кодовой базы)
- **Полный стек:** Python 3.12 + FastAPI + aiosqlite + Jinja2 + TailwindCSS + Docker / Docker Compose.
- **Интерактивный хаб лаунчеров (Quick Connect Hub):**
  - Поддержка любых Java-лаунчеров (TLauncher, Официальный Mojang, Prism Launcher, Modrinth, MultiMC) с мгновенным копированием IP в буфер и 3-шаговым визуальным гидом.
  - 1-клик запуск через официальные протоколы `lunarclient://` (Lunar Client) и `badlion://` (Badlion Client).
  - Поддержка Bedrock Edition с отдельным копированием Host и Port (`19132`), подсказка о встроенном сервере для The Hive и CubeCraft.
  - Возможность запоминания любимого лаунчера в `localStorage` и сплит-кнопка с шевроном `▼` для смены в любой момент.
- **Брендовые векторные SVG-иконки для Bedrock:** The Hive Bedrock, NetherGames, MCPE generic.
- **Удалены лишние плашки:** полностью убраны галерея скриншотов и интерактивный статус-бейдж со страниц серверов по запросу пользователя.
- **Сбор аналитики и телеметрии:** отслеживание просмотров страниц, поисковых запросов, кликов по лаунчерам, фоновый воркер опроса серверов раз в 5 минут и очистка данных старше 24 часов.
- **OAuth авторизация:** маршруты Google и Microsoft (`/api/auth/google/login`, `/api/auth/microsoft/login`, с mock-режимом для dev/fallback).
- **Эндпоинты здоровья:** `/api/health` и `/healthz` (возвращают 200 OK и статус БД).
- **Тесты:** все **75 тестов** (`pytest -q`) проходят успешно со 100% результатом.

---

## 3. Ключевые архитектурные решения и ограничения (Не менять!)
1. **База данных:** SQLite через `aiosqlite` хранится в `voxelvitals.db` (в контейнере путь монтируется в том `/app/data/voxelvitals.db`). Автоматически инициализирует схемы и таблицы при старте (`init_db()`), сидирует избранные серверы (Hypixel, CubeCraft, The Hive, NetherGames, DonutSMP).
2. **Безопасность SSH и порты:** на сервере веб-приложение должно быть скрыто за Nginx reverse-proxy, который слушает порты 80/443 и проксирует трафик на `127.0.0.1:8000`.
3. **SSL/TLS:** автоматический бесплатный сертификат Let's Encrypt через `certbot --nginx -d voxelvitals.ru -d www.voxelvitals.ru`.
4. **Конфигурация окружения:** `BASE_URL=https://voxelvitals.ru`, `HOST=127.0.0.1`, `PORT=8000`, `DB_PATH=/var/www/voxelvitals/voxelvitals.db` (или Docker volume).

---

## 4. Следующие шаги для деплоя (Next Steps)

### Шаг 1: Настройка DNS на Timeweb
В панели управления доменом на Timeweb прописать 2 A-записи, указывающие на VPS:
- `@` ➔ `45.144.65.27`
- `www` ➔ `45.144.65.27`

### Шаг 2: Первичное подключение к серверу по SSH
```bash
ssh root@45.144.65.27
# Ввести пароль: ClBkh4u$/,1~X?:,
```

### Шаг 3: Установка пакетов на сервере
```bash
apt update && apt upgrade -y
apt install -y git curl python3-pip python3-venv nginx certbot python3-certbot-nginx
```

### Шаг 4: Клонирование и настройка VoxelVitals
```bash
mkdir -p /var/www/voxelvitals
git clone https://github.com/soroka-ilya/voxelvitals.git /var/www/voxelvitals
cd /var/www/voxelvitals

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Шаг 5: Настройка Systemd сервиса для автозапуска
Создать `/etc/systemd/system/voxelvitals.service`:
```ini
[Unit]
Description=VoxelVitals Minecraft Server Status & Analytics Engine
After=network.target

[Service]
User=root
WorkingDirectory=/var/www/voxelvitals
Environment="PATH=/var/www/voxelvitals/.venv/bin"
Environment="HOST=127.0.0.1"
Environment="PORT=8000"
Environment="DB_PATH=/var/www/voxelvitals/voxelvitals.db"
Environment="BASE_URL=https://voxelvitals.ru"
ExecStart=/var/www/voxelvitals/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
Активировать сервис:
```bash
systemctl daemon-reload
systemctl enable --now voxelvitals
systemctl status voxelvitals
```

### Шаг 6: Настройка Nginx и SSL (HTTPS)
Создать конфиг `/etc/nginx/sites-available/voxelvitals`:
```nginx
server {
    server_name voxelvitals.ru www.voxelvitals.ru;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Активировать сайт и выпустить сертификат:
```bash
ln -s /etc/nginx/sites-available/voxelvitals /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
certbot --nginx -d voxelvitals.ru -d www.voxelvitals.ru --non-interactive --agree-tos -m ilya010s@mail.ru
```

### Шаг 7: Верификация
Проверить открытие `https://voxelvitals.ru` и `https://voxelvitals.ru/api/health` в браузере.

---

## 🚀 Промпт для нового чата (Скопируйте в новый диалог):
> Прочитай файл HANDOFF.md в корне проекта и приступай к развертыванию сайта на VPS FirstByte (45.144.65.27) с доменом voxelvitals.ru по шагам из раздела "Следующие шаги для деплоя".
