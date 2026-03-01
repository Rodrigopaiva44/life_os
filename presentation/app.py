"""
presentation/app.py
====================
Life OS — Command Center  ·  Hedge Fund Grade Dashboard.

Dados entram exclusivamente via Telegram / Motor Cognitivo (telegram_bot.py).
Este painel é somente leitura.

Para rodar a partir da raiz do projeto:
    streamlit run presentation/app.py
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlmodel import select

from application import briefing_service, finance_service

try:
    from streamlit_agraph import Config as GraphConfig
    from streamlit_agraph import Edge, Node, agraph

    _AGRAPH_OK = True
except ImportError:
    _AGRAPH_OK = False
from domain.models import (
    EmpresaEnum,
    Faculdade,
    Fin_Investimento,
    Fin_Transacao,
    PrioridadeEnum,
    Saude_Nutricao,
    Work_Projeto,
)
from infrastructure.database import get_session

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    layout="wide",
    page_title="Life OS — Command Center",
    page_icon="⚡",
    initial_sidebar_state="collapsed",
)

# ── CSS — Hedge Fund Institutional Dark Theme ──────────────────────────────────
st.markdown(
    """
<style>
/* ── Base ── */
[data-testid="stApp"] {
    background-color: #0a0a0a;
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
}
.block-container { padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1480px; }

/* ── Metric cards ── */
[data-testid="metric-container"] {
    background-color: #111;
    border: 1px solid #222;
    border-radius: 8px;
    padding: 0.9rem 1.15rem;
}
[data-testid="metric-container"] label {
    color: #555 !important;
    font-size: 0.68rem !important;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
}
[data-testid="stMetricValue"] {
    color: #e8e8e8 !important;
    font-size: 1.45rem !important;
    font-weight: 700 !important;
}
[data-testid="stMetricDelta"] {
    font-size: 0.78rem !important;
    font-weight: 600 !important;
}

/* ── Tabs ── */
[data-baseweb="tab-list"] { gap: 0; border-bottom: 1px solid #1c1c1c; }
[data-baseweb="tab"] {
    color: #444;
    font-weight: 500;
    letter-spacing: 0.04em;
    padding: 0.6rem 1.4rem;
    border-radius: 0;
    transition: color 0.15s;
}
[aria-selected="true"][data-baseweb="tab"] {
    color: #00d4aa !important;
    border-bottom: 2px solid #00d4aa !important;
    background: transparent !important;
}
[data-baseweb="tab-highlight"] { background: transparent !important; }

/* ── DataFrames ── */
[data-testid="stDataFrame"] {
    border: 1px solid #1c1c1c;
    border-radius: 8px;
    overflow: hidden;
}

/* ── Misc ── */
hr { border-color: #1c1c1c !important; }
[data-testid="stProgressBar"] > div > div > div { background-color: #00d4aa !important; }
[data-testid="stAlert"] { border-radius: 6px; }

/* ── Chief of Staff expander ── */
[data-testid="stExpander"] {
    border: 1px solid #00d4aa33 !important;
    border-radius: 8px !important;
    background-color: #060f0c !important;
}
[data-testid="stExpander"] summary {
    color: #00d4aa !important;
    font-weight: 700 !important;
    letter-spacing: 0.04em;
}

/* ── Section labels ── */
.section-label {
    color: #444;
    font-size: 0.70rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin: 1.75rem 0 0.6rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #1c1c1c;
}

/* ── Kanban ── */
.kanban-col-header {
    font-size: 0.70rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    text-align: center;
    padding: 0.45rem 0.5rem;
    border-radius: 6px;
    margin-bottom: 0.7rem;
}
.kanban-card {
    background: #111;
    border: 1px solid #1e1e1e;
    border-radius: 8px;
    padding: 0.7rem 0.85rem;
    margin-bottom: 0.55rem;
    border-left: 3px solid #333;
    transition: border-color 0.15s;
}
.kanban-meta {
    font-size: 0.67rem;
    color: #555;
    margin-bottom: 0.28rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
}
.kanban-title {
    font-size: 0.84rem;
    color: #ccc;
    line-height: 1.5;
}
.kanban-deadline {
    font-size: 0.70rem;
    color: #444;
    margin-top: 0.3rem;
}
</style>
""",
    unsafe_allow_html=True,
)

# ── Constants ──────────────────────────────────────────────────────────────────

_META_KCAL: int = 2500

_CHART_LAYOUT = dict(
    paper_bgcolor="#111",
    plot_bgcolor="#111",
    font_color="#888",
    margin=dict(t=44, b=14, l=14, r=14),
    title_font=dict(color="#555", size=12),
    legend=dict(font=dict(color="#888"), bgcolor="rgba(0,0,0,0)"),
    xaxis=dict(gridcolor="#1c1c1c", linecolor="#1c1c1c", tickfont=dict(color="#555")),
    yaxis=dict(gridcolor="#1c1c1c", linecolor="#1c1c1c", tickfont=dict(color="#555")),
)

_PRIO_CFG: dict[str, tuple[str, str]] = {
    "P0 - Critical": ("🔥🔥", "#ff4b4b"),
    "P1 - High":     ("🔥",   "#ff8c00"),
    "P2 - Medium":   ("▸",    "#00d4aa"),
    "P3 - Low":      ("·",    "#3a5a6a"),
}

_KANBAN_COL_COLORS: dict[str, str] = {
    "Backlog":     "#1a2035",
    "In Progress": "#0d2d1a",
    "Review":      "#2d2200",
    "Done":        "#0d2a0d",
}

_KANBAN_TEXT_COLORS: dict[str, str] = {
    "Backlog":     "#4a7fa5",
    "In Progress": "#00d4aa",
    "Review":      "#f59e0b",
    "Done":        "#22c55e",
}

# Timetable hardcoded (M1–T3 × Seg–Sex) — substituir por dado do DB na v2
_GRADE_HORARIOS = ["M1 — 07:30", "M2 — 09:30", "T1 — 13:00", "T2 — 15:00", "T3 — 17:00"]
_GRADE_DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"]


# ── Format helpers ─────────────────────────────────────────────────────────────

def _brl(value: Decimal) -> str:
    """R$ 1.234,56 — Decimal puro, nunca float."""
    q = abs(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    s = str(q)
    int_str, _, dec_str = s.partition(".")
    dec_str = dec_str.ljust(2, "0")[:2]
    out: list[str] = []
    for i, ch in enumerate(reversed(int_str)):
        if i > 0 and i % 3 == 0:
            out.append(".")
        out.append(ch)
    sign = "-" if value < 0 else ""
    return f"{sign}R$ {''.join(reversed(out))},{dec_str}"


def _usd(value: Decimal, decimals: int = 2, signed: bool = False) -> str:
    """$ 1,234.56 — Decimal puro. `signed=True` adiciona + em positivos."""
    fmt = Decimal(10) ** -decimals
    q = abs(value.quantize(fmt, rounding=ROUND_HALF_UP))
    s = str(q)
    int_str, _, dec_str = s.partition(".")
    dec_str = dec_str.ljust(decimals, "0")[:decimals]
    out: list[str] = []
    for i, ch in enumerate(reversed(int_str)):
        if i > 0 and i % 3 == 0:
            out.append(",")
        out.append(ch)
    if value < 0:
        sign = "-"
    elif signed and value > 0:
        sign = "+"
    else:
        sign = ""
    return f"{sign}$ {''.join(reversed(out))}.{dec_str}"


def _enum_str(v: object) -> str:
    """Extrai string de Enum de forma defensiva — tolera Enum, str e None."""
    if hasattr(v, "value"):
        return str(v.value)
    return str(v) if v is not None else ""


def _kanban_card(
    demanda: str,
    prioridade: str,
    empresa: str,
    deadline: datetime | date | None,
) -> str:
    """Renderiza um card de Kanban como HTML inline."""
    emoji, border_color = _PRIO_CFG.get(prioridade, ("•", "#333"))
    title = demanda[:85] + "…" if len(demanda) > 85 else demanda
    dl_html = ""
    if deadline:
        dl_fmt = (
            deadline.strftime("%d/%m/%y %H:%M")
            if isinstance(deadline, datetime)
            else deadline.strftime("%d/%m/%y")
        )
        dl_html = f'<div class="kanban-deadline">📅 {dl_fmt}</div>'
    return (
        f'<div class="kanban-card" style="border-left-color:{border_color};">'
        f'<div class="kanban-meta">{emoji} {prioridade} · {empresa}</div>'
        f'<div class="kanban-title">{title}</div>'
        f"{dl_html}"
        f"</div>"
    )


def _style_pnl_col(series: pd.Series) -> list[str]:
    """Aplica cor verde/vermelho a células de PnL no DataFrame."""
    out = []
    for val in series:
        if not isinstance(val, str) or val in ("—", ""):
            out.append("")
        elif str(val).startswith("+"):
            out.append("color: #00d4aa; font-weight: 600")
        elif str(val).startswith("-"):
            out.append("color: #ff4b4b; font-weight: 600")
        else:
            out.append("")
    return out


# ── Cached query functions (TTL 60 s) ──────────────────────────────────────────

@st.cache_data(ttl=60)
def get_investimentos() -> list[dict]:
    with get_session() as session:
        rows = session.exec(
            select(Fin_Investimento).order_by(Fin_Investimento.ticker)
        ).all()
        return [
            {
                "ticker":          r.ticker,
                "tipo_ativo":      _enum_str(r.tipo_ativo),
                "quantidade":      r.quantidade,
                "preco_medio_usd": r.preco_medio_usd,
                "carteira":        r.carteira,
                "atualizado_em":   r.atualizado_em,
            }
            for r in rows
        ]


@st.cache_data(ttl=60)
def get_transacoes() -> list[dict]:
    with get_session() as session:
        rows = session.exec(
            select(Fin_Transacao).order_by(Fin_Transacao.data_hora.desc())
        ).all()
        return [
            {
                "data_hora": r.data_hora,
                "tipo":      _enum_str(r.tipo),
                "categoria": r.categoria,
                "valor":     r.valor,
                "conta":     r.conta,
                "descricao": r.descricao or "",
            }
            for r in rows
        ]


@st.cache_data(ttl=60)
def get_projetos() -> list[dict]:
    with get_session() as session:
        rows = session.exec(
            select(Work_Projeto).order_by(
                Work_Projeto.prioridade,
                Work_Projeto.criado_em.desc(),
            )
        ).all()
        return [
            {
                "projeto":     _enum_str(r.projeto),
                "demanda":     r.demanda,
                "prioridade":  _enum_str(r.prioridade),
                "status":      _enum_str(r.status),
                "deadline":    r.deadline,
                "observacoes": r.observacoes or "",
            }
            for r in rows
        ]


@st.cache_data(ttl=60)
def get_faculdade() -> list[dict]:
    with get_session() as session:
        rows = session.exec(
            select(Faculdade).order_by(Faculdade.materia)
        ).all()
        return [
            {
                "materia":     r.materia,
                "professor":   r.professor or "—",
                "faltas":      r.faltas,
                "max_faltas":  r.max_faltas,
                "data_p1":     r.data_p1,
                "data_p2":     r.data_p2,
                "data_final":  r.data_final,
                "observacoes": r.observacoes or "",
            }
            for r in rows
        ]


@st.cache_data(ttl=60)
def get_saude() -> list[dict]:
    with get_session() as session:
        rows = session.exec(
            select(Saude_Nutricao).order_by(
                Saude_Nutricao.data_registro.desc(),
                Saude_Nutricao.refeicao,
            )
        ).all()
        return [
            {
                "data_registro": r.data_registro,
                "refeicao":      _enum_str(r.refeicao),
                "alimento":      r.alimento,
                "quantidade_g":  r.quantidade_g,
                "calorias":      r.calorias,
                "carboidratos":  r.carboidratos,
                "proteinas":     r.proteinas,
                "gorduras":      r.gorduras,
            }
            for r in rows
        ]


# ── AI Chief of Staff — context + renderer ────────────────────────────────────

@st.cache_data(ttl=60)
def get_briefing_context() -> dict:
    """Coleta um resumo tático do banco para alimentar a IA do Chief of Staff.

    TTL de 60 s (alinhado com as outras queries) para refletir mudanças
    recentes sem sobrecarregar o DB.
    """
    with get_session() as session:
        # ── Patrimônio base (custo em USD, sem preço ao vivo para evitar I/O) ─
        inv_rows    = session.exec(select(Fin_Investimento)).all()
        patrimonio  = sum(
            float(r.quantidade * r.preco_medio_usd) for r in inv_rows
        )

        # ── Projetos P0 Critical ──────────────────────────────────────────────
        proj_all    = session.exec(select(Work_Projeto)).all()
        p0_items    = [
            p for p in proj_all
            if p.prioridade == PrioridadeEnum.p0_critical
        ]
        blocked_items = [p for p in proj_all if _enum_str(p.status) == "Blocked"]

        # ── Faculdade em zona de risco (faltas ≥ 80 % do máximo) ─────────────
        fac_all     = session.exec(select(Faculdade)).all()
        risco_items = [
            m for m in fac_all
            if m.max_faltas > 0 and m.faltas >= m.max_faltas * 0.8
        ]

    return {
        "data_do_briefing":               date.today().strftime("%d/%m/%Y"),
        "patrimônio_base_usd":            f"$ {patrimonio:,.2f}",
        "total_projetos_ativos":          len(proj_all),
        "projetos_P0_Critical":           len(p0_items),
        "detalhes_P0": [
            f"{p.projeto.value}: {p.demanda[:70]}" for p in p0_items
        ],
        "projetos_bloqueados":            len(blocked_items),
        "detalhes_blocked": [
            f"{p.projeto.value}: {p.demanda[:70]}" for p in blocked_items
        ],
        "matérias_em_zona_de_risco":      len(risco_items),
        "detalhes_risco_faculdade": [
            f"{m.materia}: {m.faltas}/{m.max_faltas} faltas "
            f"({int(m.faltas / m.max_faltas * 100)}%)"
            for m in risco_items
        ],
    }


import logging as _logging  # noqa: E402 — necessário após imports de módulo
_log = _logging.getLogger(__name__)


def _render_chief_of_staff() -> None:
    """Renderiza o Daily Briefing da IA no topo do Command Center."""
    try:
        ctx           = get_briefing_context()
        briefing_text = briefing_service.generate_executive_briefing(ctx)
    except Exception as exc:
        _log.warning("Chief of Staff: fallback ativado — %s", exc)
        briefing_text = "_Briefing indisponível no momento._"

    with st.expander("♟️ AI Chief of Staff — Daily Briefing", expanded=True):
        st.markdown(
            '<div style="'
            "border-left: 3px solid #00d4aa;"
            "padding: 0.6rem 0 0.6rem 1.2rem;"
            "background: linear-gradient(90deg, #060f0c 0%, transparent 100%);"
            "border-radius: 0 6px 6px 0;"
            '">',
            unsafe_allow_html=True,
        )
        st.markdown(briefing_text)
        st.markdown("</div>", unsafe_allow_html=True)
        st.caption(
            f"🤖 Gemini 2.5 Flash  ·  Cache 1 h  ·  "
            f"Contexto coletado em: {date.today().strftime('%d/%m/%Y')}"
        )


# ── Project Graph helpers — Cyberpunk / Hedge Fund Terminal ───────────────────

# Fonte monoespacada com outline preto: legível em qualquer cor de fundo.
_TERMINAL_FONT: dict = {
    "color":       "#FFFFFF",
    "size":        14,
    "face":        "courier",
    "strokeWidth": 2,
    "strokeColor": "#000000",
}

# Sombra projetada em todos os nós para depth visual.
_NODE_SHADOW: dict = {
    "enabled": True,
    "color":   "rgba(0, 0, 0, 0.90)",
    "x":       5,
    "y":       5,
    "size":    12,
}

# Catálogo completo de projetos: EmpresaEnum.value → propriedades do nó vis.js.
_EMPRESA_CFG: dict[str, dict] = {
    # ── Web 2 ─────────────────────────────────────────────────────────────────
    "Baker Hughes": {
        "id":          "BAKER_HUGHES",
        "hub":         "WEB2",
        "shape":       "triangle",
        "color":       {
            "background": "#006400",
            "border":     "#00FF00",
            "highlight":  {"background": "#007a00", "border": "#00FF00"},
        },
        "borderWidth": 2,
        "size":        35,
        "title":       "Baker Hughes · Oil & Gas · Web2",
    },
    # ── Crypto ────────────────────────────────────────────────────────────────
    "Galton & Xend": {
        "id":          "GALTON_XEND",
        "hub":         "CRYPTO",
        "shape":       "diamond",
        "color":       {
            "background": "#000000",
            "border":     "#FFD700",
            "highlight":  {"background": "#111111", "border": "#FFD700"},
        },
        "borderWidth": 4,
        "size":        40,
        "title":       "Galton & Xend · DeFi / Exchange · Destaque Principal",
    },
    "Bee On Crypto": {
        "id":          "BEE_ON_CRYPTO",
        "hub":         "CRYPTO",
        "shape":       "hexagon",
        "color":       {
            "background": "#FF8C00",
            "border":     "#FFFFFF",
            "highlight":  {"background": "#FFA500", "border": "#FFFFFF"},
        },
        "borderWidth": 2,
        "size":        30,
        "title":       "Bee On Crypto · Content & Growth",
    },
    "Joina/Chainvite": {
        "id":          "JOINA_CHAINVITE",
        "hub":         "CRYPTO",
        "shape":       "hexagon",
        "color":       {
            "background": "#800080",
            "border":     "#FFFFFF",
            "highlight":  {"background": "#9900aa", "border": "#FFFFFF"},
        },
        "borderWidth": 2,
        "size":        25,
        "title":       "Joina / Chainvite · Web3 Tooling",
    },
    "Northfi": {
        "id":          "NORTHFI",
        "hub":         "CRYPTO",
        "shape":       "hexagon",
        "color":       {
            "background": "#0000CD",
            "border":     "#FFFFFF",
            "highlight":  {"background": "#0000EE", "border": "#FFFFFF"},
        },
        "borderWidth": 2,
        "size":        25,
        "title":       "Northfi · DeFi Protocol",
    },
    "DFB": {
        "id":          "DFB",
        "hub":         "CRYPTO",
        "shape":       "hexagon",
        "color":       {
            "background": "#696969",
            "border":     "#FFFFFF",
            "highlight":  {"background": "#808080", "border": "#FFFFFF"},
        },
        "borderWidth": 1,
        "size":        20,
        "title":       "DFB",
    },
}

# Cor das arestas hub → projeto (padrão por hub, com override por nó).
_HUB_EDGE_COLOR: dict[str, str] = {
    "WEB2":   "#00CC44",
    "CRYPTO": "#A020F0",
}
_NODE_EDGE_COLOR: dict[str, str] = {
    "GALTON_XEND":    "#FFD700",
    "BEE_ON_CRYPTO":  "#FF8C00",
    "JOINA_CHAINVITE": "#CC00CC",
    "NORTHFI":        "#3333FF",
    "DFB":            "#999999",
    "BAKER_HUGHES":   "#00FF00",
}


def _build_project_nodes(
    empresa_counts: dict[str, int],
) -> tuple[list, list]:
    """Constrói nós e arestas do grafo Cyberpunk Terminal.

    Layout ancorado no espaço (fixed=True nos hubs):
        EU (0, 0)  ─ dashed ─→  WEB2  (-300, 0)  ──→  Baker Hughes   [triangle]
                   └─ dashed ─→  CRYPTO (+300, 0) ──→  Galton & Xend  [diamond]
                                                   ──→  Bee On Crypto  [hexagon]
                                                   ──→  Joina/Chainvite[hexagon]
                                                   ──→  Northfi        [hexagon]
                                                   ──→  DFB            [hexagon]

    Os nós de projeto orbitam livremente; labels exibem contagem de tarefas.
    """
    if not _AGRAPH_OK:
        return [], []

    def _label(display: str, count: int) -> str:
        return f"{display}\n[ {count}t ]" if count else display

    # ── Nós estruturais — posição travada no espaço ───────────────────────────
    nodes: list[Node] = [
        Node(
            id="EU",
            label="[ CORE ]\nO Eu",
            shape="star",
            size=45,
            color={
                "background": "#FFFFFF",
                "border":     "#00d4aa",
                "highlight":  {"background": "#e8e8e8", "border": "#00d4aa"},
            },
            borderWidth=2,
            font={**_TERMINAL_FONT, "color": "#111111", "strokeColor": "#cccccc"},
            shadow=_NODE_SHADOW,
            fixed={"x": True, "y": True},
            x=0,
            y=0,
            title="CORE — Life OS Command Center",
        ),
        Node(
            id="WEB2",
            label="WEB 2",
            shape="hexagon",
            size=30,
            color={
                "background": "#1A1A1A",
                "border":     "#00FF00",
                "highlight":  {"background": "#2a2a2a", "border": "#00FF00"},
            },
            borderWidth=2,
            font=_TERMINAL_FONT,
            shadow=_NODE_SHADOW,
            fixed={"x": True, "y": True},
            x=-300,
            y=0,
            title="Hub Web 2 Tradicional",
        ),
        Node(
            id="CRYPTO",
            label="CRYPTO",
            shape="hexagon",
            size=30,
            color={
                "background": "#1A1A1A",
                "border":     "#A020F0",
                "highlight":  {"background": "#2a2a2a", "border": "#A020F0"},
            },
            borderWidth=2,
            font=_TERMINAL_FONT,
            shadow=_NODE_SHADOW,
            fixed={"x": True, "y": True},
            x=300,
            y=0,
            title="Hub Ecossistema Crypto / Web3",
        ),
    ]

    # ── Arestas estruturais — dashed, espessas ────────────────────────────────
    edges: list[Edge] = [
        Edge(source="EU", target="WEB2",   color="#555555", width=3, dashes=True),
        Edge(source="EU", target="CRYPTO", color="#555555", width=3, dashes=True),
    ]

    # ── Nós de projeto — flutuantes, orbitando os hubs ────────────────────────
    for empresa_value, cfg in _EMPRESA_CFG.items():
        count   = empresa_counts.get(empresa_value, 0)
        node_id = cfg["id"]
        hub     = cfg["hub"]

        nodes.append(Node(
            id=node_id,
            label=_label(empresa_value, count),
            shape=cfg["shape"],
            size=cfg["size"],
            color=cfg["color"],
            borderWidth=cfg["borderWidth"],
            font=_TERMINAL_FONT,
            shadow=_NODE_SHADOW,
            title=cfg["title"],
        ))

        edge_color = _NODE_EDGE_COLOR.get(node_id, _HUB_EDGE_COLOR[hub])
        edges.append(Edge(
            source=hub,
            target=node_id,
            color=edge_color,
            width=3 if count > 0 else 2,
        ))

    return nodes, edges


# ── Tab: Finanças ──────────────────────────────────────────────────────────────

def _render_financas() -> None:
    # ── Portfolio Section ─────────────────────────────────────────────────────
    st.markdown(
        '<p class="section-label">📊 Carteira & PnL em Tempo Real</p>',
        unsafe_allow_html=True,
    )

    inv = get_investimentos()
    if not inv:
        st.info("Nenhuma posição de investimento registrada ainda.")
    else:
        # Busca preços ao vivo (cache 5 min)
        ticker_info = tuple((r["ticker"], r["tipo_ativo"]) for r in inv)
        live_prices = finance_service.get_live_prices(ticker_info)

        # ── Cálculos com Decimal — nunca float ──
        total_custo  = Decimal("0")
        total_atual  = Decimal("0")
        tipo_valores: dict[str, Decimal] = {}
        rows_disp:    list[dict] = []
        treemap_rows: list[dict] = []   # alimenta o heatmap do portfolio

        for r in inv:
            pm:  Decimal = r["preco_medio_usd"]
            qty: Decimal = r["quantidade"]
            tipo = r["tipo_ativo"]
            raw_price = live_prices.get(r["ticker"], 0.0)
            preco_atual = Decimal(str(raw_price))
            has_price = raw_price > 0

            custo      = pm * qty
            valor_at   = preco_atual * qty if has_price else Decimal("0")
            pnl        = valor_at - custo  if has_price else Decimal("0")
            pnl_pct    = (
                (pnl / custo * 100).quantize(Decimal("0.01"))
                if has_price and custo > 0 else Decimal("0")
            )

            total_custo += custo
            if has_price:
                total_atual += valor_at
                tipo_valores[tipo] = tipo_valores.get(tipo, Decimal("0")) + valor_at

            is_crypto = tipo == "Crypto"
            rows_disp.append({
                "Ticker":      r["ticker"],
                "Tipo":        tipo,
                "Qtd":         str(qty.normalize()),
                "PM (USD)":    _usd(pm, 8 if is_crypto else 2),
                "Atual (USD)": _usd(preco_atual, 8 if is_crypto else 2) if has_price else "—",
                "Custo":       _usd(custo),
                "Valor Atual": _usd(valor_at) if has_price else "—",
                "PnL":         _usd(pnl, signed=True) if has_price else "—",
                "PnL %":       f"{pnl_pct:+.2f}%" if has_price else "—",
                "Carteira":    r["carteira"],
            })
            # ── Treemap row (float apenas para Plotly) ──
            if has_price and float(valor_at) > 0:
                treemap_rows.append({
                    "Tipo Ativo": tipo,
                    "Ticker":     r["ticker"],
                    "Valor":      float(valor_at),
                    "PnL %":      float(pnl_pct),
                })

        total_pnl = total_atual - total_custo
        total_pnl_pct = (
            (total_pnl / total_custo * 100).quantize(Decimal("0.01"))
            if total_custo > 0 else Decimal("0")
        )
        pnl_delta_str = f"{_usd(total_pnl, signed=True)} ({total_pnl_pct:+.2f}%)"

        # ── Métricas ──
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Posições", len(inv))
        c2.metric("Custo Total (USD)",  _usd(total_custo))
        c3.metric(
            "Valor Atual (USD)",
            _usd(total_atual) if total_atual > 0 else "—",
            delta=pnl_delta_str,
            delta_color="normal" if total_pnl >= 0 else "inverse",
        )
        c4.metric(
            "PnL Total (USD)",
            _usd(total_pnl, signed=True),
            delta=f"{total_pnl_pct:+.2f}%",
            delta_color="normal" if total_pnl >= 0 else "inverse",
        )

        st.markdown("")
        col_tbl, col_chart = st.columns([3, 2])

        with col_tbl:
            df_inv = pd.DataFrame(rows_disp)
            styled = df_inv.style.apply(
                _style_pnl_col, subset=["PnL", "PnL %"]
            )
            st.dataframe(
                styled,
                use_container_width=True,
                hide_index=True,
                height=min(38 * len(rows_disp) + 42, 500),
            )
            st.caption(
                "⚡ Preços via Yahoo Finance · cache 5 min · "
                "Crypto em USD · Ações em moeda nativa"
            )

        with col_chart:
            if treemap_rows:
                fig_tm = px.treemap(
                    pd.DataFrame(treemap_rows),
                    # Hierarquia: root → Tipo Ativo → Ticker
                    path=[px.Constant("Portfolio"), "Tipo Ativo", "Ticker"],
                    values="Valor",
                    color="PnL %",
                    # Escala Bloomberg: vermelho (perda) → escuro (zero) → teal (ganho)
                    color_continuous_scale=[
                        "#8B0000", "#2a0808", "#111111", "#083a1a", "#00a878",
                    ],
                    color_continuous_midpoint=0,
                    title="Portfolio Exposure Map — Live PnL Heatmap",
                )
                fig_tm.update_layout(**{
                    **_CHART_LAYOUT,
                    "margin": dict(t=44, b=4, l=4, r=4),
                    "coloraxis_colorbar": dict(
                        title="PnL %",
                        tickcolor="#444",
                        tickfont=dict(color="#555", size=10),
                        len=0.8,
                    ),
                })
                fig_tm.update_traces(
                    texttemplate="<b>%{label}</b><br>$ %{value:,.2f}",
                    textfont=dict(size=11, color="#ffffff"),
                    hovertemplate=(
                        "<b>%{label}</b><br>"
                        "Valor: $ %{value:,.2f}<br>"
                        "PnL: %{color:.2f}%"
                        "<extra></extra>"
                    ),
                )
                st.plotly_chart(fig_tm, use_container_width=True)
                st.caption(
                    "🌡️ Tamanho = exposição USD  ·  "
                    "Cor = PnL %  (🟥 perda → ⬛ neutro → 🟩 ganho)"
                )

    st.divider()

    # ── Fluxo de Caixa ────────────────────────────────────────────────────────
    st.markdown(
        '<p class="section-label">💸 Fluxo de Caixa</p>', unsafe_allow_html=True
    )

    txs = get_transacoes()
    if not txs:
        st.info("Nenhuma transação financeira registrada ainda.")
        return

    hoje = date.today()
    mes_atual = (hoje.year, hoje.month)

    entradas_mes = sum(
        (t["valor"] for t in txs
         if isinstance(t["data_hora"], datetime)
         and (t["data_hora"].year, t["data_hora"].month) == mes_atual
         and t["tipo"] == "Entrada"),
        Decimal("0"),
    )
    saidas_mes = sum(
        (t["valor"] for t in txs
         if isinstance(t["data_hora"], datetime)
         and (t["data_hora"].year, t["data_hora"].month) == mes_atual
         and t["tipo"] == "Saida"),
        Decimal("0"),
    )
    saldo_mes = entradas_mes - saidas_mes

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entradas (mês)",   _brl(entradas_mes))
    c2.metric("Saídas (mês)",     _brl(saidas_mes))
    c3.metric(
        "Saldo (mês)",
        _brl(saldo_mes),
        delta=f"{_brl(saldo_mes)}",
        delta_color="normal" if saldo_mes >= 0 else "inverse",
    )
    c4.metric("Total Transações", len(txs))

    st.markdown("")

    monthly: dict[str, dict[str, Decimal]] = {}
    for t in txs:
        dt = t["data_hora"]
        if isinstance(dt, datetime):
            key = dt.strftime("%Y-%m")
            monthly.setdefault(key, {"Entrada": Decimal("0"), "Saida": Decimal("0")})
            monthly[key][t["tipo"]] += t["valor"]

    if monthly:
        chart_rows = [
            {"Mês": mes, "Tipo": tipo, "Valor": float(val)}
            for mes in sorted(monthly)
            for tipo, val in monthly[mes].items()
        ]
        fig_bar = px.bar(
            pd.DataFrame(chart_rows),
            x="Mês", y="Valor", color="Tipo",
            barmode="group",
            title="Entradas vs Saídas — Histórico Mensal",
            color_discrete_map={"Entrada": "#00d4aa", "Saida": "#ff4b4b"},
            labels={"Valor": "R$", "Mês": ""},
        )
        fig_bar.update_layout(**_CHART_LAYOUT)
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown(
        '<p class="section-label">Transações Recentes</p>', unsafe_allow_html=True
    )
    df_tx = pd.DataFrame(
        [
            {
                "Data/Hora":  (
                    t["data_hora"].strftime("%d/%m/%y %H:%M")
                    if isinstance(t["data_hora"], datetime) else "—"
                ),
                "Tipo":       t["tipo"],
                "Categoria":  t["categoria"],
                "Valor":      _brl(t["valor"]),
                "Conta":      t["conta"],
                "Descrição":  t["descricao"],
            }
            for t in txs[:30]
        ]
    )
    st.dataframe(df_tx, use_container_width=True, hide_index=True, height=300)


# ── Tab: Projetos — Knowledge Graph + Kanban Board ────────────────────────────

def _render_projetos() -> None:
    proj = get_projetos()

    # Defensive Enum coercion — segunda camada de blindagem
    for p in proj:
        for k in ("projeto", "prioridade", "status"):
            p[k] = p[k].value if hasattr(p[k], "value") else str(p[k])

    # ── Knowledge Graph ───────────────────────────────────────────────────────
    st.markdown(
        '<p class="section-label">🕸 Knowledge Graph — Ecossistema de Projetos</p>',
        unsafe_allow_html=True,
    )

    empresa_counts: dict[str, int] = {}
    for p in proj:
        empresa_counts[p["projeto"]] = empresa_counts.get(p["projeto"], 0) + 1

    if _AGRAPH_OK:
        g_nodes, g_edges = _build_project_nodes(empresa_counts)
        g_config = GraphConfig(
            width="100%",
            height=600,
            directed=True,
            # physics como dict é repassado diretamente ao vis.js Network options.
            # barnesHut: centralGravity baixo = hubs ficam ancorados no espaço;
            # springLength/springConstant controlam a órbita dos projetos.
            physics={
                "barnesHut": {
                    "centralGravity": 0.1,
                    "springLength":   150,
                    "springConstant": 0.05,
                    "damping":        0.09,
                }
            },
            hierarchical=False,
            bgcolor="#0a0a0a",
            nodeHighlightBehavior=True,
            link={"color": "#333333", "smooth": {"type": "curvedCW", "roundness": 0.2}},
        )
        agraph(nodes=g_nodes, edges=g_edges, config=g_config)
    else:
        st.warning(
            "**streamlit-agraph** não instalado. "
            "Execute `pip install streamlit-agraph` e reinicie o servidor."
        )

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    # CAMADA MICRO — Drill-Down por projeto
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("### 🗂️ Command Center: Execution")

    # Constantes de highlight (definidas uma vez, reutilizadas em todas as abas)
    _P0_VAL = PrioridadeEnum.p0_critical.value   # "P0 - Critical"
    _P1_VAL = PrioridadeEnum.p1_high.value        # "P1 - High"

    def _highlight_priority(row: pd.Series) -> list[str]:
        prio = row.get("Prioridade", "")
        if prio == _P0_VAL:
            return ["background-color:#2a0808; color:#ff6b6b"] * len(row)
        if prio == _P1_VAL:
            return ["background-color:#1f1200; color:#ffb84d"] * len(row)
        return [""] * len(row)

    # Uma aba por empresa — ordem canônica do Enum
    empresa_tabs = st.tabs([e.value for e in EmpresaEnum])

    for tab, empresa_enum in zip(empresa_tabs, EmpresaEnum):
        with tab:
            demandas = [p for p in proj if p["projeto"] == empresa_enum.value]

            # ── Empty state ───────────────────────────────────────────────────
            if not demandas:
                st.info(
                    f"O radar está limpo. "
                    f"Nenhuma demanda ativa para **{empresa_enum.value}**."
                )

            else:
                # ── KPIs ──────────────────────────────────────────────────────
                total      = len(demandas)
                criticas   = sum(
                    1 for p in demandas
                    if p["prioridade"] in (_P0_VAL, _P1_VAL)
                )
                bloqueadas = sum(
                    1 for p in demandas if p["status"] == "Blocked"
                )
                concluidas = sum(
                    1 for p in demandas if p["status"] == "Done"
                )

                kc1, kc2, kc3, kc4 = st.columns(4)
                kc1.metric("📋 Total Ativas",    total)
                kc2.metric("🔥 Críticas (P0/P1)", criticas)
                kc3.metric("🔒 Bloqueadas",        bloqueadas)
                kc4.metric("✅ Concluídas",         concluidas)

                st.markdown("")

                # ── Data Grid Tático ──────────────────────────────────────────
                df_proj = pd.DataFrame(
                    [
                        {
                            "Demanda":     p["demanda"],
                            "Prioridade":  p["prioridade"],
                            "Status":      p["status"],
                            "Deadline":    (
                                p["deadline"].strftime("%d/%m/%y %H:%M")
                                if isinstance(p.get("deadline"), datetime)
                                else "—"
                            ),
                            "Observações": p["observacoes"] or "",
                        }
                        for p in demandas
                    ]
                )

                styled = df_proj.style.apply(_highlight_priority, axis=1)
                st.dataframe(
                    styled,
                    use_container_width=True,
                    hide_index=True,
                )


# ── Tab: Faculdade ─────────────────────────────────────────────────────────────

def _render_faculdade() -> None:
    fac = get_faculdade()
    if not fac:
        st.info("Nenhuma matéria cadastrada ainda.")
        return

    # ── Progress bars por disciplina ─────────────────────────────────────────
    st.markdown(
        '<p class="section-label">📊 Risco de Reprovação por Disciplina</p>',
        unsafe_allow_html=True,
    )

    for m in fac:
        faltas  = m["faltas"]
        max_f   = m["max_faltas"]
        pct_raw = faltas / max_f if max_f else 0.0
        pct     = int(pct_raw * 100)

        if pct >= 100:
            badge, bar_val, bar_css = "🔴 REPROVADO", 1.0, "background-color:#ff4b4b!important"
        elif pct >= 75:
            badge, bar_val, bar_css = "🟠 CRÍTICO",   min(pct_raw, 1.0), ""
        elif pct >= 50:
            badge, bar_val, bar_css = "🟡 ATENÇÃO",   pct_raw, ""
        else:
            badge, bar_val, bar_css = "🟢 OK",         pct_raw, ""

        col_info, col_bar = st.columns([2, 3])
        with col_info:
            st.markdown(f"**{m['materia']}** &nbsp; {badge}", unsafe_allow_html=True)
            st.caption(f"👤 {m['professor']}  ·  🚫 {faltas}/{max_f} faltas")
            datas = []
            if m["data_p1"]:
                datas.append(f"P1: {m['data_p1'].strftime('%d/%m')}")
            if m["data_p2"]:
                datas.append(f"P2: {m['data_p2'].strftime('%d/%m')}")
            if m["data_final"]:
                datas.append(f"Final: {m['data_final'].strftime('%d/%m')}")
            if datas:
                st.caption("  ·  ".join(datas))
        with col_bar:
            if bar_css:
                # Inject override CSS for critical progress bar
                st.markdown(
                    f"<style>[data-testid='stProgressBar']>div>div>div"
                    f"{{background-color:#ff4b4b!important}}</style>",
                    unsafe_allow_html=True,
                )
            st.progress(bar_val, text=f"{pct}% das faltas consumidas")

        st.markdown("")

    st.divider()

    # ── Summary table ─────────────────────────────────────────────────────────
    st.markdown(
        '<p class="section-label">📋 Quadro Geral</p>', unsafe_allow_html=True
    )
    df = pd.DataFrame(
        [
            {
                "Matéria":     m["materia"],
                "Professor":   m["professor"],
                "Faltas":      f"{m['faltas']}/{m['max_faltas']}",
                "Risco":       f"{int(m['faltas']/m['max_faltas']*100) if m['max_faltas'] else 0}%",
                "P1":          m["data_p1"].strftime("%d/%m/%y")    if m["data_p1"]    else "—",
                "P2":          m["data_p2"].strftime("%d/%m/%y")    if m["data_p2"]    else "—",
                "Final":       m["data_final"].strftime("%d/%m/%y") if m["data_final"] else "—",
                "Observações": m["observacoes"],
            }
            for m in fac
        ]
    )
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # ── Grade semanal hardcoded (M1–T3 × Seg–Sex) ────────────────────────────
    st.markdown(
        '<p class="section-label">🗓 Grade Semanal — Semestre Atual</p>',
        unsafe_allow_html=True,
    )

    # Distribui matérias do banco nas células como placeholder visual
    materias = [m["materia"] for m in fac]
    grid: dict[str, list[str]] = {dia: ["—"] * len(_GRADE_HORARIOS) for dia in _GRADE_DIAS}

    # Preenchimento simples: aloca matérias em slots distribuídos
    for idx, m in enumerate(materias):
        slot = idx % len(_GRADE_HORARIOS)
        dia  = _GRADE_DIAS[idx % len(_GRADE_DIAS)]
        grid[dia][slot] = m[:20]  # trunca para caber na célula

    df_grade = pd.DataFrame(grid, index=_GRADE_HORARIOS)
    df_grade.index.name = "Período"

    st.dataframe(
        df_grade.style.set_properties(**{
            "background-color": "#111",
            "color":            "#888",
            "border-color":     "#1c1c1c",
            "font-size":        "0.82rem",
        }).set_table_styles([{
            "selector": "th",
            "props": [
                ("background-color", "#0a0a0a"),
                ("color", "#555"),
                ("font-size", "0.72rem"),
                ("letter-spacing", "0.08em"),
                ("text-transform", "uppercase"),
            ],
        }]),
        use_container_width=True,
    )
    st.caption(
        "💡 Grade gerada automaticamente com as matérias cadastradas. "
        "Edite os horários reais na v2 via endpoint de agenda."
    )


# ── Tab: Saúde ─────────────────────────────────────────────────────────────────

def _render_saude() -> None:
    saude = get_saude()
    if not saude:
        st.info("Nenhum registro nutricional cadastrado ainda.")
        return

    hoje = date.today()
    regs_hoje = [r for r in saude if r["data_registro"] == hoje]

    # ── Gauge de calorias ─────────────────────────────────────────────────────
    st.markdown(
        '<p class="section-label">🎯 Meta Calórica Diária</p>',
        unsafe_allow_html=True,
    )

    kcal_hoje = sum(r["calorias"] for r in regs_hoje)
    pct_meta  = min(kcal_hoje / _META_KCAL, 1.5)

    col_gauge, col_macros = st.columns([2, 3])

    with col_gauge:
        fig_gauge = go.Figure(
            go.Indicator(
                mode="gauge+number+delta",
                value=kcal_hoje,
                delta={
                    "reference":    _META_KCAL,
                    "valueformat":  ".0f",
                    "increasing":   {"color": "#ff4b4b"},
                    "decreasing":   {"color": "#00d4aa"},
                },
                title={
                    "text": f"Hoje  ·  Meta: {_META_KCAL} kcal",
                    "font": {"color": "#555", "size": 13},
                },
                number={"font": {"color": "#00d4aa", "size": 46}, "suffix": " kcal"},
                gauge={
                    "axis": {
                        "range": [0, _META_KCAL * 1.5],
                        "tickcolor":  "#2a2a2a",
                        "tickfont":   {"color": "#444", "size": 10},
                    },
                    "bar":         {"color": "#00d4aa", "thickness": 0.22},
                    "bgcolor":     "#0a0a0a",
                    "bordercolor": "#1c1c1c",
                    "borderwidth": 1,
                    "steps": [
                        {"range": [0,            _META_KCAL * 0.5], "color": "#111"},
                        {"range": [_META_KCAL * 0.5, _META_KCAL * 0.8], "color": "#141a14"},
                        {"range": [_META_KCAL * 0.8, _META_KCAL],       "color": "#182218"},
                        {"range": [_META_KCAL,   _META_KCAL * 1.5],     "color": "#1e1010"},
                    ],
                    "threshold": {
                        "line":      {"color": "#00d4aa", "width": 3},
                        "thickness": 0.82,
                        "value":     _META_KCAL,
                    },
                },
            )
        )
        fig_gauge.update_layout(
            paper_bgcolor="#0a0a0a",
            font_color="#888",
            height=300,
            margin=dict(t=50, b=20, l=40, r=40),
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

    with col_macros:
        st.markdown("")
        prot_hoje = sum((r["proteinas"]    for r in regs_hoje), Decimal("0"))
        carb_hoje = sum((r["carboidratos"] for r in regs_hoje), Decimal("0"))
        gord_hoje = sum((r["gorduras"]     for r in regs_hoje), Decimal("0"))

        cm1, cm2, cm3, cm4 = st.columns(4)
        cm1.metric("Calorias",     f"{kcal_hoje}")
        cm2.metric("Proteínas",    f"{prot_hoje:.1f}g")
        cm3.metric("Carboidratos", f"{carb_hoje:.1f}g")
        cm4.metric("Gorduras",     f"{gord_hoje:.1f}g")

        st.markdown("")
        faltam = _META_KCAL - kcal_hoje
        if faltam > 0:
            st.info(f"Faltam **{faltam} kcal** para atingir a meta de hoje.")
        elif faltam < 0:
            st.warning(f"Meta excedida em **{abs(faltam)} kcal**.")
        else:
            st.success("Meta calórica atingida exatamente! 🎯")

        st.progress(min(pct_meta, 1.0), text=f"{int(pct_meta * 100)}% da meta")

        if regs_hoje:
            st.markdown("")
            st.caption("Refeições registradas hoje")
            df_hoje = pd.DataFrame(
                [
                    {
                        "Refeição":  r["refeicao"],
                        "Alimento":  r["alimento"],
                        "Qtd (g)":   str(r["quantidade_g"].normalize()),
                        "kcal":      r["calorias"],
                        "Prot (g)":  f"{r['proteinas']:.1f}",
                        "Carbs (g)": f"{r['carboidratos']:.1f}",
                        "Gord (g)":  f"{r['gorduras']:.1f}",
                    }
                    for r in regs_hoje
                ]
            )
            st.dataframe(df_hoje, use_container_width=True, hide_index=True)

    st.divider()

    # ── Histórico calórico ────────────────────────────────────────────────────
    st.markdown(
        '<p class="section-label">📈 Histórico — 30 dias</p>',
        unsafe_allow_html=True,
    )

    daily_kcal: dict[date, int] = {}
    for r in saude:
        d = r["data_registro"]
        daily_kcal[d] = daily_kcal.get(d, 0) + r["calorias"]

    if daily_kcal:
        df_daily = (
            pd.DataFrame(sorted(daily_kcal.items()), columns=["Data", "Calorias"])
            .tail(30)
        )
        df_daily["Meta"] = _META_KCAL

        fig_hist = go.Figure()
        fig_hist.add_trace(go.Bar(
            x=df_daily["Data"], y=df_daily["Calorias"],
            name="Calorias",
            marker_color=[
                "#ff4b4b" if v > _META_KCAL else "#00d4aa"
                for v in df_daily["Calorias"]
            ],
            opacity=0.85,
        ))
        fig_hist.add_trace(go.Scatter(
            x=df_daily["Data"], y=df_daily["Meta"],
            name=f"Meta ({_META_KCAL} kcal)",
            line=dict(color="#555", dash="dash", width=1.5),
            mode="lines",
        ))
        fig_hist.update_layout(
            **{**_CHART_LAYOUT, "title": "Calorias Diárias vs Meta"},
            showlegend=True,
        )
        st.plotly_chart(fig_hist, use_container_width=True)

    # ── Macro split ───────────────────────────────────────────────────────────
    st.markdown(
        '<p class="section-label">🥩 Macro Split — Histórico Completo</p>',
        unsafe_allow_html=True,
    )

    total_p = sum((r["proteinas"]    for r in saude), Decimal("0"))
    total_c = sum((r["carboidratos"] for r in saude), Decimal("0"))
    total_g = sum((r["gorduras"]     for r in saude), Decimal("0"))
    total_m = total_p + total_c + total_g

    if total_m > 0:
        col_pie, col_stats = st.columns([1, 1])
        with col_pie:
            fig_macro = px.pie(
                pd.DataFrame({
                    "Macro": ["Proteínas", "Carboidratos", "Gorduras"],
                    "g":     [float(total_p), float(total_c), float(total_g)],
                }),
                names="Macro", values="g",
                hole=0.5,
                color_discrete_sequence=["#00d4aa", "#4dabf7", "#ff6b6b"],
            )
            fig_macro.update_layout(**{
                **_CHART_LAYOUT,
                "margin": dict(t=20, b=12, l=12, r=12),
            })
            st.plotly_chart(fig_macro, use_container_width=True)

        with col_stats:
            st.markdown("")
            pct_p = float(total_p / total_m * 100)
            pct_c = float(total_c / total_m * 100)
            pct_g = float(total_g / total_m * 100)
            st.metric("Proteínas",    f"{total_p:.0f}g", delta=f"{pct_p:.1f}%")
            st.metric("Carboidratos", f"{total_c:.0f}g", delta=f"{pct_c:.1f}%")
            st.metric("Gorduras",     f"{total_g:.0f}g", delta=f"{pct_g:.1f}%")
    else:
        st.info("Sem dados históricos de macros ainda.")


# ── Main layout ────────────────────────────────────────────────────────────────

def main() -> None:
    # ── Header ───────────────────────────────────────────────────────────────
    col_h, col_btn = st.columns([5, 1])
    with col_h:
        st.markdown("## ⚡ Life OS — Command Center")
        st.caption(
            "Read-only  ·  Data entry via Telegram IA  ·  "
            "DB cache: 60 s  ·  Market data: 5 min"
        )
    with col_btn:
        st.markdown("")
        if st.button(
            "🔄 Refresh",
            use_container_width=True,
            help="Limpa todo o cache e recarrega dados do banco e mercado",
        ):
            st.cache_data.clear()
            st.rerun()

    st.divider()

    # ── AI Chief of Staff — Daily Briefing (topo, antes das tabs) ────────────
    try:
        _render_chief_of_staff()
    except Exception as exc:
        st.warning(f"Chief of Staff indisponível: {exc}")

    st.markdown("")

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tabs = st.tabs(["🏦 Finanças", "⚙️ Projetos", "🎓 Faculdade", "🍎 Saúde"])

    for tab, renderer in zip(
        tabs,
        [_render_financas, _render_projetos, _render_faculdade, _render_saude],
    ):
        with tab:
            try:
                renderer()
            except Exception as exc:
                st.error(f"Erro ao renderizar aba: {exc}")
                st.exception(exc)


if __name__ == "__main__":
    main()
