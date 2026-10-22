# Immagine del solo backend (SL-00b, ADR-0005). Multi-stage, utente non root, nessun segreto:
# la configurazione arriva dalle variabili d'ambiente a runtime. Compatibile con filesystem
# in sola lettura (nessuna scrittura a runtime: niente bytecode, niente file temporanei).
# Basi fissate per digest (SR-076); aggiornare insieme a `uv.lock` e ai rilasci di sicurezza.

FROM ghcr.io/astral-sh/uv:0.13.4@sha256:9f130421e930bfbdc563c00740466603f8723158e90297d07957c2294640262b AS uv

FROM python:3.14-slim@sha256:fbecd461fc72d21b2143c6eaba25143738079154a6d0ea3da3aec724f50eed4a AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_PROGRESS=1
WORKDIR /app
# Strato delle dipendenze: cambia solo con pyproject.toml e uv.lock.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-editable
# Poi il progetto, installato come pacchetto (non editable) nello stesso ambiente.
COPY backend/src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.14-slim@sha256:fbecd461fc72d21b2143c6eaba25143738079154a6d0ea3da3aec724f50eed4a
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random
# pip non serve a runtime: toglierlo elimina anche le sue dipendenze incluse (urllib3, ...).
RUN rm -rf /usr/local/lib/python3.14/site-packages/pip* /usr/local/bin/pip* \
    && groupadd --system --gid 10001 menu \
    && useradd --system --uid 10001 --gid menu --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin menu
COPY --from=builder --chown=root:root /app/.venv /app/.venv
USER 10001:10001
WORKDIR /app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
CMD ["python", "-m", "menu", "serve", "--host", "0.0.0.0", "--port", "8000"]
