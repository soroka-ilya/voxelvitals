# Руководство по настройке авторизации через Google и Microsoft

В **VoxelVitals** встроена поддержка единого входа (SSO) через **Google** и **Microsoft (Xbox Live / Minecraft)**.

---

## 1. Настройка Google OAuth 2.0

### Шаг 1: Создание проекта в Google Cloud
1. Перейдите в [Google Cloud Console](https://console.cloud.google.com/).
2. Создайте новый проект (например, `VoxelVitals`).

### Шаг 2: Настройка экрана согласия (OAuth Consent Screen)
1. В боковом меню перейдите в **APIs & Services** -> **OAuth consent screen**.
2. Выберите тип пользователя **External** (Внешний) и нажмите **Create**.
3. Заполните обязательные поля:
   - **App name**: `VoxelVitals`
   - **User support email**: ваш email
   - **Developer contact information**: ваш email
4. На шаге **Scopes** нажмите **Add or Remove Scopes** и отметьте:
   - `.../auth/userinfo.email`
   - `.../auth/userinfo.profile`
   - `openid`
5. Сохраните настройки.

### Шаг 3: Создание Client ID и Client Secret
1. Перейдите в раздел **Credentials** -> нажмите **+ Create Credentials** -> **OAuth client ID**.
2. В поле **Application type** выберите **Web application**.
3. В секции **Authorized redirect URIs** (Разрешенные URI перенаправления) добавьте:
   - Для локальной разработки:
     `http://localhost:8000/api/auth/google/callback`
   - Для продакшена:
     `https://your-domain.com/api/auth/google/callback`
4. Нажмите **Create** и скопируйте:
   - **Client ID**
   - **Client Secret**

---

## 2. Настройка Microsoft OAuth + Xbox Live / Minecraft

### Шаг 1: Регистрация приложения в Azure Portal
1. Перейдите в [Azure Portal / App Registrations](https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade).
2. Нажмите **New registration** (Новая регистрация).
3. Заполните форму:
   - **Name**: `VoxelVitals`
   - **Supported account types**: выберите **Accounts in any organizational directory and personal Microsoft accounts (e.g. Skype, Xbox)** (любые личные учетные записи Microsoft и Xbox).
   - **Redirect URI**: выберите платформу **Web** и укажите:
     `http://localhost:8000/api/auth/microsoft/callback` (для продакшена: `https://your-domain.com/api/auth/microsoft/callback`).
4. Нажмите **Register**. Скопируйте **Application (client) ID**.

### Шаг 2: Создание Client Secret
1. В боковом меню перейдите в **Certificates & secrets** -> вкладка **Client secrets**.
2. Нажмите **+ New client secret**, введите описание (например, `web-client`) и срок действия.
3. Скопируйте значение из столбца **Value** (обратите внимание: значение показывается только один раз).

### Шаг 3: Разрешения API (API Permissions)
1. В меню выберите **API permissions** -> **+ Add a permission** -> **Microsoft Graph**:
   - `User.Read`
   - `email`
   - `offline_access`
   - `openid`
   - `profile`
2. Также для доступа к Xbox/Minecraft убедитесь, что в scope запроса передаётся `XboxLive.signin` (уже настроено в коде VoxelVitals).

---

## 3. Подключение ключей в `.env`

Откройте ваш файл `.env` в корне проекта (или скопируйте из `.env.example`) и вставьте полученные данные:

```env
# Базовый адрес вашего сайта
BASE_URL=http://localhost:8000

# Google OAuth
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback

# Microsoft OAuth
MICROSOFT_CLIENT_ID=your_microsoft_client_id
MICROSOFT_CLIENT_SECRET=your_microsoft_client_secret
MICROSOFT_REDIRECT_URI=http://localhost:8000/api/auth/microsoft/callback
```

---

## 4. Локальное тестирование без ключей (Dev Mock)

Для тестирования в процессе локальной разработки или запуска автоматических тестов предусмотрен параметр `?mock=true`:
- Google: `http://localhost:8000/api/auth/google/login?mock=true`
- Microsoft: `http://localhost:8000/api/auth/microsoft/login?mock=true`

Это мгновенно авторизует тестового пользователя с проверкой всей цепочки создания сессий, базы данных и отображения профиля.
