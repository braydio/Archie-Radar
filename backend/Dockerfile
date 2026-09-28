FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir . \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
