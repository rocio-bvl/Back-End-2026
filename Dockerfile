FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y pkg-config default-libmysqlclient-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . /app/

# SEGURIDAD: Crear un usuario de sistema sin privilegios para ejecutar la app
RUN adduser --disabled-password --no-create-home django_user
RUN chown -R django_user:django_user /app
USER django_user

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "config.wsgi:application"]
