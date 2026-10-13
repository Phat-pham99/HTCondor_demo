FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONDOR_CONFIG=/app/condor_config
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY condor_config /app/condor_config
COPY app /app/app
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin dashboard
USER 1000
EXPOSE 7000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7000"]
