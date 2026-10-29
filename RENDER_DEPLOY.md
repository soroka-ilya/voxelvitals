# Развертывание VoxelVitals на Render.com

Пошаговое руководство по выгрузке проекта на GitHub и запуску в облаке [Render.com](https://render.com) на бесплатном тарифе (Free Web Service) с боевой авторизацией Google и Microsoft.

---

## Шаг 1: Выгрузка проекта на GitHub

Если репозиторий ещё не создан на GitHub:

1. Перейдите на [github.com/new](https://github.com/new) и создайте новый репозиторий (например, `voxelvitals`). Выберите **Public** (или Private). Не добавляйте README и .gitignore (они уже есть в проекте).
2. В терминале вашего проекта свяжите локальный git с удаленным репозиторием и отправьте код:

```bash
cd C:\Users\chebu\Documents\Dev\voxelvitals

# Добавьте ваш удаленный репозиторий GitHub
git remote add origin https://github.com/ВАШ_ЛОГИН_GITHUB/voxelvitals.git

# Переименуйте основную ветку в master/main и отправьте код
git branch -M master
git push -u origin master
```

---

## Шаг 2: Создание сервиса на Render.com

### Вариант А: Быстрый запуск через Blueprint (Рекомендуемый)
1. Авторизуйтесь на [dashboard.render.com](https://dashboard.render.com).
2. Нажмите **New +** ➔ **Blueprint**.
3. Подключите ваш репозиторий `voxelvitals`.
4. Render автоматически прочитает файл `render.yaml` из корня проекта:
   - Имя: `voxelvitals`
   - Регион: `Frankfurt (EU)` (минимальный пинг)
   - Среда: `Python 3.12`
   - Команда сборки: `pip install -r requirements.txt`
   - Команда запуска: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers`
   - Проверка здоровья: `/api/health`
5. Нажмите **Apply**.

### Вариант Б: Ручное создание Web Service
Если создаете вручную через **New +** ➔ **Web Service**:
- **Name:** `voxelvitals`
- **Region:** `Frankfurt`
- **Runtime:** `Python 3`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers`
- **Instance Type:** `Free`

После создания Render выделит вашему сайту публичный домен, например:
👉 `https://voxelvitals.onrender.com` (или другое имя, которое вы указали).

---

## Шаг 3: Настройка боевого OAuth (Google & Microsoft)

Для того чтобы регистрация и вход работали на вашем живом сайте Render, укажите URL вашего сайта в консолях Google и Microsoft:

### 1. Google Cloud Console
1. Откройте [Google Cloud Console Credentials](https://console.cloud.google.com/apis/credentials).
2. Выберите ваш проект ➔ нажмите на созданный **OAuth 2.0 Client ID**.
3. В блоке **Authorized redirect URIs (Разрешенные URI перенаправления)** добавьте:
   ```text
   https://ВАШ_САЙТ.onrender.com/api/auth/google/callback
   ```
4. В блоке **Authorized JavaScript origins (Разрешенные источники JavaScript)** добавьте:
   ```text
   https://ВАШ_САЙТ.onrender.com
   ```
5. Нажмите **Save (Сохранить)**.

### 2. Microsoft Azure Portal
1. Откройте [Azure Portal ➔ App registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade).
2. Выберите ваше приложение ➔ перейдите в **Authentication (Аутентификация)**.
3. В разделе **Web ➔ Redirect URIs** добавьте:
   ```text
   https://ВАШ_САЙТ.onrender.com/api/auth/microsoft/callback
   ```
4. Нажмите **Save (Сохранить)**.

---

## Шаг 4: Настройка переменных окружения на Render

В панели Render перейдите в ваш сервис ➔ вкладка **Environment** ➔ добавьте переменные:

| Переменная | Значение (Пример) | Описание |
|---|---|---|
| `BASE_URL` | `https://voxelvitals.onrender.com` | Публичный адрес сайта без слэша на конце |
| `GOOGLE_CLIENT_ID` | `123456...apps.googleusercontent.com` | Client ID из Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | `GOCSPX-...` | Client Secret из Google Cloud Console |
| `GOOGLE_REDIRECT_URI` | `https://voxelvitals.onrender.com/api/auth/google/callback` | Redirect URI для Google |
| `MICROSOFT_CLIENT_ID` | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` | Application ID из Azure Portal |
| `MICROSOFT_CLIENT_SECRET` | `xxx~xxx...` | Client Secret из Azure Portal |
| `MICROSOFT_REDIRECT_URI` | `https://voxelvitals.onrender.com/api/auth/microsoft/callback` | Redirect URI для Microsoft |
| `DB_PATH` | `voxelvitals.db` | Файл SQLite базы данных |

Нажмите **Save Changes** — Render автоматически выполнит перезапуск с новыми ключами.

---

## Шаг 5: Проверка работоспособности

1. **Проверка здоровья (Health check):**
   Откройте в браузере:
   `https://ВАШ_САЙТ.onrender.com/api/health`
   Должен вернуться JSON:
   ```json
   {"status":"ok","version":"1.0.0","database":"connected"}
   ```

2. **Главная страница:**
   Откройте `https://ВАШ_САЙТ.onrender.com/`. Каталог серверов автоматически наполнится избранными серверами (Hypixel, CubeCraft, The Hive, NetherGames, DonutSMP) и начнет фоновый опрос онлайна.

3. **Вход через Google и Microsoft:**
   Нажмите кнопку «Войти» ➔ выберите Google или Microsoft ➔ завершите авторизацию.

---

## Особенности бесплатного тарифа Render Free
- При отсутствии входящих запросов в течение 15 минут контейнер переходит в спящий режим.
- При первом новом переходе сайт «просыпается» за ~30–50 секунд (Cold Start).
- База данных SQLite автоматически инициализируется при каждом запуске, поэтому сайт всегда готов к работе.
