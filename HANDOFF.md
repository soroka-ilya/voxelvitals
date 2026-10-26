# HANDOFF.md — VoxelVitals

## 1. Что сделано
- Разработана и протестирована полнофункциональная платформа мониторинга и телеметрии игровых серверов Minecraft (Java и Bedrock Edition) — **VoxelVitals**.
- Реализовано сетевое ядро опроса серверов через библиотеку `mcstatus` с поддержкой TCP Server List Ping, UDP RakNet query и автоматического разрешения DNS SRV записей.
- Разработан парсер и санитайзер MOTD (`motd_formatter.py`): преобразование кодов Minecraft (`§0`-`§f`, стилей `§l`, `§o`, `§n` и Hex-цветов `&#RRGGBB`) в безопасный HTML с защитой от XSS.
- Реализован генератор динамических векторных SVG-бейджей (`badge_service.py` и `/api/badge/{address}.svg`) в стиле Shields.io с HTTP-заголовками кэширования.
- Построено Time-Series хранилище на SQLite (режим WAL) с автоматическим фоновым поллером и записью 24-часовой истории онлайна и задержки.
- Сверстан современный темный веб-интерфейс (FastAPI + Jinja2 + Tailwind CSS + HTMX + Chart.js) со скелетон-лоадерами, поиском без перезагрузки страниц и страницами Privacy Policy / Terms of Service.
- Написан и успешно пройден набор из 23 автоматизированных тестов (`pytest -v`, 100% pass).
- Оформлен презентабельный `README.md` с бейджами, схемой архитектуры и инструкцией по развертыванию.

---

## 2. Принятые решения
- **Отказ от шаблонов (Anti-Vibecoding):** исключены неоновые фиолетовые шары, точечные сетки (dot-grids), бутафорские терминалы macOS, декоративные эмодзи и штампы в копирайтинге. Использована сдержанная темно-угольная палитра (`#0c0f17`) с акцентом изумрудного цвета и техническими шрифтами `Plus Jakarta Sans` и `JetBrains Mono`.
- **Единый асинхронный стек:** монолит на FastAPI + HTMX вместо разделения на отдельные репозитории с тяжелым React. Это упрощает бесплатный деплой (1 контейнер/сервис на Render или Railway) и ускоряет работу.
- **Отказоустойчивость:** внедрен fallback-механизм с мок-данными на случай недоступности внешней сети при тестировании.
- **Чистый Git-профиль:** все 20+ промежуточных учебных форков скрыты/удалены с GitHub-аккаунта `@soroka-ilya`. Проект `VoxelVitals` подготовлен как флагманский pet-project для демонстрации навыков Middle/Junior+ Python Backend.

---

## 3. Структура файлов проекта (`C:\Users\chebu\Documents\Dev\voxelvitals`)

```
C:\Users\chebu\Documents\Dev\voxelvitals/
├── app/
│   ├── api/
│   │   ├── api_routes.py        # REST API и генерация SVG-бейджей
│   │   └── routes.py            # Веб-страницы (Главная, Сервер, HTMX partials)
│   ├── domain/
│   │   └── models.py            # Pydantic v2 модели статуса, игроков и телеметрии
│   ├── services/
│   │   ├── badge_service.py     # Векторные SVG бейджи в стиле Shields.io
│   │   ├── motd_formatter.py    # Парсер цветного MOTD Minecraft
│   │   └── pinger.py            # Асинхронный опрос серверов mcstatus
│   ├── static/
│   │   ├── css/style.css        # Кастомные стили и скроллбары
│   │   └── js/chart_init.js     # Конфигурация темных графиков Chart.js
│   ├── templates/
│   │   ├── base.html            # Базовый layout с навбаром и футером
│   │   ├── index.html           # Главная страница с поиском и карточками
│   │   ├── server.html          # Детальная страница сервера с графиком онлайна
│   │   ├── privacy.html         # Политика конфиденциальности
│   │   ├── terms.html           # Условия использования
│   │   └── partials/            # HTMX-компоненты карточки сервера и скелетона
│   ├── config.py                # Настройки приложения и список избранных серверов
│   ├── database.py              # Инициализация SQLite в режиме WAL
│   ├── repository.py            # Асинхронный CRUD серверов и телеметрии
│   └── main.py                  # Точка входа FastAPI и фоновый воркер
├── tests/
│   ├── test_api.py              # Тесты веб-роутов, API и HTMX
│   ├── test_badge.py            # Тесты генератора SVG и экранирования XML
│   ├── test_motd.py             # Тесты форматирования цветов §a, §c, Hex и XSS
│   ├── test_pinger.py           # Тесты сетевого парсера и таймаутов
│   └── test_repository.py       # Тесты сохранения и выборки 24ч истории
├── .env.example                 # Шаблон переменных окружения
├── .gitignore                   # Исключение .venv, *.db, кешей
├── pytest.ini                   # Конфигурация тестов asyncio
├── requirements.txt             # Зависимости проекта
├── README.md                    # Презентационная документация
└── HANDOFF.md                   # Данный документ передачи проекта
```

---

## 4. Следующие шаги

1. **Публикация на GitHub:**
   - Создать публичный репозиторий `voxelvitals` на `github.com/new`.
   - Выполнить пуш:
     ```powershell
     cd C:\Users\chebu\Documents\Dev\voxelvitals
     git remote add origin https://github.com/soroka-ilya/voxelvitals.git
     git branch -M main
     git push -u origin main
     ```
   - Закрепить репозиторий в шапке профиля на GitHub (Pinned Repositories).

2. **Бесплатный деплой в облако (Live Demo):**
   - Зарегистрироваться на **Render.com** (или Railway.app).
   - Создать новый Web Service из репозитория `voxelvitals`.
   - Команда сборки: `pip install -r requirements.txt`.
   - Команда запуска: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
   - Получить публичную ссылку (например, `voxelvitals.onrender.com`) и добавить ее в `Live Demo` в README и резюме.

3. **Упаковка резюме:**
   - Указать в стеке: Python 3.12, FastAPI, Asyncio, SQLite/aiosqlite, Pytest, Docker, Nginx, HTMX, Tailwind.
   - Добавить ссылку на проект как подтверждение умения работать с сетевыми протоколами, асинхронностью, time-series данными и автотестами.
