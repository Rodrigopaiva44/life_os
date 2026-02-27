"""
application/llm_router.py
==========================
Motor Cognitivo do Life_OS.

Combina STT + extração de entidades em uma única chamada multimodal ao Gemini,
eliminando a necessidade de um serviço de transcrição separado.

Fluxo:
  1. Recebe o caminho local de um arquivo de voz (.ogg do Telegram).
  2. Faz upload para a Gemini File API via cliente assíncrono nativo.
  3. Envia o áudio + prompt ao gemini-2.5-flash com response_schema=AgentResponse.
  4. Retorna o JSON estruturado da resposta.
  5. Limpa o arquivo no Google Cloud e no disco local (bloco finally).

Arquitetura de dados:
  - Os *Payload models* são Pydantic BaseModel puros (sem SQLAlchemy) para que
    o Gemini consiga gerar um JSON Schema válido. Usam `float` no lugar de
    `Decimal` e `str` (ISO 8601) no lugar de `date`/`datetime`.
  - Os Enum de domínio são importados de domain.models como fonte única de
    verdade — o schema do Gemini herda automaticamente os valores permitidos.
  - A camada de aplicação downstream (services/) é responsável por mapear os
    Payloads para as entidades SQLModel antes de persistir no banco.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, field_validator

from domain.models import (
    EmpresaEnum,
    PrioridadeEnum,
    RefeicaoEnum,
    TipoAtivoEnum,
    TipoTransacaoEnum,
    WorkStatusEnum,
)
from infrastructure.settings import settings

logger = logging.getLogger(__name__)

_MODEL = "gemini-2.5-flash"

_PROMPT = """\
Você é o assistente pessoal do Life_OS. Ouça o áudio com atenção e execute:

1. Identifique a área da vida a que o relato pertence:
   - FACULDADE   → aulas, matérias, professores, faltas, provas
   - TRABALHO    → demandas, tarefas e projetos profissionais
   - FINANÇAS / TRANSAÇÃO   → receitas, despesas, pagamentos
   - FINANÇAS / INVESTIMENTO → compra ou venda de ativo, cripto, ações, FIIs
   - SAÚDE / NUTRIÇÃO → refeições, alimentos consumidos, macros, calorias

2. Preencha ESTRITAMENTE o campo JSON correspondente:
   - faculdade_data        → apenas para FACULDADE
   - workflow_data         → apenas para TRABALHO
   - fin_transacao_data    → apenas para FINANÇAS / TRANSAÇÃO
   - fin_investimento_data → apenas para FINANÇAS / INVESTIMENTO
   - saude_nutricao_data   → apenas para SAÚDE / NUTRIÇÃO

3. Deixe NULOS todos os campos das áreas não mencionadas.

4. Preencha `intent_summary` com uma frase curta (máx. 15 palavras) resumindo \
o que foi capturado.

Regras de formatação:
- Datas → formato ISO 8601 (YYYY-MM-DD).
- Valores monetários e quantidades → float.
- Não invente dados que não foram ditos no áudio.

⚠️ REGRA ESTRITA — Campos Enum de workflow_data (Work_Projeto):
   Esses campos aceitam SOMENTE os identificadores exatos abaixo. NUNCA use
   texto livre, capitalização diferente ou valores não listados.

   • projeto    → 'baker_hughes'  | 'xend'      | 'beeoncrypto' | 'dfb'
   • prioridade → 'p0_critical'   | 'p1_high'   | 'p2_medium'   | 'p3_low'
   • status     → 'backlog'       | 'in_progress' | 'review'    | 'done' | 'blocked'\
"""


# ── Payload models (Pydantic puro, sem SQLAlchemy) ─────────────────────────────

class FaculdadePayload(BaseModel):
    materia:         str
    professor:       Optional[str] = None
    email_professor: Optional[str] = None
    faltas:          int           = 0
    max_faltas:      int           = 10
    data_p1:         Optional[str] = None   # ISO date
    data_p2:         Optional[str] = None
    data_final:      Optional[str] = None
    observacoes:     Optional[str] = None


class WorkflowPayload(BaseModel):
    """Payload para Work_Projeto.

    Os validadores abaixo aceitam tanto o *name* do Enum (ex: 'baker_hughes'),
    quanto o *value* (ex: 'Baker Hughes'), garantindo resiliência independente
    do formato que o Gemini retornar — seja guiado pelo prompt ou pelo schema.
    """
    projeto:     EmpresaEnum
    demanda:     str
    prioridade:  PrioridadeEnum  = PrioridadeEnum.p2_medium
    status:      WorkStatusEnum  = WorkStatusEnum.backlog
    deadline:    Optional[str]   = None   # ISO datetime
    link_docs:   Optional[str]   = None
    observacoes: Optional[str]   = None

    @field_validator("projeto", mode="before")
    @classmethod
    def _coerce_projeto(cls, v: object) -> EmpresaEnum:
        if isinstance(v, EmpresaEnum):
            return v
        if isinstance(v, str):
            try:
                return EmpresaEnum(v)       # pelo VALUE: "Baker Hughes"
            except ValueError:
                pass
            try:
                return EmpresaEnum[v]       # pelo NAME: "baker_hughes"
            except KeyError:
                pass
        raise ValueError(
            f"Valor inválido para 'projeto': {v!r}. "
            f"Aceitos: {[e.name for e in EmpresaEnum]}"
        )

    @field_validator("prioridade", mode="before")
    @classmethod
    def _coerce_prioridade(cls, v: object) -> PrioridadeEnum:
        if isinstance(v, PrioridadeEnum):
            return v
        if isinstance(v, str):
            try:
                return PrioridadeEnum(v)    # pelo VALUE: "P0 - Critical"
            except ValueError:
                pass
            try:
                return PrioridadeEnum[v]    # pelo NAME: "p0_critical"
            except KeyError:
                pass
        raise ValueError(
            f"Valor inválido para 'prioridade': {v!r}. "
            f"Aceitos: {[e.name for e in PrioridadeEnum]}"
        )

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: object) -> WorkStatusEnum:
        if isinstance(v, WorkStatusEnum):
            return v
        if isinstance(v, str):
            try:
                return WorkStatusEnum(v)    # pelo VALUE: "In Progress"
            except ValueError:
                pass
            try:
                return WorkStatusEnum[v]    # pelo NAME: "in_progress"
            except KeyError:
                pass
        raise ValueError(
            f"Valor inválido para 'status': {v!r}. "
            f"Aceitos: {[e.name for e in WorkStatusEnum]}"
        )


class FinTransacaoPayload(BaseModel):
    tipo:      TipoTransacaoEnum
    categoria: str
    valor:     float
    conta:     str
    descricao: Optional[str] = None


class FinInvestimentoPayload(BaseModel):
    ticker:          str
    tipo_ativo:      TipoAtivoEnum
    quantidade:      float
    preco_medio_usd: float
    carteira:        str


class SaudeNutricaoPayload(BaseModel):
    data_registro: str   # ISO date
    refeicao:      RefeicaoEnum
    alimento:      str
    quantidade_g:  float
    calorias:      int
    carboidratos:  float
    proteinas:     float
    gorduras:      float


class AgentResponse(BaseModel):
    """Resposta mestre do Motor Cognitivo.

    Apenas um campo de dados será preenchido por chamada — o que corresponde
    à área da vida detectada no áudio. Os demais permanecem None.
    """
    intent_summary:         str
    faculdade_data:         Optional[FaculdadePayload]       = None
    workflow_data:          Optional[WorkflowPayload]        = None
    fin_transacao_data:     Optional[FinTransacaoPayload]    = None
    fin_investimento_data:  Optional[FinInvestimentoPayload] = None
    saude_nutricao_data:    Optional[SaudeNutricaoPayload]   = None


# ── Client (singleton de módulo) ───────────────────────────────────────────────
# Instanciado uma única vez; client.aio.* expõe a interface assíncrona nativa.
_client = genai.Client(api_key=settings.gemini_api_key)


# ── Use-case principal ────────────────────────────────────────────────────────

async def processar_audio_para_json(file_path: str) -> str:
    """Processa um arquivo de voz e retorna JSON estruturado (AgentResponse).

    Args:
        file_path: Caminho local para o arquivo .ogg gerado pelo Telegram.

    Returns:
        String JSON válida representando um AgentResponse serializado.

    Raises:
        RuntimeError: Em caso de falha no upload ou na geração do conteúdo.
    """
    uploaded_file = None
    try:
        logger.info("Motor Cognitivo: iniciando upload — %s", file_path)

        uploaded_file = await _client.aio.files.upload(
            file=file_path,
            config=types.UploadFileConfig(mime_type="audio/ogg"),
        )
        logger.debug("Arquivo enviado à Gemini File API: %s", uploaded_file.name)

        response = await _client.aio.models.generate_content(
            model=_MODEL,
            contents=[
                types.Part.from_uri(
                    file_uri=uploaded_file.uri,
                    mime_type="audio/ogg",
                ),
                types.Part.from_text(text=_PROMPT),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AgentResponse,
            ),
        )

        json_text = response.text.strip()
        logger.info(
            "Motor Cognitivo: resposta estruturada gerada (%d chars).", len(json_text)
        )
        return json_text

    except Exception as exc:
        logger.exception(
            "Motor Cognitivo: erro ao processar '%s': %s", file_path, exc
        )
        raise RuntimeError(f"Falha no processamento de '{file_path}'") from exc

    finally:
        # Remove o arquivo local independentemente do resultado.
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.debug("Arquivo local removido: %s", file_path)

        # Remove o arquivo remoto para não acumular cota na Gemini File API.
        if uploaded_file is not None:
            try:
                await _client.aio.files.delete(name=uploaded_file.name)
                logger.debug("Arquivo remoto removido: %s", uploaded_file.name)
            except Exception:
                logger.warning(
                    "Não foi possível remover o arquivo remoto '%s'.",
                    uploaded_file.name,
                )
