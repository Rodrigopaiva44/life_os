"""
domain/models.py
================
Núcleo semântico do Life_OS. Fonte única de verdade para schema e regras de domínio.

REGRAS ARQUITETURAIS (inquebráveis):
  1. Valores monetários e quantidades de ativos → decimal.Decimal via Numeric(). NUNCA float.
  2. Enumerações de domínio fechado → str Enum (validação Pydantic + legível no DB).
  3. Campos de texto longo → sa_column=Column(Text) para evitar VARCHAR(255) truncado.
  4. Timestamps → datetime com timezone UTC (armazenado como TIMESTAMP no Postgres).
  5. PKs → Integer auto-incremento; ID semântico (ex.: UUID/hash) adicionado na v2.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import Column, Numeric, Text
from sqlmodel import Field, SQLModel


# ── Fábrica de tipos internos ──────────────────────────────────────────────────

def _dec(precision: int, scale: int, *, nullable: bool = False) -> Column:
    """
    Cria uma coluna Numeric para decimal.Decimal. Nunca float.

    Guia de uso:
      _dec(14,  2)  → valores em BRL  (R$ 999_999_999_999.99)
      _dec(20,  8)  → preços em USD   (cotações de cripto/ações)
      _dec(30, 18)  → quantidades de cripto (precisão ERC-20/wei)
      _dec( 8,  2)  → macronutrientes em gramas
    """
    return Column(Numeric(precision=precision, scale=scale, asdecimal=True), nullable=nullable)


def _text(*, nullable: bool = True) -> Column:
    """Coluna TEXT — sem limite de caracteres. Usada para campos descritivos."""
    return Column(Text, nullable=nullable)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ── Enumerações de Domínio ─────────────────────────────────────────────────────

class EmpresaEnum(str, Enum):
    baker_hughes    = "Baker Hughes"
    galton_xend     = "Galton & Xend"
    bee_on_crypto   = "Bee On Crypto"
    joina_chainvite = "Joina/Chainvite"
    northfi         = "Northfi"
    dfb             = "DFB"


class PrioridadeEnum(str, Enum):
    p0_critical = "P0 - Critical"
    p1_high     = "P1 - High"
    p2_medium   = "P2 - Medium"
    p3_low      = "P3 - Low"


class WorkStatusEnum(str, Enum):
    backlog     = "Backlog"
    in_progress = "In Progress"
    review      = "Review"
    done        = "Done"
    blocked     = "Blocked"


class TipoTransacaoEnum(str, Enum):
    entrada = "Entrada"
    saida   = "Saida"


class TipoAtivoEnum(str, Enum):
    crypto     = "Crypto"
    acao       = "Acao"
    fii        = "FII"
    renda_fixa = "Renda_Fixa"
    etf        = "ETF"


class RefeicaoEnum(str, Enum):
    cafe_manha   = "Cafe_Manha"
    lanche_manha = "Lanche_Manha"
    almoco       = "Almoco"
    lanche_tarde = "Lanche_Tarde"
    jantar       = "Jantar"
    ceia         = "Ceia"


# ── Entidades ──────────────────────────────────────────────────────────────────

class Faculdade(SQLModel, table=True):
    """
    Controle acadêmico por disciplina.
    Risk management embutido: (faltas / max_faltas) → taxa de risco de reprovação.
    """
    __tablename__ = "faculdade"

    id:                 Optional[int]  = Field(default=None, primary_key=True)
    materia:            str            = Field(index=True, max_length=120)
    professor:          Optional[str]  = Field(default=None, max_length=120)
    email_professor:    Optional[str]  = Field(default=None, max_length=255)
    faltas:             int            = Field(default=0, ge=0)
    max_faltas:         int            = Field(default=10, ge=1)
    data_p1:            Optional[date] = Field(default=None)
    data_p2:            Optional[date] = Field(default=None)
    data_final:         Optional[date] = Field(default=None)
    observacoes:        Optional[str]  = Field(default=None, sa_column=_text())
    ultima_atualizacao: datetime       = Field(default_factory=_utcnow)

    @property
    def risco_reprovacao(self) -> float:
        """Percentual de faltas consumidas. >1.0 = reprovado por falta."""
        return self.faltas / self.max_faltas if self.max_faltas else 0.0


class Work_Projeto(SQLModel, table=True):
    """
    Gestão de demandas profissionais multi-empresa.
    Alinhado com o kanban da aba Work_Projetos do Life_OS.xlsx.
    """
    __tablename__ = "work_projeto"

    id:          Optional[int]      = Field(default=None, primary_key=True)
    projeto:     EmpresaEnum        = Field(index=True)
    demanda:     str                = Field(sa_column=_text(nullable=False))
    prioridade:  PrioridadeEnum     = Field(default=PrioridadeEnum.p2_medium)
    status:      WorkStatusEnum     = Field(default=WorkStatusEnum.backlog, index=True)
    deadline:    Optional[datetime] = Field(default=None)
    link_docs:   Optional[str]      = Field(default=None, max_length=2048)
    observacoes: Optional[str]      = Field(default=None, sa_column=_text())
    criado_em:   datetime           = Field(default_factory=_utcnow)
    atualizado_em: datetime         = Field(default_factory=_utcnow)


class Fin_Transacao(SQLModel, table=True):
    """
    Ledger de transações financeiras (entradas e saídas).
    REGRA: `valor` é sempre positivo. O sinal de fluxo é determinado por `tipo`.
    """
    __tablename__ = "fin_transacao"

    id:        Optional[int]      = Field(default=None, primary_key=True)
    data_hora: datetime           = Field(default_factory=_utcnow, index=True)
    tipo:      TipoTransacaoEnum  = Field(index=True)
    categoria: str                = Field(max_length=100, index=True)
    # Precisão BRL: 12 dígitos inteiros + 2 casas decimais
    valor:     Decimal            = Field(sa_column=_dec(14, 2))
    conta:     str                = Field(max_length=100)
    descricao: Optional[str]      = Field(default=None, sa_column=_text())


class Fin_Investimento(SQLModel, table=True):
    """
    Posições abertas em ativos financeiros e criptoativos.

    Campos de precisão estendida para compatibilidade com DeFi/ERC-20:
      - quantidade:      Decimal(30, 18) → suporta quantidades fracionadas de wei
      - preco_medio_usd: Decimal(20,  8) → 8 casas decimais como padrão da indústria cripto
    """
    __tablename__ = "fin_investimento"

    id:              Optional[int]  = Field(default=None, primary_key=True)
    ticker:          str            = Field(index=True, max_length=20)
    tipo_ativo:      TipoAtivoEnum  = Field(index=True)
    quantidade:      Decimal        = Field(sa_column=_dec(30, 18))
    preco_medio_usd: Decimal        = Field(sa_column=_dec(20, 8))
    carteira:        str            = Field(max_length=100, index=True)
    atualizado_em:   datetime       = Field(default_factory=_utcnow)


class Saude_Nutricao(SQLModel, table=True):
    """
    Registro nutricional por refeição.
    Granularidade por alimento permite análise de macro split e déficit calórico.
    """
    __tablename__ = "saude_nutricao"

    id:            Optional[int]  = Field(default=None, primary_key=True)
    data_registro: date           = Field(index=True)
    refeicao:      RefeicaoEnum   = Field(index=True)
    alimento:      str            = Field(max_length=200)
    # Todos os campos de quantidade/macro em Decimal para precisão analítica
    quantidade_g:  Decimal        = Field(sa_column=_dec(8, 2))
    calorias:      int            = Field(ge=0)
    carboidratos:  Decimal        = Field(sa_column=_dec(8, 2))
    proteinas:     Decimal        = Field(sa_column=_dec(8, 2))
    gorduras:      Decimal        = Field(sa_column=_dec(8, 2))
