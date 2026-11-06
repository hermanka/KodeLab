FROM python:3.12.10-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home app
COPY app ./app
COPY runner ./runner
COPY plugin ./plugin
RUN mkdir -p /app/plugin/installed && chown app:app /app/plugin/installed
COPY migrations ./migrations
COPY alembic.ini .
COPY scripts ./scripts
COPY tests ./tests
COPY web ./web
USER app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
