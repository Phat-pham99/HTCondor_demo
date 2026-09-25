FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY autoscaler/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY autoscaler/condor_docker_autoscaler.py /app/condor_docker_autoscaler.py
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin autoscaler
USER 1000
ENTRYPOINT ["python", "/app/condor_docker_autoscaler.py"]
