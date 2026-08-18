FROM python:3.12-slim

WORKDIR /tests

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel
RUN python -m pip install --no-cache-dir --retries 10 --timeout 60 -r requirements.txt

COPY . .

CMD ["pytest", "-q"]
