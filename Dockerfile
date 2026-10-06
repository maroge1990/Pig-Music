FROM node:24-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20 AS frontend
WORKDIR /build/client
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client/ ./
RUN npm run build

FROM slskd/slskd@sha256:ecd4026d4f8fb504e2cc55323efa2c1f5b56d20d3686b018249cc36b48ea17a6 AS soulseek

FROM python:3.14-slim@sha256:3353bb7e9ae99c7cce6cad2b2f2b174e8f22813ac43e3b13e7a742627d2b01d8
WORKDIR /app
ARG VCS_REF=unknown
ARG VERSION=dev
LABEL org.opencontainers.image.source="https://github.com/maroge1990/Pig-Music" \
      org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.title="Pig Music"
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libicu76 libssl3t64 libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=soulseek /slskd /opt/slskd
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY server/ ./server/
COPY scripts/prune_artwork.py scripts/verify_state_migration.py scripts/benchmark_cover_store.py scripts/benchmark_delivery.py scripts/generate_brand_tokens.py ./scripts/
COPY docs/pig-family-brand-tokens.json ./docs/
COPY client/src/tokens.css ./client/src/
COPY swift/PigKit/Sources/PigBrand/Tokens.swift ./swift/PigKit/Sources/PigBrand/
COPY --from=frontend /build/client/dist ./client/dist
ENV PIG_MUSIC_DATA=/data
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health')"
CMD ["python", "-m", "server.runtime"]
