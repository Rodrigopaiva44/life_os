"""
presentation/app.py
====================
Life OS — Command Center (read-only dashboard).

Dados entram exclusivamente via Telegram / Motor Cognitivo (telegram_bot.py).
Este painel é para visualização, análise e monitoramento.

Para rodar a partir da raiz do projeto:
    streamlit run presentation/app.py
"""

import sys
from pathlib import Path

# Garante que o diretório raiz do projeto esteja no sys.path
# (necessário quando executado como `streamlit run presentation/app.py`)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlmodel import select

from domain.models import (
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

# ── Hedge Fund dark theme — CSS injection ─────────────────────────────────────
st.markdown(
    """
<style>
/* Base */
[data-testid="stApp"] {
    background-color: #0d0d0d;
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
}
.block-container {
    padding-top: 1.5rem;
    padding-bottom: 3rem;
    max-width: 1440px;
}

/* Metric cards */
[data-testid="metric-container"] {
    background-color: #161616;
    border: 1px solid #242424;
    border-radius: 8px;
    padding: 1rem 1.25rem;
}
[data-testid="metric-container"] label {
    color: #666 !important;
    font-size: 0.70rem !important;
    font-weight: 600;
    letter-spacing: 0.10em;
    text-transform: uppercase;
}
[data-testid="stMetricValue"] {
    color: #00d4aa !important;
    font-size: 1.55rem !important;
    font-weight: 700 !important;
}
[data-testid="stMetricDelta"] { display: none; }

/* Tabs */
[data-baseweb="tab-list"] {
    gap: 0;
    border-bottom: 1px solid #1f1f1f;
}
[data-baseweb="tab"] {
    color: #555;
    font-weight: 500;
    letter-spacing: 0.03em;
    padding: 0.55rem 1.25rem;
    border-radius: 0;
}
[aria-selected="true"][data-baseweb="tab"] {
    color: #00d4aa !important;
    border-bottom: 2px solid #00d4aa !important;
    background-color: transparent !important;
}
[data-baseweb="tab-highlight"] { background-color: transparent !important; }

/* DataFrames */
[data-testid="stDataFrame"] {
    border: 1px solid #1f1f1f;
    border-radius: 8px;
    overflow: hidden;
}

/* Dividers */
hr { border-color: #1f1f1f !important; }

/* Progress bar fill */
[data-testid="stProgressBar"] > div > div > div {
    background-color: #00d4aa !important;
}

/* Alerts */
[data-testid="stAlert"] { border-radius: 6px; }

/* Section sub-headings */
.section-label {
    color: #555;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin: 1.5rem 0 0.75rem;
}
</style>
""",
    unsafe_allow_html=True,
)


# ── Formatadores de precisão (Decimal puro — nunca float) ─────────────────────

def _brl(value: Decimal) -> str:
    """Formata Decimal como R$ 1.234,56 — separador mil='.', decimal=','."""
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


def _usd(value: Decimal, decimals: int = 2) -> str:
    """Formata Decimal como $ 1,234.56 — separador mil=',', decimal='.'."""
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
    sign = "-" if value < 0 else ""
    return f"{sign}$ {''.join(reversed(out))}.{dec_str}"


def _enum_str(v: object) -> str:
    """Converte Enum (ou qualquer valor) para string de forma defensiva.

    Cobre três cenários possíveis retornados pelo ORM:
      1. Enum Python normal  → devolve .value  (ex: "Baker Hughes")
      2. String raw do DB    → devolve str(v)  (já é string, sem crash)
      3. Qualquer outro tipo → devolve str(v)  (safety net)
    """
    if hasattr(v, "value"):
        return str(v.value)
    return str(v) if v is not None else ""


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
                "tipo_ativo":      r.tipo_ativo.value,
                "quantidade":      r.quantidade,        # Decimal
                "preco_medio_usd": r.preco_medio_usd,   # Decimal
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
                "tipo":      r.tipo.value,
                "categoria": r.categoria,
                "valor":     r.valor,   # Decimal
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
                "refeicao":      r.refeicao.value,
                "alimento":      r.alimento,
                "quantidade_g":  r.quantidade_g,    # Decimal
                "calorias":      r.calorias,         # int
                "carboidratos":  r.carboidratos,     # Decimal
                "proteinas":     r.proteinas,        # Decimal
                "gorduras":      r.gorduras,         # Decimal
            }
            for r in rows
        ]


# ── Plotly layout base (dark, consistent) ─────────────────────────────────────

_CHART_LAYOUT = dict(
    paper_bgcolor="#161616",
    plot_bgcolor="#161616",
    font_color="#aaa",
    margin=dict(t=44, b=12, l=12, r=12),
    title_font=dict(color="#666", size=12),
    legend=dict(font=dict(color="#aaa"), bgcolor="rgba(0,0,0,0)"),
    xaxis=dict(gridcolor="#1f1f1f", linecolor="#1f1f1f"),
    yaxis=dict(gridcolor="#1f1f1f", linecolor="#1f1f1f"),
)


# ── Tab: Finanças ──────────────────────────────────────────────────────────────

def _render_financas() -> None:
    # ── Investimentos ─────────────────────────────────────────────────────────
    st.markdown('<p class="section-label">💼 Carteira de Investimentos</p>', unsafe_allow_html=True)

    inv = get_investimentos()
    if not inv:
        st.info("Nenhuma posição de investimento registrada ainda.")
    else:
        # ── Cálculos com Decimal ──
        total_usd = sum(
            (r["quantidade"] * r["preco_medio_usd"] for r in inv),
            Decimal("0"),
        )
        tipo_counts: dict[str, int] = {}
        rows_disp: list[dict] = []
        for r in inv:
            val_est = r["quantidade"] * r["preco_medio_usd"]
            tipo_counts[r["tipo_ativo"]] = tipo_counts.get(r["tipo_ativo"], 0) + 1
            rows_disp.append(
                {
                    "Ticker":      r["ticker"],
                    "Tipo":        r["tipo_ativo"],
                    "Quantidade":  str(r["quantidade"].normalize()),
                    "PM (USD)":    _usd(r["preco_medio_usd"], decimals=8),
                    "Valor Est.":  _usd(val_est, decimals=2),
                    "Carteira":    r["carteira"],
                    "Atualizado":  (
                        r["atualizado_em"].strftime("%d/%m/%y %H:%M")
                        if isinstance(r["atualizado_em"], datetime)
                        else "—"
                    ),
                }
            )

        tipo_dom = max(tipo_counts, key=lambda k: tipo_counts[k])

        c1, c2, c3 = st.columns(3)
        c1.metric("Posições Abertas", len(inv))
        c2.metric("Valor Est. Total (USD)", _usd(total_usd))
        c3.metric("Tipo Dominante", tipo_dom)

        st.markdown("")
        col_tbl, col_pie = st.columns([3, 2])

        with col_tbl:
            st.dataframe(
                pd.DataFrame(rows_disp),
                use_container_width=True,
                hide_index=True,
                height=min(38 * len(rows_disp) + 40, 440),
            )

        with col_pie:
            fig_pie = px.pie(
                pd.DataFrame(tipo_counts.items(), columns=["Tipo", "Posições"]),
                names="Tipo",
                values="Posições",
                title="Distribuição por Tipo de Ativo",
                color_discrete_sequence=px.colors.sequential.Teal,
                hole=0.45,
            )
            fig_pie.update_layout(**_CHART_LAYOUT)
            fig_pie.update_traces(textfont_color="#e2e2e2")
            st.plotly_chart(fig_pie, use_container_width=True)

    st.divider()

    # ── Fluxo de Caixa ────────────────────────────────────────────────────────
    st.markdown('<p class="section-label">💸 Fluxo de Caixa</p>', unsafe_allow_html=True)

    txs = get_transacoes()
    if not txs:
        st.info("Nenhuma transação registrada ainda.")
        return

    # Métricas do mês atual — Decimal puro
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
    c1.metric("Entradas (mês)",     _brl(entradas_mes))
    c2.metric("Saídas (mês)",       _brl(saidas_mes))
    c3.metric("Saldo (mês)",        _brl(saldo_mes))
    c4.metric("Total Transações",   len(txs))

    st.markdown("")

    # Agrupar por mês — Decimal para cálculo, float só na hora de plotar
    monthly: dict[str, dict[str, Decimal]] = {}
    for t in txs:
        dt = t["data_hora"]
        if isinstance(dt, datetime):
            key = dt.strftime("%Y-%m")
            monthly.setdefault(key, {"Entrada": Decimal("0"), "Saida": Decimal("0")})
            monthly[key][t["tipo"]] += t["valor"]

    if monthly:
        chart_rows = [
            {"Mês": mes, "Tipo": tipo, "Valor": float(val)}   # float apenas para Plotly
            for mes in sorted(monthly)
            for tipo, val in monthly[mes].items()
        ]
        fig_bar = px.bar(
            pd.DataFrame(chart_rows),
            x="Mês", y="Valor", color="Tipo",
            barmode="group",
            title="Entradas vs Saídas por Mês",
            color_discrete_map={"Entrada": "#00d4aa", "Saida": "#ff4b4b"},
            labels={"Valor": "R$", "Mês": ""},
        )
        fig_bar.update_layout(**_CHART_LAYOUT)
        st.plotly_chart(fig_bar, use_container_width=True)

    # Tabela das últimas 30 transações
    st.markdown('<p class="section-label">Transações Recentes</p>', unsafe_allow_html=True)
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


# ── Tab: Projetos ──────────────────────────────────────────────────────────────

def _render_projetos() -> None:
    proj = get_projetos()
    if not proj:
        st.info("Nenhum projeto ou tarefa registrada ainda.")
        return

    df_orig = pd.DataFrame(proj).rename(
        columns={
            "projeto":     "Empresa",
            "demanda":     "Demanda",
            "prioridade":  "Prioridade",
            "status":      "Status",
            "deadline":    "Deadline",
            "observacoes": "Observações",
        }
    )

    # Segunda camada de blindagem: garante que nenhum objeto Enum ou tipo
    # inesperado chegue ao Streamlit — cobre falhas de hidratação do ORM.
    for _col in ("Empresa", "Prioridade", "Status"):
        df_orig[_col] = df_orig[_col].apply(
            lambda x: x.value if hasattr(x, "value") else str(x)
        )

    # ── Filtros ───────────────────────────────────────────────────────────────
    f1, f2, f3 = st.columns(3)
    empresa_sel = f1.selectbox(
        "Empresa", ["Todas"] + sorted(df_orig["Empresa"].unique().tolist())
    )
    status_sel = f2.selectbox(
        "Status", ["Todos"] + sorted(df_orig["Status"].unique().tolist())
    )
    prio_sel = f3.selectbox(
        "Prioridade",
        ["Todas", "P0 - Critical", "P1 - High", "P2 - Medium", "P3 - Low"],
    )

    df = df_orig.copy()
    if empresa_sel != "Todas":
        df = df[df["Empresa"] == empresa_sel]
    if status_sel != "Todos":
        df = df[df["Status"] == status_sel]
    if prio_sel != "Todas":
        df = df[df["Prioridade"] == prio_sel]

    df["Deadline"] = df["Deadline"].apply(
        lambda x: x.strftime("%d/%m/%y %H:%M") if isinstance(x, datetime) else "—"
    )

    st.caption(f"{len(df)} tarefa(s) encontrada(s)")

    # ── Highlight P0/P1 ───────────────────────────────────────────────────────
    _P0 = PrioridadeEnum.p0_critical.value
    _P1 = PrioridadeEnum.p1_high.value

    def _highlight_row(row: pd.Series) -> list[str]:
        if row["Prioridade"] == _P0:
            return ["background-color: #2a0a0a; color: #ff6b6b"] * len(row)
        if row["Prioridade"] == _P1:
            return ["background-color: #1f1200; color: #ffb84d"] * len(row)
        return [""] * len(row)

    styled = df.style.apply(_highlight_row, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True, height=440)

    # ── Métricas de status ────────────────────────────────────────────────────
    st.divider()
    st.markdown('<p class="section-label">Distribuição por Status</p>', unsafe_allow_html=True)

    status_list = ["Backlog", "In Progress", "Review", "Done", "Blocked"]
    cols = st.columns(len(status_list))
    status_icons = {"Backlog": "📥", "In Progress": "⚙️", "Review": "🔍",
                    "Done": "✅", "Blocked": "🔒"}
    for col, s in zip(cols, status_list):
        count = int((df_orig["Status"] == s).sum())
        col.metric(f"{status_icons[s]} {s}", count)


# ── Tab: Faculdade ─────────────────────────────────────────────────────────────

def _render_faculdade() -> None:
    fac = get_faculdade()
    if not fac:
        st.info("Nenhuma matéria registrada ainda.")
        return

    st.markdown('<p class="section-label">📊 Risco de Reprovação por Disciplina</p>', unsafe_allow_html=True)

    for m in fac:
        faltas   = m["faltas"]
        max_f    = m["max_faltas"]
        pct_raw  = faltas / max_f if max_f else 0.0
        pct      = int(pct_raw * 100)

        if pct >= 100:
            badge, bar_pct = "🔴 REPROVADO", 1.0
        elif pct >= 75:
            badge, bar_pct = "🟠 CRÍTICO",   min(pct_raw, 1.0)
        elif pct >= 50:
            badge, bar_pct = "🟡 ATENÇÃO",   pct_raw
        else:
            badge, bar_pct = "🟢 OK",         pct_raw

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
            st.progress(bar_pct, text=f"{pct}% das faltas consumidas")

        st.markdown("")

    st.divider()

    # ── Tabela resumida ───────────────────────────────────────────────────────
    st.markdown('<p class="section-label">📋 Quadro Geral</p>', unsafe_allow_html=True)

    df = pd.DataFrame(
        [
            {
                "Matéria":     m["materia"],
                "Professor":   m["professor"],
                "Faltas":      f"{m['faltas']}/{m['max_faltas']}",
                "Risco %":     f"{int(m['faltas'] / m['max_faltas'] * 100) if m['max_faltas'] else 0}%",
                "P1":          m["data_p1"].strftime("%d/%m/%y")    if m["data_p1"]    else "—",
                "P2":          m["data_p2"].strftime("%d/%m/%y")    if m["data_p2"]    else "—",
                "Final":       m["data_final"].strftime("%d/%m/%y") if m["data_final"] else "—",
                "Observações": m["observacoes"],
            }
            for m in fac
        ]
    )
    st.dataframe(df, use_container_width=True, hide_index=True)


# ── Tab: Saúde ─────────────────────────────────────────────────────────────────

def _render_saude() -> None:
    saude = get_saude()
    if not saude:
        st.info("Nenhum registro nutricional ainda.")
        return

    hoje = date.today()
    regs_hoje = [r for r in saude if r["data_registro"] == hoje]

    # ── Métricas de hoje (Decimal puro) ───────────────────────────────────────
    st.markdown('<p class="section-label">📅 Hoje</p>', unsafe_allow_html=True)

    kcal_hoje = sum(r["calorias"]     for r in regs_hoje)
    prot_hoje = sum((r["proteinas"]   for r in regs_hoje), Decimal("0"))
    carb_hoje = sum((r["carboidratos"] for r in regs_hoje), Decimal("0"))
    gord_hoje = sum((r["gorduras"]    for r in regs_hoje), Decimal("0"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Calorias",     f"{kcal_hoje} kcal")
    c2.metric("Proteínas",    f"{prot_hoje:.1f} g")
    c3.metric("Carboidratos", f"{carb_hoje:.1f} g")
    c4.metric("Gorduras",     f"{gord_hoje:.1f} g")

    if regs_hoje:
        st.markdown("")
        st.caption("Refeições de hoje")
        df_hoje = pd.DataFrame(
            [
                {
                    "Refeição":      r["refeicao"],
                    "Alimento":      r["alimento"],
                    "Qtd (g)":       str(r["quantidade_g"].normalize()),
                    "Calorias":      r["calorias"],
                    "Proteínas (g)": f"{r['proteinas']:.1f}",
                    "Carbs (g)":     f"{r['carboidratos']:.1f}",
                    "Gorduras (g)":  f"{r['gorduras']:.1f}",
                }
                for r in regs_hoje
            ]
        )
        st.dataframe(df_hoje, use_container_width=True, hide_index=True)

    st.divider()

    # ── Histórico calórico diário (últimos 30 dias) ───────────────────────────
    st.markdown('<p class="section-label">📈 Histórico Calórico — 30 dias</p>', unsafe_allow_html=True)

    daily_kcal: dict[date, int] = {}
    for r in saude:
        d = r["data_registro"]
        daily_kcal[d] = daily_kcal.get(d, 0) + r["calorias"]

    if daily_kcal:
        df_daily = (
            pd.DataFrame(
                sorted(daily_kcal.items()), columns=["Data", "Calorias"]
            )
            .tail(30)
        )
        fig_cal = px.bar(
            df_daily,
            x="Data", y="Calorias",
            title="Calorias diárias",
            color="Calorias",
            color_continuous_scale="Teal",
            labels={"Calorias": "kcal", "Data": ""},
        )
        fig_cal.update_layout(**{**_CHART_LAYOUT, "coloraxis_showscale": False})
        st.plotly_chart(fig_cal, use_container_width=True)

    # ── Macro split geral ─────────────────────────────────────────────────────
    st.markdown('<p class="section-label">🥩 Macro Split — Histórico Completo</p>', unsafe_allow_html=True)

    total_p = sum((r["proteinas"]    for r in saude), Decimal("0"))
    total_c = sum((r["carboidratos"] for r in saude), Decimal("0"))
    total_g = sum((r["gorduras"]     for r in saude), Decimal("0"))
    total_m = total_p + total_c + total_g

    if total_m > 0:
        fig_macro = px.pie(
            pd.DataFrame({
                "Macro": ["Proteínas", "Carboidratos", "Gorduras"],
                "g":     [float(total_p), float(total_c), float(total_g)],  # float só para Plotly
            }),
            names="Macro", values="g",
            hole=0.45,
            color_discrete_sequence=["#00d4aa", "#4dabf7", "#ff6b6b"],
        )
        fig_macro.update_layout(**{**_CHART_LAYOUT, "margin": dict(t=20, b=12, l=12, r=12)})
        col_pie, _ = st.columns([1, 1])
        with col_pie:
            st.plotly_chart(fig_macro, use_container_width=True)


# ── Main layout ────────────────────────────────────────────────────────────────

def main() -> None:
    # ── Header ───────────────────────────────────────────────────────────────
    col_h, col_btn = st.columns([5, 1])
    with col_h:
        st.markdown("## ⚡ Life OS — Command Center")
        st.caption(
            "Dashboard read-only  ·  Data entry via Telegram IA  ·  "
            "Cache auto-refresh: 60 s"
        )
    with col_btn:
        st.markdown("")
        if st.button("🔄 Refresh", use_container_width=True,
                     help="Limpa o cache e recarrega dados do banco"):
            st.cache_data.clear()
            st.rerun()

    st.divider()

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tabs = st.tabs(["🏦 Finanças", "⚙️ Projetos", "🎓 Faculdade", "🍎 Saúde"])

    _TAB_RENDERERS = [_render_financas, _render_projetos, _render_faculdade, _render_saude]

    for tab, renderer in zip(tabs, _TAB_RENDERERS):
        with tab:
            try:
                renderer()
            except Exception as exc:
                st.error(f"Erro ao carregar dados: {exc}")
                st.exception(exc)


if __name__ == "__main__":
    main()
