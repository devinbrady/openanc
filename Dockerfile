
FROM python:3.10.6-slim-buster
ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY . .

