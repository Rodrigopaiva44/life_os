"""
application/executor.py
========================
Camada de Atuação (Executor) do Life_OS.

Responsabilidade: receber o JSON estruturado gerado pelo Motor Cognitivo,
converter os tipos do Payload (float, str ISO) para os tipos do domínio
(Decimal, date, datetime) e persistir via SQLModel + PostgreSQL.

Por que não usar model_dump() direto?
  Os Payload models usam float para valores numéricos (necessário para o JSON
  Schema do Gemini) e str para datas. As entidades SQLModel exigem Decimal e
  date/datetime. Os builders abaixo fazem esse mapeamento explicitamente,
  respeitando a regra arquitetural "NUNCA float para valores monetários".

Concorrência:
  get_session() é síncrono (psycopg2). O bloco de DB é executado em
  asyncio.to_thread para não bloquear o event-loop do bot Telegram.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from pydantic import ValidationError

from application.llm_router import (
    AgentResponse,
    FaculdadePayload,
    FinInvestimentoPayload,
    FinTransacaoPayload,
    SaudeNutricaoPayload,
    WorkflowPayload,
)
from domain.models import (
    Faculdade,
    Fin_Investimento,
    Fin_Transacao,
    Saude_Nutricao,
    Work_Projeto,
)
from infrastructure.database import get_session

logger = logging.getLogger(__name__)


# ── Type-conversion helpers ────────────────────────────────────────────────────

def _to_date(value: Optional[str]) -> Optional[date]:
    """Converte string ISO 8601 para date. Tolerante a "YYYY-MM-DDTHH:MM:SS"."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        logger.warning("Data inválida ignorada: %r", value)
        return None


def _to_datetime(value: Optional[str]) -> Optional[datetime]:
    """Converte string ISO 8601 para datetime com timezone UTC."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        logger.warning("Datetime inválido ignorado: %r", value)
        return None


def _dec(value: float) -> Decimal:
    """float → Decimal via string para preservar precisão decimal."""
    return Decimal(str(value))


# ── Entity builders ────────────────────────────────────────────────────────────

def _build_faculdade(p: FaculdadePayload) -> Faculdade:
    return Faculdade(
        materia=p.materia,
        professor=p.professor,
        email_professor=p.email_professor,
        faltas=p.faltas,
        max_faltas=p.max_faltas,
        data_p1=_to_date(p.data_p1),
        data_p2=_to_date(p.data_p2),
        data_final=_to_date(p.data_final),
        observacoes=p.observacoes,
    )


def _build_work_projeto(p: WorkflowPayload) -> Work_Projeto:
    return Work_Projeto(
        projeto=p.projeto,
        demanda=p.demanda,
        prioridade=p.prioridade,
        status=p.status,
        deadline=_to_datetime(p.deadline),
        link_docs=p.link_docs,
        observacoes=p.observacoes,
    )


def _build_fin_transacao(p: FinTransacaoPayload) -> Fin_Transacao:
    return Fin_Transacao(
        tipo=p.tipo,
        categoria=p.categoria,
        valor=_dec(p.valor),
        conta=p.conta,
        descricao=p.descricao,
    )


def _build_fin_investimento(p: FinInvestimentoPayload) -> Fin_Investimento:
    return Fin_Investimento(
        ticker=p.ticker,
        tipo_ativo=p.tipo_ativo,
        quantidade=_dec(p.quantidade),
        preco_medio_usd=_dec(p.preco_medio_usd),
        carteira=p.carteira,
    )


def _build_saude_nutricao(p: SaudeNutricaoPayload) -> Saude_Nutricao:
    return Saude_Nutricao(
        data_registro=_to_date(p.data_registro) or date.today(),
        refeicao=p.refeicao,
        alimento=p.alimento,
        quantidade_g=_dec(p.quantidade_g),
        calorias=p.calorias,
        carboidratos=_dec(p.carboidratos),
        proteinas=_dec(p.proteinas),
        gorduras=_dec(p.gorduras),
    )


# ── Sync persistence block (executado via asyncio.to_thread) ──────────────────

def _persistir_sync(response: AgentResponse) -> str:
    """Persiste a entidade no banco e devolve a mensagem de confirmação.

    Síncrono por design (psycopg2). Chamado em thread pool pelo wrapper async.
    O commit/rollback é gerenciado automaticamente pelo context manager de sessão.
    """
    with get_session() as session:

        if response.faculdade_data:
            p = response.faculdade_data
            session.add(_build_faculdade(p))
            pct = int((p.faltas / p.max_faltas) * 100) if p.max_faltas else 0
            return (
                f"✅ Faculdade registrada\n"
                f"📚 Matéria: {p.materia}\n"
                f"🚫 Faltas: {p.faltas}/{p.max_faltas} ({pct}% consumido)\n"
                f"💬 {response.intent_summary}"
            )

        if response.workflow_data:
            p = response.workflow_data
            session.add(_build_work_projeto(p))
            demanda_curta = p.demanda[:60] + "…" if len(p.demanda) > 60 else p.demanda
            return (
                f"✅ Tarefa adicionada ao Kanban\n"
                f"🏢 Projeto: {p.projeto.value}\n"
                f"📋 {demanda_curta}\n"
                f"🔥 {p.prioridade.value}  |  {p.status.value}\n"
                f"💬 {response.intent_summary}"
            )

        if response.fin_transacao_data:
            p = response.fin_transacao_data
            session.add(_build_fin_transacao(p))
            sinal = "📈" if p.tipo.value == "Entrada" else "📉"
            return (
                f"✅ Transação registrada\n"
                f"{sinal} {p.tipo.value}: R$ {p.valor:,.2f}\n"
                f"🗂 Categoria: {p.categoria}  |  Conta: {p.conta}\n"
                f"💬 {response.intent_summary}"
            )

        if response.fin_investimento_data:
            p = response.fin_investimento_data
            session.add(_build_fin_investimento(p))
            return (
                f"✅ Posição registrada\n"
                f"💹 {p.quantidade} {p.ticker} ({p.tipo_ativo.value})\n"
                f"💰 PM: USD {p.preco_medio_usd:,.8f}  |  Carteira: {p.carteira}\n"
                f"💬 {response.intent_summary}"
            )

        if response.saude_nutricao_data:
            p = response.saude_nutricao_data
            session.add(_build_saude_nutricao(p))
            return (
                f"✅ Refeição registrada\n"
                f"🍽 {p.refeicao.value}: {p.alimento} ({p.quantidade_g}g)\n"
                f"🔥 {p.calorias} kcal  |  "
                f"P: {p.proteinas}g  C: {p.carboidratos}g  G: {p.gorduras}g\n"
                f"💬 {response.intent_summary}"
            )

    # Nenhum campo de domínio populado — Motor Cognitivo não identificou área.
    return f"⚠️ Nenhum dado identificável foi salvo.\n💬 {response.intent_summary}"


# ── Public async use-case ─────────────────────────────────────────────────────

async def persistir_dados(json_str: str) -> str:
    """Valida, persiste e confirma em uma única chamada.

    Args:
        json_str: JSON produzido por processar_audio_para_json.

    Returns:
        Mensagem amigável informando o que foi salvo.

    Raises:
        ValueError: JSON não pôde ser validado como AgentResponse.
        RuntimeError: Falha na persistência no banco de dados.
    """
    try:
        response = AgentResponse.model_validate_json(json_str)
    except ValidationError as exc:
        logger.error("Executor: JSON inválido recebido do Motor Cognitivo:\n%s", exc)
        raise ValueError("Resposta do Motor Cognitivo não pôde ser validada.") from exc

    logger.info(
        "Executor: AgentResponse validado. Intent: '%s'", response.intent_summary
    )

    try:
        confirmation = await asyncio.to_thread(_persistir_sync, response)
    except Exception as exc:
        logger.exception("Executor: falha na persistência: %s", exc)
        raise RuntimeError("Falha ao salvar os dados no banco.") from exc

    logger.info("Executor: persistência concluída — %s", confirmation.splitlines()[0])
    return confirmation
