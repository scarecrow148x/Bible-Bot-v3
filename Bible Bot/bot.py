import json
from telegraph import Telegraph
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import os
import re
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, date, timedelta
from telegram.constants import ChatType
from telegram.ext import ConversationHandler as TGConversationHandler

# Загрузка текста Библии
with open('bible.json', 'r', encoding='utf-8') as f:
    BIBLE = json.load(f)

LINKS_FILE = 'telegraph_links.json'
if os.path.exists(LINKS_FILE):
    with open(LINKS_FILE, 'r', encoding='utf-8') as f:
        TELEGRAPH_LINKS = json.load(f)
else:
    TELEGRAPH_LINKS = {}

SUBSCRIBERS_FILE = 'subscribers.json'
if os.path.exists(SUBSCRIBERS_FILE):
    with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
        SUBSCRIBERS = set(json.load(f))
else:
    SUBSCRIBERS = set()

NOTES_FILE = 'notes.json'
if os.path.exists(NOTES_FILE):
    with open(NOTES_FILE, 'r', encoding='utf-8') as f:
        ALL_NOTES = json.load(f)
else:
    ALL_NOTES = {}

CHANNEL_FILE = 'channel.json'
if os.path.exists(CHANNEL_FILE):
    with open(CHANNEL_FILE, 'r', encoding='utf-8') as f:
        CHANNEL_ID = json.load(f).get('channel_id')
else:
    CHANNEL_ID = None

GROUP_READING_FILE = 'group_reading.json'
if os.path.exists(GROUP_READING_FILE):
    with open(GROUP_READING_FILE, 'r', encoding='utf-8') as f:
        GROUP_READING = json.load(f)
else:
    GROUP_READING = {}

telegraph = Telegraph()
telegraph.create_account(short_name="biblebot")

CHOOSE_BOOK, CHOOSE_CHAPTER, CHAPTER_MENU, BOOK_SEARCH, ADD_NOTE, CHOOSE_PLAN = range(6)

# Списки книг по заветам
OLD_TESTAMENT = [
    "Бытие", "Исход", "Левит", "Числа", "Второзаконие",
    "Иисус Навин", "Судьи", "Руфь", "1 Царств", "2 Царств",
    "3 Царств", "4 Царств", "1 Паралипоменон", "2 Паралипоменон", "Ездра",
    "Неемия", "Есфирь", "Иов", "Псалтирь", "Притчи",
    "Екклесиаст", "Песнь песней", "Исаия", "Иеремия", "Плач Иеремии",
    "Иезекииль", "Даниил", "Осия", "Иоиль", "Амос",
    "Авдий", "Иона", "Михей", "Наум", "Аввакум",
    "Софония", "Аггей", "Захария", "Малахия"
]
NEW_TESTAMENT = [
    "От Матфея", "От Марка", "От Луки", "От Иоанна", "Деяния",
    "К Римлянам", "1 Коринфянам", "2 Коринфянам", "К Галатам", "К Ефесянам",
    "К Филиппийцам", "К Колоссянам", "1 Фессалоникийцам", "2 Фессалоникийцам", "1 Тимофею",
    "2 Тимофею", "К Титу", "К Филимону", "К Евреям", "Иаков",
    "1 Петра", "2 Петра", "1 Иоанна", "2 Иоанна", "3 Иоанна",
    "Иуда", "Откровение"
]

# --- Вспомогательные функции ---
def get_all_books():
    return list(BIBLE.keys())

def get_all_chapters(book):
    return list(BIBLE[book].keys())

def get_telegraph_link(book, chapter, verses):
    key = f"{book}|{chapter}"
    if key in TELEGRAPH_LINKS:
        return TELEGRAPH_LINKS[key]
    # Формируем HTML для Telegraph: каждый стих в отдельном <p> с жирным номером
    html = f"<b>{book} {chapter} глава</b>" + ''.join([f"<p><b>{i+1}</b>. {v}</p>" for i, v in enumerate(verses)])
    response = telegraph.create_page(
        title=f"{book} {chapter}",
        html_content=html
    )
    link = 'https://telegra.ph/' + response['path']
    TELEGRAPH_LINKS[key] = link
    with open(LINKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(TELEGRAPH_LINKS, f, ensure_ascii=False, indent=2)
    return link

def get_chapter_text(book, chapter):
    verses = BIBLE[book][chapter]
    text = f"{book} {chapter} глава:\n" + '\n'.join([f"{i+1}. {v}" for i, v in enumerate(verses)])
    return text, verses

def get_next_chapter(book, chapter):
    chapters = get_all_chapters(book)
    idx = chapters.index(chapter)
    if idx < len(chapters) - 1:
        return chapters[idx + 1]
    return None

def get_prev_chapter(book, chapter):
    chapters = get_all_chapters(book)
    idx = chapters.index(chapter)
    if idx > 0:
        return chapters[idx - 1]
    return None

def get_first_chapter(book):
    return get_all_chapters(book)[0]

def get_last_chapter(book):
    return get_all_chapters(book)[-1]

def filter_books(query):
    query = query.lower()
    return [book for book in get_all_books() if query in book.lower()]

def add_to_history(context, book, chapter):
    if 'history' not in context.user_data:
        context.user_data['history'] = []
    entry = (book, chapter)
    if entry in context.user_data['history']:
        context.user_data['history'].remove(entry)
    context.user_data['history'].insert(0, entry)
    context.user_data['history'] = context.user_data['history'][:20]

def get_history(context):
    return context.user_data.get('history', [])

def get_last_chapter_from_history(context):
    history = get_history(context)
    if history:
        return history[0]
    return None, None

def chapters_keyboard(chapters, row_size=4):
    # Группируем главы по row_size в ряд
    rows = []
    for i in range(0, len(chapters), row_size):
        rows.append([chapter for chapter in chapters[i:i+row_size]])
    return rows

def books_keyboard(books, row_size=4):
    rows = []
    for i in range(0, len(books), row_size):
        rows.append([book for book in books[i:i+row_size]])
    return rows

async def send_long_message(update, text):
    # Делит длинный текст на части по 4096 символов и отправляет их по очереди
    max_len = 4096
    for i in range(0, len(text), max_len):
        await update.message.reply_text(text[i:i+max_len])

# --- Избранные книги и история ---
def add_favorite(context, book):
    if 'favorites' not in context.user_data:
        context.user_data['favorites'] = []
    if book not in context.user_data['favorites']:
        context.user_data['favorites'].append(book)

def remove_favorite(context, book):
    if 'favorites' in context.user_data and book in context.user_data['favorites']:
        context.user_data['favorites'].remove(book)

def is_favorite(context, book):
    return 'favorites' in context.user_data and book in context.user_data['favorites']

def get_favorites(context):
    return context.user_data.get('favorites', [])

def save_subscribers():
    with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(SUBSCRIBERS), f, ensure_ascii=False, indent=2)

def save_notes():
    with open(NOTES_FILE, 'w', encoding='utf-8') as f:
        json.dump(ALL_NOTES, f, ensure_ascii=False, indent=2)

def get_user_notes(user_id):
    return ALL_NOTES.get(str(user_id), {})

def add_user_note(user_id, book, chapter, note):
    user_id = str(user_id)
    if user_id not in ALL_NOTES:
        ALL_NOTES[user_id] = {}
    key = f"{book}|{chapter}"
    ALL_NOTES[user_id][key] = note
    save_notes()

def remove_user_note(user_id, book, chapter):
    user_id = str(user_id)
    key = f"{book}|{chapter}"
    if user_id in ALL_NOTES and key in ALL_NOTES[user_id]:
        del ALL_NOTES[user_id][key]
        save_notes()

def get_user_note(user_id, book, chapter):
    user_id = str(user_id)
    key = f"{book}|{chapter}"
    return ALL_NOTES.get(user_id, {}).get(key)

# --- Хендлеры ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Ветхий Завет", "Новый Завет"]]
    keyboard.append(["⭐ Избранные книги", "📖 Последняя прочитанная"])
    keyboard.append(["🕓 История чтения", "🔍 Поиск книги", "📚 Недавно", "ℹ️ Справка"])
    keyboard.append(["🔔 Подписаться на стих дня", "🔕 Отписаться от рассылки"])
    keyboard.append(["📝 Мои заметки"])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Выберите раздел:", reply_markup=reply_markup
    )
    return CHOOSE_BOOK

async def choose_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "📅 Календарь чтения":
        await calendar_menu(update, context)
        return CHOOSE_BOOK
    if text == "📝 Мои заметки":
        user_id = update.effective_user.id
        notes = get_user_notes(user_id)
        if not notes:
            await update.message.reply_text("У вас нет заметок.")
            return CHOOSE_BOOK
        keyboard = [[f"{k.replace('|', ' ')}"] for k in notes.keys()]
        keyboard.append(["🏠 Главное меню"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Ваши заметки (книга и глава):", reply_markup=reply_markup)
        return CHOOSE_BOOK
    if text == "🏠 Главное меню":
        return await start(update, context)
    if text == "⭐ Избранные книги":
        favs = get_favorites(context)
        if not favs:
            await update.message.reply_text("У вас нет избранных книг.")
            return CHOOSE_BOOK
        keyboard = books_keyboard(favs)
        keyboard.append(["🏠 Главное меню"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Ваши избранные книги:", reply_markup=reply_markup)
        return CHOOSE_BOOK
    if text == "📖 Последняя прочитанная":
        last = get_last_chapter_from_history(context)
        if last and last[0] and last[1]:
            context.user_data['book'] = last[0]
            context.user_data['chapter'] = last[1]
            return await show_chapter(update, context, last[0], last[1])
        else:
            await update.message.reply_text("Нет последней прочитанной главы.")
            return CHOOSE_BOOK
    if text == "🕓 История чтения":
        hist = get_history(context)
        if not hist:
            await update.message.reply_text("История пуста.")
            return CHOOSE_BOOK
        keyboard = [[f"{b} {c}"] for b, c in hist[:10]]
        keyboard.append(["🏠 Главное меню"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Последние прочитанные главы:", reply_markup=reply_markup)
        return CHOOSE_BOOK
    if text == "🔔 Подписаться на стих дня":
        user_id = update.effective_user.id
        SUBSCRIBERS.add(user_id)
        save_subscribers()
        await update.message.reply_text("Вы подписались на ежедневную рассылку стиха дня!")
        return CHOOSE_BOOK
    if text == "🔕 Отписаться от рассылки":
        user_id = update.effective_user.id
        if user_id in SUBSCRIBERS:
            SUBSCRIBERS.remove(user_id)
            save_subscribers()
            await update.message.reply_text("Вы отписались от рассылки.")
        else:
            await update.message.reply_text("Вы не были подписаны.")
        return CHOOSE_BOOK
    # Выбор завета
    if text == "Ветхий Завет":
        context.user_data['testament'] = 'old'
        keyboard = books_keyboard(OLD_TESTAMENT)
        keyboard.append(["🔙 К разделам", "🏠 Главное меню"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Выберите книгу Ветхого Завета:", reply_markup=reply_markup)
        return CHOOSE_BOOK
    if text == "Новый Завет":
        context.user_data['testament'] = 'new'
        keyboard = books_keyboard(NEW_TESTAMENT)
        keyboard.append(["🔙 К разделам", "🏠 Главное меню"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Выберите книгу Нового Завета:", reply_markup=reply_markup)
        return CHOOSE_BOOK
    if text == "🔙 К разделам":
        keyboard = [["Ветхий Завет", "Новый Завет"]]
        keyboard.append(["🔍 Поиск книги", "📚 Недавно", "ℹ️ Справка"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Выберите раздел:", reply_markup=reply_markup)
        return CHOOSE_BOOK
    # Быстрый переход: "Бытие 3" или "Псалтирь 22"
    match = re.match(r'^([А-Яа-яЁё\s]+)\s+(\d+)$', text)
    if match:
        book = match.group(1).strip()
        chapter = match.group(2).strip()
        if book in BIBLE and chapter in BIBLE[book]:
            context.user_data['book'] = book
            context.user_data['chapter'] = chapter
            return await show_chapter(update, context, book, chapter)
        else:
            await update.message.reply_text("Такой книги или главы нет. Попробуйте ещё раз.")
            return CHOOSE_BOOK
    if text == "🔍 Поиск книги":
        await update.message.reply_text("Введите часть названия книги:")
        return BOOK_SEARCH
    if text == "📚 Недавно":
        history = get_history(context)
        if not history:
            await update.message.reply_text("История пуста.")
            return CHOOSE_BOOK
        keyboard = [[f"{b} {c}"] for b, c in history]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Недавно открытые главы:", reply_markup=reply_markup)
        return CHOOSE_BOOK
    if text == "ℹ️ Справка":
        await update.message.reply_text(
            "\u2139\ufe0f <b>Справка по боту</b>\n\n"
            "\u2022 Выберите книгу и главу для чтения.\n"
            "\u2022 Можно быстро перейти к главе, написав, например, 'Бытие 3'.\n"
            "\u2022 Используйте поиск для быстрого выбора книги.\n"
            "\u2022 В меню главы доступны кнопки навигации, содержание, возврат к книге, поделиться главой и оформление как картинка.\n"
            "\u2022 Кнопка 'Недавно' — быстрый доступ к последним главам.\n",
            parse_mode='HTML')
        return CHOOSE_BOOK
    # Обычный выбор книги
    if text in BIBLE:
        chapters = get_all_chapters(text)
        fav_btn = "⭐ Убрать из избранного" if is_favorite(context, text) else "⭐ Добавить в избранное"
        keyboard = chapters_keyboard(chapters)
        keyboard.append([fav_btn, "🏠 Главное меню"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        context.user_data['book'] = text
        await update.message.reply_text(f"Вы выбрали книгу {text}. Теперь выберите главу:", reply_markup=reply_markup)
        return CHOOSE_CHAPTER
    if text == "⭐ Добавить в избранное":
        book = context.user_data.get('book')
        add_favorite(context, book)
        await update.message.reply_text(f"Книга {book} добавлена в избранное.")
        return await choose_book(update, context)
    if text == "⭐ Убрать из избранного":
        book = context.user_data.get('book')
        remove_favorite(context, book)
        await update.message.reply_text(f"Книга {book} убрана из избранного.")
        return await choose_book(update, context)
    # Фильтрация по названию книги
    filtered = filter_books(text)
    if filtered:
        keyboard = [[book] for book in filtered[:10]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Возможно, вы имели в виду:", reply_markup=reply_markup)
        return CHOOSE_BOOK
    await update.message.reply_text("Пожалуйста, выберите книгу из списка, воспользуйтесь поиском или введите, например, 'Бытие 3'.")
    return CHOOSE_BOOK

async def book_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    filtered = filter_books(query)
    if filtered:
        keyboard = [[book] for book in filtered[:10]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Выберите книгу:", reply_markup=reply_markup)
        return CHOOSE_BOOK
    else:
        await update.message.reply_text("Ничего не найдено. Попробуйте ещё раз.")
        return BOOK_SEARCH

async def choose_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapter = update.message.text.strip()
    if chapter == "🏠 Главное меню":
        return await start(update, context)
    book = context.user_data.get('book')
    if book and chapter in BIBLE[book]:
        context.user_data['chapter'] = chapter
        return await show_chapter(update, context, book, chapter)
    else:
        await update.message.reply_text("Пожалуйста, выберите главу из списка.")
        return CHOOSE_CHAPTER

async def show_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE, book, chapter):
    text, verses = get_chapter_text(book, chapter)
    link = get_telegraph_link(book, chapter, verses)
    add_to_history(context, book, chapter)
    context.user_data['current_chapter'] = (book, chapter)
    chapters = get_all_chapters(book)
    idx = chapters.index(chapter)
    nav_row = []
    if idx > 0:
        nav_row.append(KeyboardButton("⬅️ Предыдущая глава"))
    if idx < len(chapters) - 1:
        nav_row.append(KeyboardButton("Следующая глава ➡️"))
    nav2_row = [KeyboardButton("⏮ В начало книги"), KeyboardButton("⏭ В конец книги")]
    action_row = [KeyboardButton("📖 Содержание книги"), KeyboardButton("🔄 Вернуться к текущей главе")]
    share_row = [KeyboardButton("🔗 Поделиться главой"), KeyboardButton("🔙 К выбору книги")]
    note_row = [KeyboardButton("✏️ Добавить заметку"), KeyboardButton("🏠 Главное меню")]
    reply_markup = ReplyKeyboardMarkup(
        [nav_row, nav2_row, action_row, share_row, note_row], resize_keyboard=True
    )
    await send_long_message(update, text)
    await update.message.reply_text(f"Читать в Telegraph: {link}", reply_markup=reply_markup)
    note = get_user_note(update.effective_user.id, book, chapter)
    if note:
        await update.message.reply_text(f"Ваша заметка к этой главе:\n{note}")
    return CHAPTER_MENU

async def chapter_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🏠 Главное меню":
        return await start(update, context)
    book = context.user_data.get('book')
    chapter = context.user_data.get('chapter')
    chapters = get_all_chapters(book)
    idx = chapters.index(chapter)
    if text == "⬅️ Предыдущая глава":
        prev_ch = get_prev_chapter(book, chapter)
        if prev_ch:
            context.user_data['chapter'] = prev_ch
            return await show_chapter(update, context, book, prev_ch)
    elif text == "Следующая глава ➡️":
        next_ch = get_next_chapter(book, chapter)
        if next_ch:
            context.user_data['chapter'] = next_ch
            return await show_chapter(update, context, book, next_ch)
    elif text == "⏮ В начало книги":
        first_ch = get_first_chapter(book)
        context.user_data['chapter'] = first_ch
        return await show_chapter(update, context, book, first_ch)
    elif text == "⏭ В конец книги":
        last_ch = get_last_chapter(book)
        context.user_data['chapter'] = last_ch
        return await show_chapter(update, context, book, last_ch)
    elif text == "📖 Содержание книги":
        chapters = get_all_chapters(book)
        keyboard = chapters_keyboard(chapters)
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(f"Содержание книги {book}:", reply_markup=reply_markup)
        return CHOOSE_CHAPTER
    elif text == "🔙 К выбору книги":
        books = get_all_books()
        keyboard = [[book] for book in books[:10]]
        keyboard.append(["🔍 Поиск книги", "📚 Недавно", "ℹ️ Справка"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Выберите книгу Библии, введите, например, 'Бытие 3', или воспользуйтесь поиском:", reply_markup=reply_markup)
        return CHOOSE_BOOK
    elif text == "🔄 Вернуться к текущей главе":
        last_book, last_chapter = get_last_chapter_from_history(context)
        if last_book and last_chapter:
            context.user_data['book'] = last_book
            context.user_data['chapter'] = last_chapter
            return await show_chapter(update, context, last_book, last_chapter)
        else:
            await update.message.reply_text("Нет текущей главы.")
            return CHAPTER_MENU
    elif text == "🔗 Поделиться главой":
        link = get_telegraph_link(book, chapter, BIBLE[book][chapter])
        await update.message.reply_text(f"Ссылка для пересылки: {link}")
        return CHAPTER_MENU
    elif text == "🖼 Оформить как картинку":
        await update.message.reply_text("Функция временно отключена. Если нужно вернуть — напишите!")
        return CHAPTER_MENU
    elif text == "✏️ Добавить заметку":
        await update.message.reply_text("Введите текст заметки (или отправьте 'отмена' для отмены):")
        return ADD_NOTE
    else:
        await update.message.reply_text("Пожалуйста, выберите действие из меню.")
        return CHAPTER_MENU

async def add_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note_text = update.message.text.strip()
    if note_text.lower() == "отмена":
        await update.message.reply_text("Добавление заметки отменено.")
        return CHAPTER_MENU
    book = context.user_data.get('book')
    chapter = context.user_data.get('chapter')
    user_id = update.effective_user.id
    add_user_note(user_id, book, chapter, note_text)
    await update.message.reply_text(f"Заметка для {book} {chapter} сохранена!")
    return CHAPTER_MENU

async def send_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Для теста: ручная рассылка стиха дня всем подписчикам
    # Стих дня выбирается случайно
    import random
    book = random.choice(list(BIBLE.keys()))
    chapter = random.choice(list(BIBLE[book].keys()))
    verses = BIBLE[book][chapter]
    verse_num = random.randint(0, len(verses)-1)
    verse = verses[verse_num]
    text = f"Стих дня:\n{book} {chapter}:{verse_num+1} — {verse}"
    for user_id in SUBSCRIBERS:
        try:
            await context.bot.send_message(chat_id=user_id, text=text)
        except Exception:
            pass
    await update.message.reply_text("Рассылка выполнена.")

def save_channel_id(channel_id):
    with open(CHANNEL_FILE, 'w', encoding='utf-8') as f:
        json.dump({'channel_id': channel_id}, f, ensure_ascii=False, indent=2)

async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Команда должна быть отправлена из канала или группы, где бот — админ
    chat = update.effective_chat
    if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
        save_channel_id(chat.id)
        global CHANNEL_ID
        CHANNEL_ID = chat.id
        await update.message.reply_text(f"Канал/группа для рассылки установлен: {chat.title or chat.id}")
    else:
        await update.message.reply_text("Эту команду нужно отправить из канала или группы, где бот — админ!")

async def send_daily_to_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Отправляет стих дня в канал/группу
    if not CHANNEL_ID:
        await update.message.reply_text("Канал для рассылки не установлен. Используйте /set_channel в нужном чате.")
        return
    import random
    book = random.choice(list(BIBLE.keys()))
    chapter = random.choice(list(BIBLE[book].keys()))
    verses = BIBLE[book][chapter]
    verse_num = random.randint(0, len(verses)-1)
    verse = verses[verse_num]
    text = f"Стих дня:\n{book} {chapter}:{verse_num+1} — {verse}"
    try:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=text)
        await update.message.reply_text("Стих дня отправлен в канал/группу!")
    except Exception as e:
        await update.message.reply_text(f"Ошибка отправки: {e}")

def save_group_reading():
    with open(GROUP_READING_FILE, 'w', encoding='utf-8') as f:
        json.dump(GROUP_READING, f, ensure_ascii=False, indent=2)

async def group_reading_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await update.message.reply_text("Эта команда работает только в группах!")
        return
    GROUP_READING[str(chat.id)] = {
        'book': 'Бытие',
        'chapter': '1',
        'read_users': [],
        'votes': {}
    }
    save_group_reading()
    await update.message.reply_text("Совместное чтение начато! Первая глава: Бытие 1. Используйте /group_reading_status для просмотра статуса.")

async def group_reading_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if str(chat.id) not in GROUP_READING:
        await update.message.reply_text("Совместное чтение не начато. Используйте /group_reading_start.")
        return
    data = GROUP_READING[str(chat.id)]
    book = data['book']
    chapter = data['chapter']
    read_users = data.get('read_users', [])
    votes = data.get('votes', {})
    text = f"Текущая глава: {book} {chapter}\nПрочитали: {len(read_users)} участников\nГолоса за следующую главу: {votes}"
    await update.message.reply_text(text)

async def group_vote_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if str(chat.id) not in GROUP_READING:
        await update.message.reply_text("Совместное чтение не начато. Используйте /group_reading_start.")
        return
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text("Используйте: /group_vote_next <Книга> <Глава>")
        return
    book = args[0]
    chapter = args[1]
    key = f"{book} {chapter}"
    votes = GROUP_READING[str(chat.id)].setdefault('votes', {})
    votes[key] = votes.get(key, 0) + 1
    save_group_reading()
    await update.message.reply_text(f"Голос за {book} {chapter} учтён!")

def main():
    import os
    TOKEN = os.getenv('BOT_TOKEN', '7771236927:AAGvTkMWju2ATHPN21n_r6pTOBzPfGuHdOw')
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), MessageHandler(filters.TEXT & ~filters.COMMAND, choose_book)],
        states={
            CHOOSE_BOOK: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_book)],
            BOOK_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, book_search)],
            CHOOSE_CHAPTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_chapter)],
            CHAPTER_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, chapter_menu)],
            ADD_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_note)],
        },
        fallbacks=[CommandHandler('start', start)],
    )
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler('send_daily', send_daily))
    app.add_handler(CommandHandler('set_channel', set_channel))
    app.add_handler(CommandHandler('send_daily_to_channel', send_daily_to_channel))
    app.add_handler(CommandHandler('group_reading_start', group_reading_start))
    app.add_handler(CommandHandler('group_reading_status', group_reading_status))
    app.add_handler(CommandHandler('group_vote_next', group_vote_next))
    print('Бот запущен!')
    app.run_polling()

if __name__ == '__main__':
    main() 