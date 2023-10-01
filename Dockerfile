FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# collectstatic only needs importable settings, not a real key.
RUN SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput \
    && useradd --create-home --uid 10001 app

USER app
EXPOSE 8000

CMD ["gunicorn", "bnbu_backend_api.wsgi", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-"]
