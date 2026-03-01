"""
application/briefing_service.py
================================
AI Chief of Staff — Gerador de Daily Briefing Tático.

Sintetiza patrimônio, projetos críticos e riscos acadêmicos em um briefing
executivo usando Gemini 2.5 Flash.

Design:
  - @st.cache_data(ttl=3600): uma única chamada à LLM por hora — sem custo
    extra em reloads e sem latência percebida pelo usuário.
  - Silent fallback: qualquer exceção (rede, cota, timeout) retorna uma
    mensagem amigável sem quebrar o dashboard.
  - Singleton do cliente: _client instanciado uma vez no módulo.
"""

from __future__ import annotations

import logging

import streamlit as st
from google import genai
from google.genai import types

from infrastructure.settings import settings

logger = logging.getLogger(__name__)

_MODEL = "gemini-2.5-flash"

_SYSTEM_PROMPT = """\
Você é o Chief of Staff (Diretor de Operações) de um fundo de investimentos \
e advisor pessoal do usuário. \
Analise os dados brutos de patrimônio, projetos e faculdade abaixo. \
Forneça um briefing tático MATINAL em formato Markdown.

Estrutura obrigatória:
1. 🚨 Red Flags (O que está em risco crítico, ex: Tarefas P0, Faltas altas na \
faculdade, Status Blocked). Se não houver, elogie a estabilidade.
2. 🎯 Foco do Dia (Ação sugerida).

Seja calculista, direto, frio e aja como um parceiro de negócios de alto nível. \
Use no máximo 3 parágrafos curtos.\
"""

# Singleton: instanciado uma vez; reutilizado em todas as chamadas cacheadas.
_client = genai.Client(api_key=settings.gemini_api_key)


def _format_context(context_data: dict) -> str:
    """Converte o dicionário de contexto em uma string legível para o prompt."""
    lines = ["### DADOS DO SISTEMA (Life OS)\n"]
    for key, value in context_data.items():
        if isinstance(value, list):
            lines.append(f"**{key}**:")
            if value:
                lines.extend(f"  - {item}" for item in value)
            else:
                lines.append("  - (nenhum)")
        else:
            lines.append(f"**{key}**: {value}")
    return "\n".join(lines)


@st.cache_data(ttl=3600)
def generate_executive_briefing(context_data: dict) -> str:
    """Gera o briefing executivo diário com Gemini 2.5 Flash.

    Args:
        context_data: Dicionário com resumo do estado atual do Life OS
                      (patrimônio, projetos críticos, riscos acadêmicos).

    Returns:
        Markdown com o briefing tático. Em caso de falha, retorna um
        fallback silencioso para não quebrar o dashboard.

    Cache:
        TTL de 1 hora — evita chamadas redundantes a cada reload da página.
    """
    context_str = _format_context(context_data)
    full_prompt  = f"{_SYSTEM_PROMPT}\n\n{context_str}"

    try:
        response = _client.models.generate_content(
            model=_MODEL,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                temperature=0.65,
                max_output_tokens=512,
            ),
        )
        text = (response.text or "").strip()
        if not text:
            raise ValueError("Resposta vazia do modelo.")
        logger.info("Chief of Staff: briefing gerado (%d chars).", len(text))
        return text

    except Exception as exc:
        logger.warning("Chief of Staff: fallback ativado — %s", exc)
        return "_Briefing indisponível no momento. Tente novamente em instantes._"
