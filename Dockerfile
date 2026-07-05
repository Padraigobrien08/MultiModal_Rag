FROM python:3.11-slim

# ffmpeg for frame extraction and yt-dlp muxing
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the package with its runtime dependencies only (no dev extras).
# The build backend needs the source tree present to resolve the package,
# so copy the metadata and source before installing. README.md and LICENSE are
# referenced by pyproject.toml metadata, so hatchling needs them at build time.
# constraints.txt pins the resolved transitive tree for reproducible builds
# (regenerate with `make lock`); ranges stay in pyproject.toml.
COPY pyproject.toml constraints.txt README.md LICENSE ./
COPY stepwise/ ./stepwise/
RUN pip install --no-cache-dir -c constraints.txt .

# Run as an unprivileged user. Own /app (incl. the data dir) so the app can
# write the SQLite db, Chroma index, and extracted frames.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

# PYTHONPATH keeps ./stepwise importable so the compose source mount (dev)
# takes precedence over the baked copy without needing an editable install.
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "stepwise.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
