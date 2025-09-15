FROM python:3.8-slim

WORKDIR /app

RUN apt-get update && apt-get install -y tzdata

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY src/ /app/src/

CMD ["python", "-u", "/app/main.py"]