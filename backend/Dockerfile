# Stage 1: Устанавливаем зависимости
FROM python:3.11-slim

WORKDIR /app

# Устанавливаем нужный часовой пояс
RUN ln -sf /usr/share/zoneinfo/Europe/Moscow /etc/localtime && echo "Europe/Moscow" > /etc/timezone

# Копируем только requirements.txt и устанавливаем зависимости
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь исходный код
COPY . .

# Команда для запуска приложения
CMD ["python", "main.py"]
