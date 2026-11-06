# 📋 Project Handoff — VoxelVitals

**Дата обновления:** 2026-11-06 22:25  
**Текущая цель:** Деплой VoxelVitals на VPS FirstByte и привязка домена `voxelvitals.ru` с поддержкой HTTPS **ПОЛНОСТЬЮ ЗАВЕРШЕНЫ**! Проект находится в стабильном боевом режиме (production).

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

## 4. Текущий статус деплоя и инфраструктуры

### ✅ Все этапы успешно завершены (Production Live):
1. **VPS**: Ubuntu 22.04 LTS на FirstByte (`45.144.65.27`, IPv6 `2a0c:5d00:3001::5335:6d85`).
2. **Systemd сервис**: `voxelvitals.service` активен, автозапуск при ребуте, 2 воркера Uvicorn, фоновый сборщик телеметрии серверов.
3. **Nginx Reverse Proxy**: настроен и защищён, проксирует HTTP/HTTPS трафик на порт 8000.
4. **DNS**: в Timeweb настроены A и AAAA записи для `voxelvitals.ru` и `www.voxelvitals.ru`.
5. **SSL (HTTPS)**: получен официальный сертификат Let's Encrypt, настроен автоматический HTTP->HTTPS редирект (301) и фоновое автопродление (`certbot.timer`).

---

## 🚀 Ссылки на продакшен:
- **Основной сайт (HTTPS):** [https://voxelvitals.ru](https://voxelvitals.ru)
- **Зеркало с www (HTTPS):** [https://www.voxelvitals.ru](https://www.voxelvitals.ru)
- **API Healthcheck:** [https://voxelvitals.ru/api/health](https://voxelvitals.ru/api/health)
- **Swagger / OpenAPI документация:** [https://voxelvitals.ru/docs](https://voxelvitals.ru/docs)
