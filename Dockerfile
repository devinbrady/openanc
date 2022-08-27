
FROM python:3.10.6-slim-buster
ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update
RUN apt-get -y install gcc

COPY requirements.txt requirements.txt
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . .

