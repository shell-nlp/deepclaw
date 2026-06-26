FROM pgvector/pgvector:pg16-bookworm

ARG PG_MAJOR=16
ARG PG_SEARCH_VERSION=0.24.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && arch="$(dpkg --print-architecture)" \
    && curl -fsSL \
        "https://github.com/paradedb/paradedb/releases/download/v${PG_SEARCH_VERSION}/postgresql-${PG_MAJOR}-pg-search_${PG_SEARCH_VERSION}-1PARADEDB-bookworm_${arch}.deb" \
        -o /tmp/pg_search.deb \
    && apt-get install -y /tmp/pg_search.deb \
    && rm -f /tmp/pg_search.deb \
    && rm -rf /var/lib/apt/lists/*

# PostgreSQL 16 需要在启动前预加载 pg_search
RUN echo "shared_preload_libraries = 'pg_search'" >> /usr/share/postgresql/postgresql.conf.sample
