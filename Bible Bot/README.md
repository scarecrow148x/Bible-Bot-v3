# Bible Bot - Telegram Bot

Telegram бот для чтения Библии с функциями поиска, заметок и совместного чтения.

## Функции

- 📖 Чтение книг Библии по главам
- 🔍 Поиск по названиям книг
- 📝 Добавление заметок к главам
- 🔗 Создание ссылок на Telegraph
- 👥 Совместное чтение в группах
- 📅 Рассылка стихов дня

## Деплой на Render

### Вариант 1: Через Render Dashboard

1. **Создайте новый Web Service на Render:**
   - Перейдите на [render.com](https://render.com)
   - Нажмите "New" → "Web Service"
   - Подключите ваш GitHub репозиторий

2. **Настройте параметры:**
   - **Name**: `bible-bot`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
   - **Environment Variables**: Добавьте `BOT_TOKEN` с вашим токеном бота

3. **Нажмите "Create Web Service"**

### Вариант 2: Через .render.yaml (рекомендуется)

1. **Добавьте переменную окружения в Render Dashboard:**
   - Перейдите в настройки вашего сервиса
   - Добавьте переменную `BOT_TOKEN` с вашим токеном бота

2. **Закоммитьте и запушьте изменения:**
   ```bash
   git add .
   git commit -m "Add Render configuration"
   git push origin main
   ```

3. **Render автоматически задеплоит приложение**

## Переменные окружения

- `BOT_TOKEN` - токен вашего Telegram бота (получите у @BotFather)

## Локальный запуск

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Запустите бота:
```bash
python bot.py
```

## Структура файлов

- `bot.py` - основной файл бота
- `bible.json` - данные Библии
- `requirements.txt` - зависимости Python
- `pyproject.toml` - конфигурация Poetry
- `.render.yaml` - конфигурация Render
- `Procfile` - конфигурация для Render
- `runtime.txt` - версия Python

## Устранение проблем

Если возникает ошибка с Poetry, убедитесь что:
1. Файл `pyproject.toml` присутствует в репозитории
2. Файл `requirements.txt` содержит все необходимые зависимости
3. В настройках Render указан правильный Build Command: `pip install -r requirements.txt` 