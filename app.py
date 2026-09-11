"""
Dashboard - Projeto Final DEX (EJ)
Faturamento, Cluster MEJ e Recomendações Personalizadas

Rodar com:
    streamlit run app.py
"""

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DATA_DIR = Path(__file__).parent / "dados_tratados"

# ----------------------------------------------------------------------
# Config da página
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="Dashboard DEX - Faturamento & Cluster",
    page_icon="📊",
    layout="wide",
)

CLUSTER_COLORS = {
    1: "#B0BEC5", 2: "#90A4AE", 3: "#42A5F5",
    4: "#66BB6A", 5: "#FFB300",
}

MESES_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
            "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

# ----------------------------------------------------------------------
# Regras oficiais de cluster (extraídas literalmente do Code_3.ipynb)
# ----------------------------------------------------------------------
REGUA_CLUSTER = [
    (0, 12_000_000, 1),
    (12_000_000.01, 24_000_000, 2),
    (24_000_000.01, 61_000_000, 3),
    (61_000_000.01, 130_000_000, 4),
    (130_000_000.01, float("inf"), 5),
]


def classificar_cluster(indice):
    for minimo, maximo, cluster in REGUA_CLUSTER:
        if minimo <= indice <= maximo:
            return cluster
    return None


def calcular_indice_cluster(faturamento, csat, eng_mej_pct, pct_faturamento_colaborativo):
    """Índice = Faturamento x CSAT x (1+%Eng.MEJ) x (1+%Fat.Colaborativo) x 100"""
    pct_faturamento_colaborativo = pct_faturamento_colaborativo or 0
    eng_mej_pct = eng_mej_pct or 0
    csat = csat or 0
    return faturamento * csat * (1 + eng_mej_pct) * (1 + pct_faturamento_colaborativo) * 100


def aplicar_regras_cluster(cluster_bruto, faturamento_ano, qtd_projetos_impacto_ano,
                            cluster_anterior=None, selo_ej_ok=True):
    """As 4 restrições oficiais do PDF, na ordem."""
    if faturamento_ano <= 0:
        return 1, ["faturamento_zero_no_ano -> rebaixado para Cluster 1"]

    cluster_final = cluster_bruto
    motivos = []

    if cluster_bruto == 5 and qtd_projetos_impacto_ano < 1:
        cluster_final = 4
        motivos.append("sem_projeto_de_impacto -> Cluster 5 travado em 4")

    if cluster_anterior is not None:
        if not selo_ej_ok and cluster_final > cluster_anterior:
            cluster_final = cluster_anterior
            motivos.append("selo_ej_fora_de_conformidade -> não sobe cluster")
        elif cluster_final > cluster_anterior + 1:
            cluster_final = cluster_anterior + 1
            motivos.append("subida_limitada_a_1_cluster_por_ano")

    return cluster_final, motivos


def limite_inferior_do_cluster(cluster):
    """Índice mínimo (régua oficial) para pertencer a um dado cluster."""
    for minimo, _, c in REGUA_CLUSTER:
        if c == cluster:
            return minimo
    return None


def fator_necessario(indice_atual, valor_atual, indice_alvo):
    """
    Isola um fator multiplicativo da fórmula do índice.
    indice_atual = outros_fatores * valor_atual  ->  outros_fatores = indice_atual / valor_atual
    valor_necessario = indice_alvo / outros_fatores
    Retorna None se o valor atual do fator for 0 (não dá pra isolar por divisão).
    """
    if valor_atual == 0:
        return None
    outros_fatores = indice_atual / valor_atual
    if outros_fatores == 0:
        return None
    return indice_alvo / outros_fatores


# ----------------------------------------------------------------------
# Motor de insights — tudo aqui é CALCULADO a partir dos dados carregados.
# Nenhuma conclusão (qual insight aparece, com qual severidade, com que
# número) é escrita à mão: é resultado de condicionais sobre os dataframes.
# ----------------------------------------------------------------------
def gerar_insights(hist_cluster, sensibilidade, avaliacao_proj, projetos,
                    fat_total_traj, fat_colab_traj, ano_ref, mes_atual):
    insights = []

    # 1) Tendência de cluster ano a ano — computada a partir dos deltas reais
    hc = hist_cluster.sort_values("ano")
    deltas = hc["cluster_final"].diff().dropna()
    if len(deltas) > 0:
        if (deltas < 0).all():
            direcao = "queda"
        elif (deltas > 0).all():
            direcao = "alta"
        elif (deltas == 0).all():
            direcao = "estável"
        else:
            direcao = "mista (sobe e desce)"
        ultimo_ano, penultimo_ano = hc.iloc[-1], hc.iloc[-2]
        insights.append({
            "titulo": "Tendência do índice de cluster",
            "nivel": "warning" if direcao == "queda" else ("success" if direcao == "alta" else "info"),
            "texto": (
                f"A trajetória {int(hc['ano'].min())}–{int(hc['ano'].max())} é de **{direcao}** "
                f"(Cluster {int(hc['cluster_final'].iloc[0])} → Cluster {int(hc['cluster_final'].iloc[-1])}). "
                f"De {int(penultimo_ano['ano'])} para {int(ultimo_ano['ano'])} o índice foi de "
                f"{penultimo_ano['indice_cluster']:,.0f} para {ultimo_ano['indice_cluster']:,.0f}."
            ),
        })

    # 2) Correlação entre % faturamento colaborativo e o índice de cluster —
    #    calculada de verdade (Pearson) sobre o histórico, não afirmada.
    if hist_cluster["pct_faturamento_colaborativo"].nunique() > 1:
        corr = hist_cluster["pct_faturamento_colaborativo"].corr(hist_cluster["indice_cluster"])
        colab_atual = avaliacao_proj["pct_faturamento_colaborativo"]
        colab_medio_hist = hist_cluster["pct_faturamento_colaborativo"].mean()
        if pd.notna(corr) and corr > 0.5 and colab_atual < colab_medio_hist:
            insights.append({
                "titulo": "% Faturamento colaborativo correlaciona com o índice",
                "nivel": "warning",
                "texto": (
                    f"A correlação histórica entre % colaborativo e índice de cluster é de "
                    f"**{corr:+.2f}**. A projeção atual usa {colab_atual:.0%} de faturamento "
                    f"colaborativo, abaixo da média histórica de {colab_medio_hist:.0%} — "
                    "esse é hoje o fator mais distante do seu próprio padrão histórico."
                ),
            })

    # 3) Alavancas para o próximo cluster — resolve a fórmula para cada fator
    #    isoladamente (faturamento, CSAT, engajamento, % colaborativo).
    cluster_atual = int(avaliacao_proj["cluster_final"])
    indice_atual = avaliacao_proj["indice_cluster"]
    if cluster_atual < 5:
        limite_alvo = limite_inferior_do_cluster(cluster_atual + 1)
        fat = avaliacao_proj["faturamento"]
        csat = avaliacao_proj["csat"]
        eng = avaliacao_proj["eng_mej_pct"]
        colab = avaliacao_proj["pct_faturamento_colaborativo"]

        fat_necessario = fator_necessario(indice_atual, fat, limite_alvo)
        csat_necessario = fator_necessario(indice_atual, csat, limite_alvo)
        eng_necessario = fator_necessario(indice_atual, 1 + eng, limite_alvo)
        colab_necessario = fator_necessario(indice_atual, 1 + colab, limite_alvo)

        alavancas = []
        if fat_necessario is not None:
            alavancas.append(("Faturamento", f"R$ {fat_necessario:,.0f}", f"(atual: R$ {fat:,.0f})", fat_necessario / fat if fat else None))
        if csat_necessario is not None and csat_necessario <= 5:
            alavancas.append(("CSAT", f"{csat_necessario:.2f}", f"(atual: {csat:.2f})", csat_necessario / csat if csat else None))
        if eng_necessario is not None and eng_necessario - 1 <= 1.0:
            alavancas.append(("% Engajamento MEJ", f"{(eng_necessario - 1):.0%}", f"(atual: {eng:.0%})", eng_necessario / (1 + eng)))
        if colab_necessario is not None and colab_necessario - 1 <= 1.0:
            alavancas.append(("% Fat. Colaborativo", f"{(colab_necessario - 1):.0%}", f"(atual: {colab:.0%})", colab_necessario / (1 + colab)))

        if alavancas:
            # ordena pela alavanca que exige o MENOR esforço relativo (menor múltiplo do valor atual)
            alavancas_validas = [a for a in alavancas if a[3] is not None]
            alavancas_validas.sort(key=lambda a: a[3])
            linhas = "\n".join(f"- **{nome}**: precisaria chegar a {valor} {ref}" for nome, valor, ref, _ in alavancas_validas)
            mais_facil = alavancas_validas[0][0] if alavancas_validas else None
            insights.append({
                "titulo": f"O que falta para o Cluster {cluster_atual + 1} (mantendo os demais fatores)",
                "nivel": "info",
                "texto": (
                    f"Isolando cada fator da fórmula (índice mínimo para Cluster {cluster_atual + 1}: "
                    f"{limite_alvo:,.0f}):\n\n{linhas}\n\n"
                    + (f"A alavanca que exige a menor mudança relativa é **{mais_facil}**." if mais_facil else "")
                ),
            })
        else:
            insights.append({
                "titulo": f"Cluster {cluster_atual + 1} fora de alcance isolando um único fator",
                "nivel": "warning",
                "texto": (
                    "Nenhum fator sozinho (dentro dos limites plausíveis — CSAT ≤ 5, "
                    "engajamento e % colaborativo ≤ 100%) fecha a conta para o próximo cluster "
                    "mantendo os demais fatores como estão. Seria necessária uma combinação de "
                    "melhorias em mais de um fator."
                ),
            })
    else:
        insights.append({
            "titulo": "Cluster máximo projetado",
            "nivel": "success",
            "texto": "A projeção atual já alcança o Cluster 5, o topo da régua oficial.",
        })

    # 4) Sensibilidade de engajamento MEJ — verifica se o cluster muda de fato
    #    dentro dos cenários simulados (não afirma isso, calcula).
    if sensibilidade["cluster_final"].nunique() == 1:
        insights.append({
            "titulo": "% Engajamento MEJ não decide o cluster neste momento",
            "nivel": "info",
            "texto": (
                f"Nos {len(sensibilidade)} cenários simulados (engajamento de "
                f"{sensibilidade['eng_mej_pct'].min():.0%} a {sensibilidade['eng_mej_pct'].max():.0%}), "
                f"o cluster final permaneceu **Cluster {int(sensibilidade['cluster_final'].iloc[0])}** em todos. "
                "O índice varia, mas não o suficiente para cruzar uma faixa da régua."
            ),
        })
    else:
        limiar = sensibilidade.loc[sensibilidade["cluster_final"] > sensibilidade["cluster_final"].min()].sort_values("eng_mej_pct").iloc[0]
        insights.append({
            "titulo": "% Engajamento MEJ pode decidir o cluster",
            "nivel": "warning",
            "texto": (
                f"A partir de {limiar['eng_mej_pct']:.0%} de engajamento, o cluster simulado sobe para "
                f"Cluster {int(limiar['cluster_final'])}. Vale confirmar o valor real com a Direx."
            ),
        })

    # 5) Ritmo linear da meta anual — sinal automático (atrás/à frente)
    meta_parcial = fat_total_traj["meta"] * mes_atual / 12
    realizado = fat_total_traj["realizado_ate_agora"]
    gap_ritmo = realizado - meta_parcial
    insights.append({
        "titulo": "Ritmo de faturamento vs. meta linear",
        "nivel": "success" if gap_ritmo >= 0 else "warning",
        "texto": (
            f"Até o mês {mes_atual}/{ano_ref}, o ritmo linear da meta anual esperaria "
            f"R$ {meta_parcial:,.0f} realizados; o valor real é R$ {realizado:,.0f} "
            f"({'à frente' if gap_ritmo >= 0 else 'atrás'} em R$ {abs(gap_ritmo):,.0f}). "
            + (
                f"A meta anual só se sustenta na projeção dos meses restantes "
                f"(R$ {fat_total_traj['projetado_meses_restantes']:,.0f})."
                if gap_ritmo < 0 else
                "O ritmo real já cobre a meta linear esperada até aqui."
            )
        ),
    })

    # 6) Faturamento colaborativo vs. meta própria — gap direto do JSON
    if fat_colab_traj["gap_para_meta"] > 0:
        pct_atingido = fat_colab_traj["total_projetado_ano"] / fat_colab_traj["meta"] if fat_colab_traj["meta"] else 0
        insights.append({
            "titulo": "Meta de faturamento colaborativo",
            "nivel": "warning" if pct_atingido < 0.5 else "info",
            "texto": (
                f"Projeção atual atinge {pct_atingido:.0%} da meta colaborativa "
                f"(R$ {fat_colab_traj['total_projetado_ano']:,.0f} de R$ {fat_colab_traj['meta']:,.0f}), "
                f"faltando R$ {fat_colab_traj['gap_para_meta']:,.0f}."
            ),
        })

    # 7) Taxa de resposta de CSAT no ano corrente — contagem real, não estimada
    projetos_ano = projetos[projetos["ano_inicio"] == ano_ref]
    if len(projetos_ano) > 0:
        nao_respondidos = int((~projetos_ano["csat_respondido"]).sum())
        total_ano = len(projetos_ano)
        if nao_respondidos > 0:
            concluidos_sem_csat = int(((~projetos_ano["csat_respondido"]) & (projetos_ano["status"] == "Concluído")).sum())
            insights.append({
                "titulo": "CSAT não respondido pelo cliente",
                "nivel": "warning",
                "texto": (
                    f"{nao_respondidos} de {total_ano} projetos de {ano_ref} ainda não têm resposta de "
                    f"satisfação do cliente"
                    + (f", incluindo {concluidos_sem_csat} já concluído(s)" if concluidos_sem_csat > 0 else "")
                    + f". A avaliação de cluster usa o fallback histórico "
                    f"({avaliacao_proj['csat']:.2f}) para preencher essa lacuna."
                ),
            })
        else:
            insights.append({
                "titulo": "CSAT do ano corrente",
                "nivel": "success",
                "texto": f"Todos os {total_ano} projetos de {ano_ref} já têm resposta de satisfação do cliente.",
            })

    # 8) Projeto de impacto — obrigatório para Cluster 5, checagem direta
    qtd_impacto = avaliacao_proj["qtd_projetos_impacto"]
    if qtd_impacto < 1:
        insights.append({
            "titulo": "Sem projeto de impacto no ano",
            "nivel": "warning",
            "texto": (
                "Nenhum projeto de impacto registrado no ano de referência. Isso trava o cluster em "
                "4 mesmo que o índice bruto calculado alcance a faixa do Cluster 5 (regra oficial)."
            ),
        })

    return insights


def gerar_recomendacoes(insights, parametros):
    """
    Recomendações derivadas 1:1 dos insights que de fato dispararam
    (nível warning), na ordem em que apareceram. Não há texto fixo
    desacoplado do que foi calculado acima.
    """
    mapa_recomendacao = [
        ("Tendência do índice de cluster",
         "Investigar a causa da queda de índice ano a ano antes de assumir que a projeção atual é suficiente."),
        ("% Faturamento colaborativo correlaciona com o índice",
         "Priorizar o fechamento de faturamento colaborativo — é o fator mais distante do seu próprio padrão histórico de anos com cluster mais alto."),
        ("O que falta para o Cluster",
         "Focar na alavanca de menor esforço relativo indicada acima, em vez de tentar mexer em tudo ao mesmo tempo."),
        ("fora de alcance isolando um único fator",
         "Planejar melhorias combinadas (não apenas um fator) para o próximo ciclo, já que nenhum fator isolado fecha a conta."),
        ("% Engajamento MEJ pode decidir o cluster",
         "Confirmar com a Direx o valor real de engajamento com o MEJ — ele pode mudar o cluster final."),
        ("Ritmo de faturamento vs. meta linear",
         "Acompanhar o ritmo mensal de perto, já que a meta anual depende da projeção dos meses restantes se comprovar."),
        ("Meta de faturamento colaborativo",
         "Buscar parcerias/projetos colaborativos ainda neste ano para reduzir o gap para a meta."),
        ("CSAT não respondido pelo cliente",
         "Cobrar ativamente a resposta de CSAT dos clientes de projetos concluídos, em vez de depender do fallback histórico."),
        ("Sem projeto de impacto no ano",
         "Garantir ao menos 1 projeto de impacto no ano — é pré-requisito formal para o Cluster 5."),
    ]

    recomendacoes = []
    for ins in insights:
        if ins["nivel"] != "warning":
            continue
        for chave, texto in mapa_recomendacao:
            if chave in ins["titulo"] and texto not in recomendacoes:
                recomendacoes.append(texto)
                break

    # Pendências institucionais sempre viram recomendação enquanto não resolvidas
    if parametros["cluster_anterior_conhecido"] is None:
        recomendacoes.append(
            "Confirmar o cluster oficial do ano anterior com a Direx — necessário para ativar a "
            "regra de subida máxima de 1 cluster por ano."
        )
    if not parametros["selo_ej_em_conformidade"]:
        recomendacoes.append("Regularizar o Selo EJ — enquanto fora de conformidade, o cluster não sobe.")

    return recomendacoes


# ----------------------------------------------------------------------
# Carregamento de dados (com cache)
# ----------------------------------------------------------------------
@st.cache_data
def load_all():
    def read_csv(name):
        path = DATA_DIR / name
        return pd.read_csv(path) if path.exists() else None

    def read_json(name):
        path = DATA_DIR / name
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    return {
        "previsao": read_csv("previsao_faturamento.csv"),
        "historico_cluster": read_csv("avaliacao_cluster_historico.csv"),
        "sensibilidade": read_csv("sensibilidade_engajamento_mej.csv"),
        "base_mensal": read_csv("base_cluster_mensal.csv"),
        "projetos": read_csv("projetos_tratados.csv"),
        "trajetoria": read_json("trajetoria_metas.json"),
        "cluster_projetado": read_json("avaliacao_cluster_projetada.json"),
        "metadados": read_json("metadados_execucao.json"),
    }


data = load_all()
missing = [k for k, v in data.items() if v is None]
if missing:
    st.error(
        "Não encontrei estes arquivos na pasta `data/` (coloque-os ao lado de "
        f"`app.py`): {', '.join(missing)}"
    )
    st.stop()

previsao = data["previsao"]
hist_cluster = data["historico_cluster"]
sensibilidade = data["sensibilidade"]
base_mensal = data["base_mensal"]
projetos = data["projetos"].copy()
trajetoria = data["trajetoria"]
cluster_proj = data["cluster_projetado"]
metadados = data["metadados"]

fat_total_traj = trajetoria["faturamento_total"]
fat_colab_traj = trajetoria["faturamento_colaborativo"]
avaliacao_proj = cluster_proj["avaliacao_projetada"]
parametros = cluster_proj["parametros_assumidos"]

ANO_REF = fat_total_traj["ano_referencia"]
MES_ATUAL = pd.to_datetime(metadados["executado_em"]).month

# CSAT: cliente pode não responder -> tratar NaN explicitamente em vez de esconder
projetos["csat_respondido"] = projetos["satisfacao"].notna()
projetos["satisfacao_exibicao"] = projetos["satisfacao"].apply(
    lambda x: f"{x:.1f}" if pd.notna(x) else "Não respondido"
)
taxa_resposta_geral = projetos["csat_respondido"].mean()

# ----------------------------------------------------------------------
# Header + KPIs
# ----------------------------------------------------------------------
st.title("📊 Faturamento & Cluster MEJ — Projeto Final DEX")
st.caption(
    f"Última execução do pipeline: {metadados['executado_em']}  •  "
    f"{metadados['qtd_projetos']} projetos analisados"
)

col1, col2, col3, col4, col5 = st.columns(5)

cluster_final_proj = int(avaliacao_proj["cluster_final"])

with col1:
    st.metric("Cluster projetado (fim de 2026)", f"Cluster {cluster_final_proj}")
with col2:
    delta_meta = fat_total_traj["total_projetado_ano"] - fat_total_traj["meta"]
    st.metric(
        "Faturamento total projetado 2026",
        f"R$ {fat_total_traj['total_projetado_ano']:,.0f}",
        f"{delta_meta:,.0f} vs meta",
    )
with col3:
    st.metric(
        "Faturamento colaborativo projetado",
        f"R$ {fat_colab_traj['total_projetado_ano']:,.0f}",
        f"-{fat_colab_traj['gap_para_meta']:,.0f} p/ meta",
        delta_color="inverse",
    )
with col4:
    st.metric(
        "CSAT usado na projeção",
        f"{avaliacao_proj['csat']:.2f}",
        help="Fallback histórico é usado quando o cliente ainda não respondeu a pesquisa de satisfação.",
    )
with col5:
    st.metric(
        "Taxa de resposta CSAT (geral)",
        f"{taxa_resposta_geral:.0%}",
        help="% de projetos em que o cliente efetivamente respondeu a pesquisa de satisfação.",
    )

st.divider()

tab1, tab2, tab3, tab4, tab5, tab6, tab7= st.tabs(
    [
        "📈 Faturamento",
        "📅 2026 em Foco",
        "🏆 Cluster & Sensibilidade",
        "🧮 Calculadora de Cluster",
        "🗓️ Histórico Multi-Ano",
        "🗂️ Projetos",
        "💡 Insights & Recomendações",
    ]
)

# ----------------------------------------------------------------------
# TAB 1 — Faturamento (histórico + projeção + meta linear)
# ----------------------------------------------------------------------
with tab1:
    st.subheader("Faturamento mensal — histórico e projeção")

    base_mensal_sorted = base_mensal.sort_values("ano_mes_inicio")
    prev_total = previsao[previsao["metrica"] == "faturamento_total"].sort_values("ano_mes")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=base_mensal_sorted["ano_mes_inicio"], y=base_mensal_sorted["faturamento_total"],
        name="Realizado", marker_color="#42A5F5",
    ))
    fig.add_trace(go.Scatter(
        x=prev_total["ano_mes"], y=prev_total["previsto"], name="Projetado",
        mode="lines+markers", line=dict(color="#FFB300", dash="dash"),
    ))
    fig.add_trace(go.Scatter(
        x=list(prev_total["ano_mes"]) + list(prev_total["ano_mes"][::-1]),
        y=list(prev_total["intervalo_superior"]) + list(prev_total["intervalo_inferior"][::-1]),
        fill="toself", fillcolor="rgba(255,179,0,0.15)",
        line=dict(color="rgba(255,255,255,0)"), name="Intervalo de confiança", hoverinfo="skip",
    ))
    fig.add_hline(
        y=fat_total_traj["meta"], line_dash="dot", line_color="red",
        annotation_text=f"Meta anual: R$ {fat_total_traj['meta']:,.0f}",
    )
    fig.update_layout(xaxis_title="Ano-mês", yaxis_title="Faturamento (R$)",
                       legend=dict(orientation="h", y=1.1), height=430)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("📐 Comparativo com a meta anual — trajetória linear")
    st.caption(
        "A linha pontilhada distribui a meta anual de forma linear mês a mês "
        "(meta ÷ 12 × mês). Comparamos o acumulado realizado + projetado do ano contra "
        "esse ritmo constante — se a barra ficar abaixo da linha, o ano está andando "
        "mais devagar do que o necessário para bater a meta no ritmo ideal."
    )

    bm_2026 = base_mensal_sorted[base_mensal_sorted["ano_mes_inicio"].str.startswith(str(ANO_REF))]
    fat_por_mes = {int(r["ano_mes_inicio"].split("-")[1]): r["faturamento_total"] for _, r in bm_2026.iterrows()}

    prev_2026 = prev_total[prev_total["ano_mes"].str.startswith(str(ANO_REF))]
    proj_por_mes = {int(r["ano_mes"].split("-")[1]): r["previsto"] for _, r in prev_2026.iterrows()}

    meses = list(range(1, 13))
    realizado_mensal = [fat_por_mes.get(m, 0.0) if m <= MES_ATUAL else 0.0 for m in meses]
    projetado_mensal = [proj_por_mes.get(m, 0.0) if m > MES_ATUAL else 0.0 for m in meses]
    combinado_mensal = [r + p for r, p in zip(realizado_mensal, projetado_mensal)]
    acumulado_combinado = pd.Series(combinado_mensal).cumsum()
    meta_linear = [fat_total_traj["meta"] * m / 12 for m in meses]

    fig_lin = go.Figure()
    fig_lin.add_trace(go.Bar(
        x=[MESES_PT[m - 1] for m in meses[:MES_ATUAL]],
        y=acumulado_combinado[:MES_ATUAL], name="Acumulado realizado", marker_color="#42A5F5",
    ))
    fig_lin.add_trace(go.Bar(
        x=[MESES_PT[m - 1] for m in meses[MES_ATUAL:]],
        y=acumulado_combinado[MES_ATUAL:], name="Acumulado projetado", marker_color="#FFB300",
    ))
    fig_lin.add_trace(go.Scatter(
        x=[MESES_PT[m - 1] for m in meses], y=meta_linear, name="Meta linear (ritmo ideal)",
        mode="lines+markers", line=dict(color="red", dash="dot"),
    ))
    fig_lin.update_layout(
        xaxis_title=f"Mês de {ANO_REF}", yaxis_title="Faturamento acumulado (R$)",
        legend=dict(orientation="h", y=1.15), height=420, barmode="stack",
    )
    st.plotly_chart(fig_lin, use_container_width=True)

    meta_parcial_ate_agora = fat_total_traj["meta"] * MES_ATUAL / 12
    gap_ritmo = fat_total_traj["realizado_ate_agora"] - meta_parcial_ate_agora
    c1, c2 = st.columns(2)
    c1.metric(f"Meta linear esperada até {MESES_PT[MES_ATUAL - 1]}", f"R$ {meta_parcial_ate_agora:,.0f}")
    c2.metric(
        "Realizado até agora vs ritmo linear",
        f"R$ {fat_total_traj['realizado_ate_agora']:,.0f}",
        f"{gap_ritmo:,.0f}",
        delta_color="normal" if gap_ritmo >= 0 else "inverse",
    )

# ----------------------------------------------------------------------
# TAB 2 — 2026 em Foco (série histórica voltada para o ano corrente)
# ----------------------------------------------------------------------
with tab2:
    st.subheader(f"Série mensal de {ANO_REF} — realizado vs. projetado")
    st.caption(
        f"Estamos em {MESES_PT[MES_ATUAL - 1]}/{ANO_REF}. Meses até aqui usam dado realizado; "
        "os meses seguintes usam a projeção do modelo (regressão linear ou média móvel, "
        "conforme menor erro — ver Code_2)."
    )

    df_2026 = pd.DataFrame({
        "mes": [MESES_PT[m - 1] for m in meses],
        "realizado": realizado_mensal,
        "projetado": projetado_mensal,
    })

    fig5 = go.Figure()
    fig5.add_trace(go.Bar(x=df_2026["mes"], y=df_2026["realizado"], name="Realizado", marker_color="#42A5F5"))
    fig5.add_trace(go.Bar(x=df_2026["mes"], y=df_2026["projetado"], name="Projetado", marker_color="#FFB300"))
    fig5.add_vline(x=MES_ATUAL - 0.5, line_dash="dash", line_color="gray",
                    annotation_text="hoje", annotation_position="top")
    fig5.update_layout(yaxis_title="Faturamento (R$)", height=420,
                        legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig5, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Meses com faturamento registrado", int((pd.Series(realizado_mensal) > 0).sum()))
    c2.metric("Meses sem nenhum projeto iniciado", int((pd.Series(realizado_mensal) == 0).sum()))
    c3.metric("Faturamento total do ano (real + projetado)", f"R$ {sum(combinado_mensal):,.0f}")

    st.dataframe(
        df_2026.assign(acumulado=acumulado_combinado.round(0)),
        use_container_width=True, hide_index=True,
    )

# ----------------------------------------------------------------------
# TAB 3 — Cluster & Sensibilidade
# ----------------------------------------------------------------------
with tab3:
    st.subheader("Evolução do cluster por ano")
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        x=hist_cluster["ano"].astype(str), y=hist_cluster["indice_cluster"],
        marker_color=[CLUSTER_COLORS.get(int(c), "#999") for c in hist_cluster["cluster_final"]],
        text=[f"Cluster {int(c)}" for c in hist_cluster["cluster_final"]], textposition="outside",
    ))
    fig2.update_layout(yaxis_title="Índice de cluster", xaxis_title="Ano", height=420, showlegend=False)
    st.plotly_chart(fig2, use_container_width=True)
    st.caption(
        "Barra de 2026 usa o índice real parcial do ano (histórico). A projeção de fim de "
        "ano (Cluster {}) está nos KPIs no topo da página.".format(cluster_final_proj)
    )

    st.subheader("Análise de sensibilidade — % Engajamento MEJ")
    fig3 = go.Figure()
    fig3.add_trace(go.Bar(
        x=sensibilidade["cenario_engajamento_mej"], y=sensibilidade["indice_cluster"],
        marker_color=[CLUSTER_COLORS.get(int(c), "#999") for c in sensibilidade["cluster_final"]],
        text=[f"Cluster {int(c)}" for c in sensibilidade["cluster_final"]], textposition="outside",
    ))
    fig3.update_layout(yaxis_title="Índice de cluster", xaxis_title="Cenário", height=400)
    st.plotly_chart(fig3, use_container_width=True)
    st.dataframe(sensibilidade, use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------
# TAB 4 — Calculadora de Cluster (nova, interativa)
# ----------------------------------------------------------------------
with tab4:
    st.subheader("🧮 Calculadora de Cluster")
    st.caption(
        "Usa a fórmula oficial do PDF do MEJ e as 4 regras de negócio aplicadas no Code_3.ipynb. "
        "Simule cenários e veja o cluster resultante em tempo real."
    )

    preset = st.radio(
        "Carregar cenário:", ["Personalizado", "Projeção 2026 do pipeline", "Exemplo do PDF (validação)"],
        horizontal=True,
    )
    if preset == "Projeção 2026 do pipeline":
        d_fat = float(avaliacao_proj["faturamento"])
        d_csat = float(avaliacao_proj["csat"])
        d_eng = float(avaliacao_proj["eng_mej_pct"]) * 100
        d_colab = float(avaliacao_proj["pct_faturamento_colaborativo"]) * 100
        d_impacto = int(avaliacao_proj["qtd_projetos_impacto"])
    elif preset == "Exemplo do PDF (validação)":
        d_fat, d_csat, d_eng, d_colab, d_impacto = 88000.0, 5.0, 70.0, 80.0, 1
    else:
        d_fat, d_csat, d_eng, d_colab, d_impacto = 88000.0, 4.6, 70.0, 0.0, 1

    c1, c2 = st.columns(2)
    with c1:
        faturamento_in = st.number_input("Faturamento no ano (R$)", min_value=0.0, value=d_fat, step=1000.0)
        csat_in = st.slider("CSAT médio (0 a 5)", 0.0, 5.0, d_csat, 0.1)
        eng_in = st.slider("% Engajamento com o MEJ", 0, 100, int(d_eng)) / 100
    with c2:
        colab_in = st.slider("% Faturamento colaborativo", 0, 100, int(d_colab)) / 100
        impacto_in = st.number_input("Qtd. de projetos de impacto no ano", min_value=0, value=d_impacto, step=1)
        usar_anterior = st.checkbox("Considerar cluster do ano anterior (regra de subida)")
        cluster_anterior_in = None
        if usar_anterior:
            cluster_anterior_in = st.selectbox("Cluster oficial do ano anterior", [1, 2, 3, 4, 5], index=3)
        selo_ok_in = st.checkbox("Selo EJ em conformidade", value=True)

    indice = calcular_indice_cluster(faturamento_in, csat_in, eng_in, colab_in)
    cluster_bruto = classificar_cluster(indice)
    cluster_final, motivos = aplicar_regras_cluster(
        cluster_bruto, faturamento_in, impacto_in, cluster_anterior_in, selo_ok_in
    )

    st.divider()
    r1, r2, r3 = st.columns(3)
    r1.metric("Índice calculado", f"{indice:,.0f}")
    r2.metric("Cluster bruto (só pela régua)", f"Cluster {cluster_bruto}" if cluster_bruto else "—")
    r3.metric("Cluster final (após regras)", f"Cluster {cluster_final}")

    if motivos:
        for m in motivos:
            st.warning(f"Regra aplicada: {m}")
    else:
        st.success("Nenhuma regra de ajuste alterou o cluster bruto.")

    with st.expander("Ver régua oficial de clusters"):
        regua_df = pd.DataFrame(REGUA_CLUSTER, columns=["mínimo", "máximo", "cluster"])
        st.dataframe(regua_df, use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------
# TAB 5 — Histórico Multi-Ano ("ativo" mensal ao longo dos anos)
# ----------------------------------------------------------------------
with tab5:
    st.subheader("🗓️ Histórico mensal ao longo dos anos")
    st.caption(
        "Compara o mesmo mês em anos diferentes, para enxergar sazonalidade e evolução ano a ano. "
        "Escolha qual indicador mensal quer comparar."
    )

    metrica_map = {
        "Faturamento total (R$)": "faturamento_total",
        "Faturamento colaborativo (R$)": "faturamento_colaborativo",
        "Qtd. de projetos iniciados": "qtd_projetos",
        "Qtd. de projetos de impacto": "qtd_projetos_impacto",
        "Qtd. de projetos concluídos": "qtd_projetos_concluidos",
    }
    metrica_escolhida = st.selectbox("Indicador", list(metrica_map.keys()))
    col_metrica = metrica_map[metrica_escolhida]

    bm = base_mensal.copy()
    bm[["ano", "mes"]] = bm["ano_mes_inicio"].str.split("-", expand=True).astype(int)
    bm["mes_nome"] = bm["mes"].apply(lambda m: MESES_PT[m - 1])

    pivot = bm.pivot_table(index="mes", columns="ano", values=col_metrica, aggfunc="sum", fill_value=0)
    pivot = pivot.reindex(range(1, 13), fill_value=0)
    pivot.index = MESES_PT

    fig6 = go.Figure()
    anos_disponiveis = sorted(bm["ano"].unique())
    palette = ["#B0BEC5", "#42A5F5", "#FFB300", "#66BB6A", "#EF5350"]
    for i, ano in enumerate(anos_disponiveis):
        fig6.add_trace(go.Scatter(
            x=pivot.index, y=pivot[ano], mode="lines+markers", name=str(ano),
            line=dict(color=palette[i % len(palette)]),
        ))
    fig6.update_layout(
        xaxis_title="Mês", yaxis_title=metrica_escolhida, height=430,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig6, use_container_width=True)

    st.markdown("**Mapa de calor (Ano x Mês)**")
    fig7 = go.Figure(data=go.Heatmap(
        z=pivot.T.values, x=pivot.index, y=[str(a) for a in pivot.columns],
        colorscale="Blues", colorbar=dict(title=metrica_escolhida),
    ))
    fig7.update_layout(height=280)
    st.plotly_chart(fig7, use_container_width=True)

    st.caption(
        "💡 Ajuste o indicador acima se 'histórico do ativo mensal' se referir a outra métrica "
        "específica do projeto — a estrutura do painel já está pronta para qualquer coluna numérica "
        "da base mensal."
    )

# ----------------------------------------------------------------------
# TAB 6 — Projetos
# ----------------------------------------------------------------------
with tab6:
    st.subheader("Projetos tratados")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        areas = ["Todas"] + sorted(projetos["area"].dropna().unique().tolist())
        area_sel = st.selectbox("Área", areas)
    with col_f2:
        status_opts = ["Todos"] + sorted(projetos["status"].dropna().unique().tolist())
        status_sel = st.selectbox("Status", status_opts)

    df_f = projetos.copy()
    if area_sel != "Todas":
        df_f = df_f[df_f["area"] == area_sel]
    if status_sel != "Todos":
        df_f = df_f[df_f["status"] == status_sel]

    st.dataframe(
        df_f[[
            "nome_projeto", "area", "responsavel", "cliente", "satisfacao_exibicao",
            "valor_total_projeto", "valor_faturamento_colaborativo",
            "valor_faturamento_proprio", "projeto_de_impacto", "status",
            "data_inicio", "data_fim",
        ]].rename(columns={"satisfacao_exibicao": "CSAT (cliente)"}),
        use_container_width=True, hide_index=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Projetos no filtro", len(df_f))
    c2.metric("Faturamento total no filtro", f"R$ {df_f['valor_total_projeto'].sum():,.0f}")
    c3.metric(
        "CSAT médio (só respondidos)",
        f"{df_f['satisfacao'].mean():.2f}" if df_f["satisfacao"].notna().any() else "— nenhuma resposta",
    )
    c4.metric("Taxa de resposta CSAT no filtro", f"{df_f['csat_respondido'].mean():.0%}" if len(df_f) else "—")

    if df_f["csat_respondido"].notna().any() and not df_f["csat_respondido"].all():
        st.info(
            "Alguns projetos ainda não têm resposta de CSAT do cliente — eles aparecem como "
            "'Não respondido' na tabela e são excluídos do cálculo da média (não tratados como zero)."
        )

    st.subheader("Faturamento por área")
    por_area = projetos.groupby("area")["valor_total_projeto"].sum().sort_values(ascending=False)
    fig4 = go.Figure(go.Bar(x=por_area.index, y=por_area.values, marker_color="#42A5F5"))
    fig4.update_layout(yaxis_title="Faturamento (R$)", height=380)
    st.plotly_chart(fig4, use_container_width=True)

# ----------------------------------------------------------------------
# TAB 7 — Insights & Recomendações
# ----------------------------------------------------------------------
with tab7:
    st.subheader("💡 Insights (gerados automaticamente a partir dos dados)")
    st.caption(
        "Cada bloco abaixo é resultado de uma condicional sobre os dataframes carregados — "
        "muda sozinho se você reexecutar o pipeline com números diferentes."
    )

    insights = gerar_insights(
        hist_cluster, sensibilidade, avaliacao_proj, projetos,
        fat_total_traj, fat_colab_traj, ANO_REF, MES_ATUAL,
    )

    nivel_para_widget = {"warning": st.warning, "success": st.success, "info": st.info}
    for ins in insights:
        with st.container(border=True):
            st.markdown(f"**{ins['titulo']}**")
            nivel_para_widget[ins["nivel"]](ins["texto"])

    st.subheader("✅ Recomendações (derivadas dos insights acima)")
    recomendacoes = gerar_recomendacoes(insights, parametros)
    if recomendacoes:
        for r in recomendacoes:
            st.markdown(f"- {r}")
    else:
        st.success("Nenhum alerta disparado pelos dados atuais — nada crítico a recomendar agora.")

# ----------------------------------------------------------------------
# TAB 8 — Pendências
# ----------------------------------------------------------------------