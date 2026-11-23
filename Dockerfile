FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SALESAGENT_DATA=/data

# Fonts for Marketing Studio posters (the video encoder comes with the imageio-ffmpeg package)
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Railway sets $PORT. Data (database, settings, outbox) lives on the volume mounted at /data.
CMD python -m salesagent.cli serve --port ${PORT:-8000}
