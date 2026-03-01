#!/usr/bin/env python3
"""
scripts/seed_db.py
==================
Script de seeding inicial do Life_OS.

O que faz
---------
1. Dropa a tabela ``work_projeto`` e o tipo PostgreSQL ``empresaenum`` —
   necessário sempre que o EmpresaEnum mudar de valores (breaking change).
2. Limpa todos os registros de ``faculdade``.
3. Recria o schema completo via ``SQLModel.metadata.create_all``.
4. Insere 4 matérias base de Faculdade prontas para uso.

Uso
---
    # a partir da raiz do projeto:
    python scripts/seed_db.py           # pede confirmação interativa
    python scripts/seed_db.py --force   # pula confirmação
    python scripts/seed_db.py --force --no-faculdade  # só reseta, não insere
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

# ── Garante que o root do projeto está no sys.path ────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Imports do projeto (após path fix) ────────────────────────────────────────
from sqlalchemy import text                       # noqa: E402
from sqlmodel import SQLModel                     # noqa: E402

import domain.models  # noqa: F401, E402 — registra metadados no SQLModel
from infrastructure.database import engine, get_session  # noqa: E402


# ── Dados base de Faculdade ────────────────────────────────────────────────────

_MATERIAS: list[dict] = [
    {
        "materia":     "Microeconomia II",
        "professor":   "Prof. Dr. Santos",
        "max_faltas":  14,
        "data_p1":     date(2025, 4, 10),
        "data_p2":     date(2025, 5, 29),
        "data_final":  date(2025, 7, 3),
        "observacoes": (
            "Teoria dos jogos, oligopólio, externalidades, "
            "assimetria de informação."
        ),
    },
    {
        "materia":     "Econometria",
        "professor":   "Prof. Dr. Ferreira",
        "max_faltas":  12,
        "data_p1":     date(2025, 4, 8),
        "data_p2":     date(2025, 6, 3),
        "data_final":  date(2025, 7, 1),
        "observacoes": (
            "MQO, heterocedasticidade, autocorrelação, MQG, "
            "dados em painel, variáveis instrumentais."
        ),
    },
    {
        "materia":     "Finanças Públicas",
        "professor":   "Profa. Dra. Lima",
        "max_faltas":  10,
        "data_p1":     date(2025, 4, 15),
        "data_p2":     date(2025, 6, 10),
        "data_final":  date(2025, 7, 8),
        "observacoes": (
            "Orçamento público, federalismo fiscal, "
            "endividamento, política fiscal."
        ),
    },
    {
        "materia":     "Desenvolvimento Econômico",
        "professor":   "Prof. Dr. Cardoso",
        "max_faltas":  10,
        "data_p1":     date(2025, 4, 22),
        "data_p2":     date(2025, 6, 17),
        "data_final":  None,
        "observacoes": (
            "Teorias clássicas do desenvolvimento, catch-up tecnológico, "
            "armadilha da renda média."
        ),
    },
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables "
            "  WHERE table_schema = 'public' AND table_name = :t"
            ")"
        ),
        {"t": table_name},
    )
    return bool(result.scalar())


def _step_reset_tables() -> None:
    """
    Dropa ``work_projeto`` em CASCADE e o tipo ``empresaenum`` que o PostgreSQL
    criou automaticamente para o EmpresaEnum Python.

    Em seguida limpa ``faculdade`` se existir.
    """
    print("  → Dropando work_projeto + type empresaenum …")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS work_projeto CASCADE"))
        conn.execute(text("DROP TYPE  IF EXISTS empresaenum    CASCADE"))

        if _table_exists(conn, "faculdade"):
            print("  → Limpando faculdade …")
            conn.execute(text("DELETE FROM faculdade"))
        else:
            print("  → Tabela faculdade ainda não existe (será criada).")

    print("  ✔ Reset concluído.")


def _step_recreate_schema() -> None:
    """Cria/re-cria todas as tabelas registradas no SQLModel metadata."""
    SQLModel.metadata.create_all(engine)
    print("  ✔ Schema aplicado (CREATE TABLE IF NOT EXISTS).")


def _step_seed_faculdade() -> None:
    """Insere as matérias base via get_session (commit automático em sucesso)."""
    from domain.models import Faculdade  # import local evita ciclo antes do path fix

    with get_session() as session:
        for m in _MATERIAS:
            session.add(
                Faculdade(
                    materia=m["materia"],
                    professor=m["professor"],
                    max_faltas=m["max_faltas"],
                    data_p1=m.get("data_p1"),
                    data_p2=m.get("data_p2"),
                    data_final=m.get("data_final"),
                    observacoes=m.get("observacoes"),
                    faltas=0,
                )
            )

    print(f"  ✔ {len(_MATERIAS)} matérias inseridas com sucesso:")
    for m in _MATERIAS:
        print(f"     • {m['materia']}  (max_faltas={m['max_faltas']})")


# ── Entrypoint ─────────────────────────────────────────────────────────────────

def run(*, force: bool, seed_faculdade: bool) -> None:
    if not force:
        print()
        print("⚠️  ATENÇÃO: Este script irá:")
        print("   1. Dropar a tabela work_projeto (dados de projetos serão PERDIDOS)")
        print("   2. Limpar a tabela faculdade")
        print("   3. Recriar o schema com os Enums atualizados")
        if seed_faculdade:
            print("   4. Inserir matérias base de Faculdade")
        print()
        resp = input("   Digite 'sim' para confirmar: ").strip().lower()
        if resp != "sim":
            print("❌ Seeding cancelado.")
            return

    print()
    print("[1/3] Resetando tabelas …")
    _step_reset_tables()

    print("[2/3] Recriando schema …")
    _step_recreate_schema()

    if seed_faculdade:
        print("[3/3] Inserindo dados base de Faculdade …")
        _step_seed_faculdade()
    else:
        print("[3/3] Seeding de Faculdade ignorado (--no-faculdade).")

    print()
    print("🎉 Seeding finalizado!")
    print(f"   Projeto: {_ROOT}")
    print("   Configuração de conexão: ver .env (POSTGRES_HOST, POSTGRES_DB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Life_OS — Script de Seeding Inicial",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Pula a confirmação interativa",
    )
    parser.add_argument(
        "--no-faculdade",
        dest="no_faculdade",
        action="store_true",
        help="Reseta as tabelas mas não insere matérias base",
    )
    args = parser.parse_args()

    run(force=args.force, seed_faculdade=not args.no_faculdade)
