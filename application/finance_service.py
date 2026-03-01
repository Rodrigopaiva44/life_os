"""
application/finance_service.py
================================
Serviço de Market Data em tempo real via Yahoo Finance (yfinance).

Design:
  - @st.cache_data(ttl=300): preços são refrescados a cada 5 minutos.
  - _PRICE_FALLBACK: dict de módulo que persiste o último preço bem-sucedido.
    Na expiração do cache, se a API falhar, o fallback é usado em vez de 0.
  - Ticker resolution: converte tickers internos para o formato do Yahoo Finance
    com base no tipo de ativo (Crypto → TICKER-USD, BR → TICKER.SA, etc.).
  - Silent failure: exceções do yfinance nunca propagam para o dashboard.
"""

from __future__ import annotations

import logging
from typing import Final

import streamlit as st
import yfinance as yf

logger = logging.getLogger(__name__)

# Fallback em memória — sobrevive entre expirations do cache (in-process)
_PRICE_FALLBACK: dict[str, float] = {}

# Tipos de ativo sem cotação negociável em exchange
_NO_MARKET_TYPES: Final[frozenset[str]] = frozenset({"Renda_Fixa"})


# ── Ticker resolution ──────────────────────────────────────────────────────────

def _resolve_yf_ticker(ticker: str, tipo_ativo: str) -> str:
    """Converte ticker interno para o formato do Yahoo Finance.

    Regras:
      - Crypto       → TICKER-USD   (ex: BTC → BTC-USD)
      - Acao / FII   → se não tiver sufixo, tenta raw (US market);
                       fornecedor pode passar "PETR4.SA" diretamente
      - ETF          → raw ticker (assume US market)
      - Outros       → raw ticker
    """
    t = ticker.upper().strip()
    if tipo_ativo == "Crypto":
        return t if t.endswith("-USD") else f"{t}-USD"
    return t


def _fetch_price(yf_ticker: str) -> float | None:
    """Busca o preço mais recente de um ticker no Yahoo Finance.

    Tenta `last_price` primeiro (preço intraday / pós-market); cai em
    `previous_close` quando o mercado está fechado. Retorna None em falha.
    """
    try:
        fi = yf.Ticker(yf_ticker).fast_info
        price = getattr(fi, "last_price", None) or getattr(fi, "previous_close", None)
        return float(price) if price else None
    except Exception as exc:
        logger.debug("yfinance falhou para %s: %s", yf_ticker, exc)
        return None


# ── Public API ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_live_prices(
    ticker_info: tuple[tuple[str, str], ...]
) -> dict[str, float]:
    """Retorna {ticker: preco_atual} para cada ativo da carteira.

    Args:
        ticker_info: Tupla imutável de (ticker, tipo_ativo).
                     Tupla é usada (em vez de lista) para ser hashável
                     pelo mecanismo de cache do Streamlit.

    Returns:
        Dict com o preço mais recente disponível em USD ou moeda nativa
        do exchange. Ativos sem cotação (Renda_Fixa) retornam 0.0.
        Em caso de falha da API, devolve o último valor bem-sucedido
        armazenado em _PRICE_FALLBACK, ou 0.0 se nunca houve dado.
    """
    result: dict[str, float] = {}

    for ticker, tipo in ticker_info:
        if tipo in _NO_MARKET_TYPES:
            result[ticker] = 0.0
            continue

        yf_ticker = _resolve_yf_ticker(ticker, tipo)
        price = _fetch_price(yf_ticker)

        if price is not None and price > 0:
            result[ticker] = price
            _PRICE_FALLBACK[ticker] = price          # atualiza fallback
        else:
            fallback = _PRICE_FALLBACK.get(ticker, 0.0)
            result[ticker] = fallback
            if fallback == 0.0:
                logger.warning(
                    "Sem preço para %s (%s) — usando 0.", ticker, yf_ticker
                )
            else:
                logger.info(
                    "yfinance indisponível para %s — usando fallback %.8f",
                    ticker, fallback,
                )

    return result
