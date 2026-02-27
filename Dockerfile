# ── Build Stage ────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# Sem bytecode em disco; logs fluem diretamente para o container runtime.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ── Dependências ────────────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Código ─────────────────────────────────────────────────────────────────────
COPY . .

# ── Usuário não-root (princípio do menor privilégio) ──────────────────────────
RUN groupadd --gid 1001 appgroup \
 && useradd  --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser \
 && chown -R appuser:appgroup /app

USER appuser

# Entrypoint padrão; sobrescrito no docker-compose por serviço.
CMD ["python", "init_core.py"]
