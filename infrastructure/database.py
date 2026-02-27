"""
infrastructure/database.py
==========================
Motor de banco de dados e gerenciamento de sessão.

Uso:
    from infrastructure.database import get_session, create_db_and_tables

    # Como context manager direto:
    with get_session() as session:
        session.add(obj)
        session.commit()

    # Como gerador para injeção de dependência (FastAPI / futura API):
    def endpoint(session: Session = Depends(get_session)): ...
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from infrastructure.settings import settings

# ── Engine ─────────────────────────────────────────────────────────────────────
engine = create_engine(
    settings.database_url,
    echo=not settings.is_production,   # SQL visível em dev, silencioso em prod
    pool_pre_ping=True,                # detecta conexões zumbis antes de usar
    pool_size=5,
    max_overflow=10,
    connect_args={
        "options": "-c timezone=UTC",  # força UTC no nível de sessão do Postgres
    },
)


# ── Session factory ────────────────────────────────────────────────────────────
@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context manager que entrega uma Session isolada com commit/rollback automático.
    Padrão Unit of Work: o commit só ocorre se o bloco `with` não lançar exceção.
    """
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


# ── Schema ─────────────────────────────────────────────────────────────────────
def create_db_and_tables() -> None:
    """
    Cria todas as tabelas registradas em SQLModel.metadata que ainda não existem.
    Idempotente: seguro chamar múltiplas vezes (usa CREATE TABLE IF NOT EXISTS).
    Para ambientes de produção, prefira Alembic para migrações controladas.
    """
    import domain.models  # noqa: F401 – garante registro das tabelas no metadata

    SQLModel.metadata.create_all(engine)
    print(f"[OK] Schema aplicado em: {settings.postgres_db}@{settings.postgres_host}")


if __name__ == "__main__":
    create_db_and_tables()
