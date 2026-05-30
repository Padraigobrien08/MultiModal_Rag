FROM python:3.11-slim

# ffmpeg for frame extraction, yt-dlp for audio download
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir -e .

COPY stepwise/ ./stepwise/

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "stepwise.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
