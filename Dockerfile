FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .
COPY config.yaml .

RUN mkdir -p /app/output

ENTRYPOINT ["python", "main.py"]
