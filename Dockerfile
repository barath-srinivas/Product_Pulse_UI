FROM python:3.12-slim-bookworm

WORKDIR /app

# Native build deps for hdbscan / umap-learn
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy full source before install — Nixpacks runs pip install before COPY,
# which leaves pulse-api without the pulse package (ModuleNotFoundError).
COPY . .

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

CMD ["pulse-api"]
