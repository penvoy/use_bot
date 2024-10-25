import asyncio
import aiosqlite
from telebot import types
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message
from telebot.util import quick_markup

bot = AsyncTeleBot('BOT_KEY')

user_states = {}


async def db_setup():
    # Создаем базу данных и необходимые таблицы
    async with aiosqlite.connect('sqlite.db') as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                telegram_id INTEGER UNIQUE NOT NULL
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                subject TEXT NOT NULL,
                score INTEGER NOT NULL,
                FOREIGN KEY (student_id) REFERENCES students (id)
            )
        ''')
        await db.commit()


# команда /start
@bot.message_handler(commands=['start'])
async def start_handler(message: Message):
    markup = quick_markup({
        'Зарегистрироваться': {'callback_data': 'register'},
        'Просмотреть баллы': {'callback_data': 'view_scores'}
    }, row_width=2)
    await bot.send_message(message.chat.id,
                           "Привет! Выбери нужное действие", reply_markup=markup)


# команда register
@bot.callback_query_handler(func=lambda call: call.data == 'register')
async def register_handler(call: types.CallbackQuery):
    # подключаемся к бд и проверяем зарегистрирован ли уже юзер
    async with aiosqlite.connect('sqlite.db') as db:
        cursor = await db.execute("SELECT id FROM students WHERE telegram_id = ?", (call.from_user.id,))

        student = await cursor.fetchone()

        if student:
            text = "Вы уже зарегистрированы!"
        else:
            # Установим состояние для дальнейшей регистрации
            user_states[call.from_user.id] = 'waiting_for_first_name'
            text = "Введите ваше имя:"

    await bot.send_message(call.message.chat.id, text)
    await bot.answer_callback_query(call.id)


# обработчик имени
@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == 'waiting_for_first_name')
async def process_first_name(message: Message):
    # получаем и сохраняем имя
    first_name = message.text
    # обновляем состояние и передем имя
    user_states[message.from_user.id] = ('waiting_for_last_name', first_name)
    await bot.send_message(message.chat.id, "Введите вашу фамилию:")


# обработчик фамилии
@bot.message_handler(func=lambda message: user_states.get(message.from_user.id)[0] == 'waiting_for_last_name')
async def process_last_name(message: Message):
    # получаем и сохраняем фамилию
    last_name = message.text

    # Получаем имя из состояния
    first_name = user_states.get(message.from_user.id)[1]

    # убираем из словаря данные пользователя
    user_states.pop(message.from_user.id)

    # подключаемся к бд
    async with aiosqlite.connect('sqlite.db') as db:

        # заносим запись в бд
        await db.execute("INSERT INTO students (first_name, last_name, telegram_id) VALUES (?, ?, ?)",
                         (first_name, last_name, message.from_user.id))

        # комиттим изменения
        await db.commit()

    # кнопки
    markup = quick_markup({
        'Просмотреть баллы': {'callback_data': 'view_scores'}
    }, row_width=2)

    await bot.send_message(message.chat.id, text=f"Спасибо, {first_name} {last_name}, вы зарегистрированы!", reply_markup=markup)


# обработчик просмотра баллов
@bot.callback_query_handler(func=lambda call: call.data == 'view_scores')
async def view_scores_handler(call: types.CallbackQuery):
    # сохраняем id юзера
    telegram_id = call.from_user.id

    # подключаемся к бд
    async with aiosqlite.connect('sqlite.db') as db:

        # проверяем есть ли такой юзер в нашей бд
        cursor = await db.execute("SELECT id FROM students WHERE telegram_id = ?", (telegram_id,))
        student = await cursor.fetchone()

        if student:
            # берём айди пользователя из бд
            student_id = student[0]

            # запрашиваем данные о баллах пользователя
            cursor = await db.execute("SELECT subject, score FROM scores WHERE student_id = ?", (student_id,))
            scores = await cursor.fetchall()

            # кнопка
            markup = quick_markup({
                'Внести баллы за ЕГЭ': {'callback_data': 'enter_scores'}
            }, row_width=3)

            # если есть данные о баллах, то выводим их
            if scores:
                text = "Ваши баллы:\n" + \
                    "\n".join(f"{subject}: {score}" for subject,
                              score in scores)
            # иначе информируем об их отсутствии
            else:
                text = "У вас нет сохраненных баллов."

            await bot.send_message(call.message.chat.id, text, reply_markup=markup)
        else:
            await bot.send_message(call.message.chat.id, "Сначала зарегистрируйтесь!")

    await bot.answer_callback_query(call.id)


# обработчик ввода баллов
@bot.callback_query_handler(func=lambda call: call.data == 'enter_scores')
async def enter_scores_handler(call: types.CallbackQuery):
    # бновляем состояние
    user_states[call.from_user.id] = 'waiting_for_subject'
    await bot.send_message(call.message.chat.id, "Введите предмет")
    await bot.answer_callback_query(call.id)


# обработчик получения предмета
@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == 'waiting_for_subject')
async def process_subject(message: Message):
    # получаем предмет
    subject = message.text

    # Обновляем состояние
    user_states[message.from_user.id] = ('waiting_for_scores', subject)
    await bot.send_message(message.chat.id, "Введите баллы")


# обработчик баллов
@bot.message_handler(func=lambda message: user_states.get(message.from_user.id)[0] == 'waiting_for_scores')
async def process_scores(message: Message):
    # получаем баллы
    scores = message.text

    # получаем предмет из стейта
    subject = user_states.get(message.from_user.id)[1]

    # очищаем
    user_states.pop(message.from_user.id)

    # подключение к бд
    async with aiosqlite.connect('sqlite.db') as db:
        # запрос на существование зарегистрированного юзера
        cursor = await db.execute("SELECT id FROM students WHERE telegram_id = ?", (message.from_user.id,))
        student = await cursor.fetchone()

        if student:
            # если нашли, то берём его id
            student_id = student[0]

            # записываем данные о баллах
            await db.execute("INSERT INTO scores (student_id, subject, score) VALUES (?, ?, ?)",
                             (student_id, subject, scores))
            # комиттим изменения
            await db.commit()

            # выводим кнопку и текст об успехе
            markup = {'Просмотреть баллы': {'callback_data': 'view_scores'}}
            text = "Ваш балл успешно сохранен!"
        else:
            # если не нашли юзера, то говорим об этом и предлагаем кнопку регистрации
            markup = {'Зарегистрироваться': {'callback_data': 'register'}}
            text = "Сначала зарегистрируйтесь!"

        await bot.send_message(message.chat.id, text=text, reply_markup=quick_markup(markup, row_width=2))


async def main():
    # настраиваем бд
    await db_setup()
    # запуск бота
    await bot.polling()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
