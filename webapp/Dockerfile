FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# collectstatic needs a SECRET_KEY to boot the app, but not a real one at build time.
RUN DJANGO_SECRET_KEY=build-time-placeholder python manage.py collectstatic --noinput

EXPOSE 8000

# Migrations run once per deploy via fly.toml's release_command, not here: with several machines
# booting at once they would race each other.
CMD ["gunicorn", "openanc_web.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
