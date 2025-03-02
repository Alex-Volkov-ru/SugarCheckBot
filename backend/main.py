import os
import logging
import asyncio

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta

from app.keyboards import main as kb
from app.commands import set_commands

# Загрузка переменных окружения
load_dotenv()
# Константы для настройки спама
REMINDER_DURATION = 30  # Длительность спама в секундах
REMINDER_INTERVAL = 1  # Интервал между сообщениями в секундах

# Инициализация бота и диспетчера
bot = Bot(token=os.getenv('TELEGRAM_TOKEN'))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Инициализация планировщика
scheduler = AsyncIOScheduler()

# Глобальный словарь для хранения флагов спама
spam_flags = {}


# Состояния
class UserStates(StatesGroup):
    """Класс для хранения состояний пользователя."""
    waiting_for_meal_time = State()  # Ожидание времени приема пищи
    waiting_for_reminder_minutes = State()  # Ожидание времени напоминания


# Команда /start
@dp.message(Command('start'))
async def cmd_start(message: types.Message, state: FSMContext):
    """Обрабатывает команду /start и запрашивает время приема пищи."""
    logging.info(f"Пользователь {message.from_user.id} начал работу с ботом.")
    await message.answer(
        "Привет! 👋\n"
        "Я — твой помощник, чтобы не забыть сделать забор крови после еды.\n\n"
        "Для начала, напиши, во сколько ты поел (в формате HH:MM):",
        reply_markup=kb,
    )
    await state.set_state(UserStates.waiting_for_meal_time)


# Обработка времени приема пищи
@dp.message(UserStates.waiting_for_meal_time)
async def process_meal_time(message: types.Message, state: FSMContext):
    """Обрабатывает введенное время приема пищи."""
    meal_time = message.text
    logging.info(
        f"Пользователь {message.from_user.id} ввел время: {meal_time}.")
    try:
        # Проверка формата времени
        hours, minutes = map(int, meal_time.split(':'))
        if 0 <= hours < 24 and 0 <= minutes < 60:
            await state.update_data(meal_time=meal_time)
            await message.answer(
                "Отлично! 🕒\n"
                "Теперь укажи, через сколько минут тебе напомнить "
                "о заборе крови.\n\n"
                "Напиши число минут (например, 30 или 120):"
            )
            await state.set_state(UserStates.waiting_for_reminder_minutes)
        else:
            logging.warning(f"Некорректное время: {meal_time}.")
            await message.answer(
                "❌ Неверный формат времени.\n"
                "Пожалуйста, введи время в формате HH:MM (например, 14:30)."
            )
    except ValueError:
        logging.warning(f"Ошибка при обработке времени: {meal_time}.")
        await message.answer(
            "❌ Неверный формат времени.\n"
            "Пожалуйста, введи время в формате HH:MM (например, 14:30)."
        )


# Обработка времени напоминания в минутах
@dp.message(UserStates.waiting_for_reminder_minutes)
async def process_reminder_minutes(message: types.Message, state: FSMContext):
    """Обрабатывает введенное количество минут для напоминания."""
    try:
        reminder_minutes = int(message.text)
        if reminder_minutes < 0:
            logging.warning(
                f"Некорректное количество минут: {reminder_minutes}.")
            await message.answer(
                "❌ Неверное значение.\n"
                "Пожалуйста, введи положительное число минут."
            )
            return

        user_data = await state.get_data()
        meal_time = user_data['meal_time']
        hours, minutes = map(int, meal_time.split(':'))

        # Рассчитываем время напоминания
        meal_datetime = datetime.now().replace(
            hour=hours, minute=minutes, second=0, microsecond=0)
        reminder_datetime = meal_datetime + timedelta(minutes=reminder_minutes)

        logging.info(
            f"Пользователь {message.from_user.id} установил напоминание "
            f"на {reminder_datetime.strftime('%H:%M')}."
        )

        await message.answer(
            "✅ Отлично! Я запомнил.\n\n"
            f"Я напомню тебе о заборе крови в "
            f"{reminder_datetime.strftime('%H:%M')}.\n\n"
            "Если что-то изменится, просто нажми /start."
        )

        # Добавляем задачу в планировщик
        spam_flags[message.chat.id] = True  # Устанавливаем флаг спама
        scheduler.add_job(
            send_reminder,
            'date',
            run_date=reminder_datetime,
            args=(message.chat.id,)
        )

        await state.clear()  # Очистка состояния
    except ValueError:
        logging.warning(f"Ошибка при обработке минут: {message.text}.")
        await message.answer(
            "❌ Неверное значение.\n"
            "Пожалуйста, введи число минут (например, 30 или 120)."
        )


async def send_reminder(chat_id: int):
    """Отправляет напоминание пользователю о заборе крови."""
    logging.info(f"Отправка напоминания пользователю {chat_id}.")

    # Время начала спама
    start_time = asyncio.get_event_loop().time()

    # Продолжаем отправлять сообщения в течение REMINDER_DURATION секунд
    while asyncio.get_event_loop().time() - start_time < REMINDER_DURATION:
        # Проверяем, не был ли остановлен спам
        if not spam_flags.get(chat_id, True):
            logging.info(f"Спам остановлен для пользователя {chat_id}.")
            break

        try:
            await bot.send_message(
                chat_id,
                "⏰ Время сделать забор крови!\n\n"
                "Не забудь выполнить забор крови, как мы договорились. 😊"
            )
        except Exception as e:
            logging.error(f"Ошибка при отправке сообщения: {e}")
        await asyncio.sleep(REMINDER_INTERVAL)  # Интервал между сообщениями

    logging.info(f"Завершение отправки напоминаний пользователю {chat_id}.")
    spam_flags.pop(chat_id, None)  # Удаляем флаг после завершения


# Обработка кнопки "Старт"
@dp.message(lambda message: message.text == 'Старт')
async def handle_start_button(message: types.Message, state: FSMContext):
    """Обрабатывает нажатие кнопки 'Старт'."""
    await cmd_start(message, state)


# Обработка кнопки "Стоп"
@dp.message(lambda message: message.text == 'Стоп')
async def handle_stop_button(message: types.Message, state: FSMContext):
    """Обрабатывает нажатие кнопки 'Стоп'."""
    spam_flags[message.chat.id] = False  # Останавливаем спам
    await state.clear()  # Сбрасываем состояние
    await message.answer("Спам остановлен. Нажми /start, чтобы начать заново.")


# Запуск бота
async def main():
    """Запускает бота и планировщик."""
    logging.info("Запуск бота и планировщика.")
    scheduler.start()
    await set_commands(bot)
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler("bot.log", encoding="utf-8")
            ]
        )
        logging.info("Бот запущен.")
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот отключен.")
    except Exception as e:
        logging.error(f"Неизвестная ошибка: {str(e)}")
