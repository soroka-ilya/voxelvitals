# VoxelVitals — Руководство по развертыванию в продакшен

VoxelVitals готов к деплою на любой современный облачный хостинг, VPS или Docker-кластер.

---

## Вариант 1: Запуск через Docker Compose (Рекомендуемый)

Контейнер изолирован, работает от непривилегированного пользователя `appuser`, проверяет собственное здоровье через `/api/health` и сохраняет базу данных в отдельный том `voxelvitals_data`.

```bash
# 1. Клонирование репозитория
git clone https://github.com/your-username/voxelvitals.git
cd voxelvitals

# 2. Настройка переменных окружения
cp .env.example .env

# 3. Сборка и запуск контейнера в фоне
docker compose up -d --build

# 4. Проверка состояния и логов
docker compose ps
docker compose logs -f
```

Сайт будет доступен по адресу `http://localhost:8000` (или внешнему IP вашего сервера).

---

## Вариант 2: Мгновенный деплой в облако (Railway / Render)

### Railway
1. Подключите репозиторий на [railway.app](https://railway.app).
2. Railway автоматически обнаружит `Dockerfile` или `Procfile`.
3. Добавьте том (Volume) с точкой монтирования `/app/data`, чтобы SQLite база сохранялась между перезапусками.
4. Укажите переменную `DB_PATH=/app/data/voxelvitals.db`.
5. Нажмите **Deploy**.

### Render
1. Создайте новый **Web Service** на [render.com](https://render.com).
2. Выберите среду **Docker** или **Python 3**.
3. Если выбран Python:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers`
4. Добавьте диск (Disk) с точкой монтирования `/app/data` и укажите `DB_PATH=/app/data/voxelvitals.db`.

---

## Вариант 3: Linux VPS (Ubuntu 22.04 / 24.04 + Systemd + Nginx + SSL)

### 1. Подготовка системы
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip nginx certbot python3-certbot-nginx git
```

### 2. Клонирование и виртуальное окружение
```bash
sudo mkdir -p /var/www/voxelvitals
sudo chown -R $USER:$USER /var/www/voxelvitals
cd /var/www/voxelvitals
git clone https://github.com/your-username/voxelvitals.git .

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Настройка Systemd сервиса
Создайте `/etc/systemd/system/voxelvitals.service`:
```ini
[Unit]
Description=VoxelVitals Minecraft Server Status & Analytics Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/voxelvitals
Environment="PATH=/var/www/voxelvitals/.venv/bin"
Environment="HOST=127.0.0.1"
Environment="PORT=8000"
Environment="DB_PATH=/var/www/voxelvitals/voxelvitals.db"
ExecStart=/var/www/voxelvitals/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Запуск:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now voxelvitals
sudo systemctl status voxelvitals
```

### 4. Настройка Nginx и бесплатного SSL (Let's Encrypt)
Создайте `/etc/nginx/sites-available/voxelvitals`:
```nginx
server {
    server_name your-domain.com www.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Активация и получение SSL-сертификата:
```bash
sudo ln -s /etc/nginx/sites-available/voxelvitals /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

---

## Мониторинг и Health Check

- Эндпоинт проверки здоровья: `GET /api/health`
  Ответ:
  ```json
  {
    "status": "ok",
    "version": "1.0.0",
    "database": "connected"
  }
  ```
- Панель аналитики и телеметрии (для админов): `GET /analytics`
