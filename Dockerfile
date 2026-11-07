FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python scripts/build_translations.py \
    && SECRET_KEY=build-only-key-not-used-at-runtime DEBUG=0 DB_ENGINE=sqlite python manage.py collectstatic --noinput \
    && useradd --uid 10001 --create-home canela \
    && mkdir -p /app/media /app/data \
    && chown -R canela:canela /app
USER canela
EXPOSE 8000
CMD ["python", "scripts/serve.py"]
