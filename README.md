# Análise de Faturamento e Cluster de Projetos
 
Pipeline em 3 notebooks para tratar os dados de projetos de uma Empresa Júnior (EJ), projetar o faturamento futuro e simular o cluster institucional (1 a 5) com base nesses números.
 
## Visão geral do pipeline
 
```
Code_1.ipynb  →  Code_2.ipynb  →  Code_3.ipynb
(tratamento)     (previsão)       (avaliação de cluster)
```
 
Cada notebook lê a saída do anterior a partir da pasta `dados_tratados/`, então eles devem ser executados nessa ordem.
 
---
 
### `Code_1.ipynb` — Tratamento e exploração dos dados
 
- Lê as respostas de um formulário (Google Sheets, exportado como `.xlsx`) com os dados de cada projeto: área, responsável, cliente, valores (total, faturamento colaborativo, custo), se é projeto de impacto, datas de início/fim e status.
- Renomeia as colunas genéricas do formulário (`Coluna 1`, `Coluna 2`...) para nomes legíveis (`data_registro`, `nome_projeto`, `valor_total_projeto`...).
- Faz limpeza básica: conversão de tipos, remoção de espaços, checagem de duplicados e nulos.
- Cria colunas derivadas de data (`ano_inicio`, `mes_inicio`, `ano_mes_inicio`, `duracao_dias`).
- Gera o gráfico de faturamento mensal e acumulado comparado a uma meta anual (`META_ANUAL`).
- Agrega os dados por mês (`cluster_base`) e aplica `StandardScaler` para padronizar as variáveis numéricas.
### `Code_2.ipynb` — Previsão de faturamento
 
- Carrega `dados_tratados/projetos_tratados.csv` (saída tratada dos projetos).
- Monta uma série mensal de faturamento (total e colaborativo), preenchendo meses sem projetos com zero.
- Para cada métrica, compara duas abordagens — **baseline** (média móvel dos últimos meses) vs. **regressão linear** — usando holdout e MAE, e escolhe automaticamente a melhor.
- Gera a previsão dos próximos 6 meses com intervalo de confiança aproximado (~95%).
- Calcula a trajetória até a meta anual (`META_ANUAL` e `META_COLABORATIVA`): quanto já foi realizado, quanto é projetado para os meses restantes e o gap até a meta.
- Exporta `previsao_faturamento.csv` e `trajetoria_metas.json` para `dados_tratados/`.
### `Code_3.ipynb` — Avaliação de cluster institucional
 
- Carrega as saídas dos dois notebooks anteriores (`base_cluster_mensal.csv`, `projetos_tratados.csv`, `previsao_faturamento.csv`, `trajetoria_metas.json`).
- Implementa a fórmula oficial do índice de cluster:
```
  Índice = Faturamento × CSAT × (1 + %Engajamento MEJ) × (1 + %Faturamento Colaborativo) × 100
```
 
- Classifica o índice em um cluster de 1 a 5 conforme uma régua de faixas de valor, e aplica as 4 regras de negócio do regulamento:
  1. Faturamento zero no ano → cluster 1 automático.
  2. Cluster 5 exige ao menos um projeto de impacto no ano.
  3. Fora de conformidade com o Selo EJ → não sobe de cluster.
  4. Só é permitido subir 1 cluster por ano.
- Recalcula o cluster histórico (ano a ano) e projeta o cluster de fim de ano com base na previsão de faturamento do `Code_2`.
- Faz uma análise de sensibilidade do cluster projetado para diferentes cenários de engajamento no MEJ (40%, 70%, 75%, 90%).
- Gera recomendações automáticas (ex.: quanto falta faturar para alcançar o Cluster 5).
- Exporta `avaliacao_cluster_historico.csv`, `sensibilidade_engajamento_mej.csv` e `avaliacao_cluster_projetada.json`.
---

## Tecnologias
 
- Python 3.13
- pandas, numpy
- matplotlib, seaborn
- scikit-learn (`StandardScaler`, `LinearRegression`, `mean_absolute_error`)

### `app.py` — Dashboard interativo (Streamlit)
 
Aplicação Streamlit que consome **todos** os arquivos gerados pelos três notebooks e apresenta os resultados em um painel interativo, com 7 abas:
 
1. **📈 Faturamento** — histórico mensal, projeção e comparação com a meta linear.
2. **📅 2026 em Foco** — KPIs do ano de referência (realizado vs. projetado).
3. **🏆 Cluster & Sensibilidade** — evolução do índice de cluster ano a ano e a análise de sensibilidade ao % de engajamento com o MEJ.
4. **🧮 Calculadora de Cluster** — simulador "e se": o usuário ajusta faturamento, CSAT, % engajamento MEJ, % faturamento colaborativo e qtd. de projetos de impacto, e o app recalcula o índice e o cluster final em tempo real (reaproveitando as mesmas funções `calcular_indice_cluster` e `aplicar_regras_cluster` do `Code_3.ipynb`).
5. **🗓️ Histórico Multi-Ano** — compara o mesmo mês em anos diferentes (sazonalidade), com gráfico de linhas e mapa de calor por indicador.
6. **🗂️ Projetos** — tabela de projetos com filtros por área e status, CSAT por projeto (distinguindo explicitamente "não respondido" de zero) e faturamento por área.
7. **💡 Insights & Recomendações** — motor de insights totalmente calculado a partir dos dataframes (tendência do cluster, correlação entre % colaborativo e índice, alavancas necessárias para subir de cluster, sensibilidade ao engajamento MEJ, ritmo da meta, gap da meta colaborativa, taxa de resposta de CSAT e checagem do projeto de impacto), com recomendações derivadas 1:1 dos alertas disparados — nenhum texto fixo desacoplado dos números.
> ⚠️ **Nota**: o arquivo termina logo após o comentário `# TAB 8 — Pendências`, sem o bloco `with tab8:` correspondente (e a variável `tab8` nem chega a ser criada em `st.tabs(...)`, que hoje só define `tab1` a `tab7`). Essa aba parece ter ficado pela metade — é preciso completá-la (ou remover o comentário) antes de considerar o dashboard finalizado.
 
Além dos arquivos já listados na seção anterior, o `app.py` também espera um `metadados_execucao.json` em `dados_tratados/` (com pelo menos `executado_em` e `qtd_projetos`), usado no cabeçalho do dashboard — esse arquivo ainda não é exportado por nenhum dos três notebooks.
 
---
 
## Estrutura de pastas esperada
 
```
.
├── Code_1.ipynb
├── Code_2.ipynb
├── Code_3.ipynb
├── app.py
└── dados_tratados/
    ├── projetos_tratados.csv
    ├── base_cluster_mensal.csv
    ├── previsao_faturamento.csv
    ├── trajetoria_metas.json
    ├── avaliacao_cluster_historico.csv
    ├── sensibilidade_engajamento_mej.csv
    ├── avaliacao_cluster_projetada.json
    └── metadados_execucao.json
```
 
> ⚠️ **Nota**: o `Code_1.ipynb` atual lê os dados diretamente do Google Sheets e termina na etapa de padronização (`StandardScaler`), mas ainda não exporta os arquivos `projetos_tratados.csv` e `base_cluster_mensal.csv` que o `Code_2` e o `Code_3` esperam encontrar em `dados_tratados/`. Também é necessário garantir no tratamento colunas adicionais usadas mais adiante (`valor_faturamento_proprio`, `satisfacao`, `indice_tempo`). Vale adicionar essas etapas de exportação ao final do `Code_1` antes de rodar o pipeline completo.
 
## Parâmetros e premissas a confirmar
 
O `Code_3.ipynb` deixa explícitas algumas premissas que dependem de validação com a gestão da EJ antes da entrega final:
 
- `ENG_MEJ_PCT_ASSUMIDO` — percentual de engajamento com o MEJ (valor ilustrativo, ainda sem fonte de dados confirmada).
- `CLUSTER_ANTERIOR_CONHECIDO` — cluster oficial do ano anterior, a ser preenchido pela Direx.
- `SELO_EJ_EM_CONFORMIDADE` — conformidade com o Selo EJ, a confirmar com o gestor.
## Tecnologias
 
- Python 3.13
- pandas, numpy
- matplotlib, seaborn
- scikit-learn (`StandardScaler`, `LinearRegression`, `mean_absolute_error`)
- streamlit, plotly (dashboard)
## Como executar
 
1. Instale as dependências:
```bash
   pip install pandas numpy matplotlib seaborn scikit-learn openpyxl streamlit plotly
```
2. Execute os notebooks na ordem `Code_1 → Code_2 → Code_3`, garantindo que a pasta `dados_tratados/` seja criada e populada a cada etapa (ver nota acima sobre o `Code_1`, inclusive quanto ao `metadados_execucao.json`).
3. Rode o dashboard:
```bash
   streamlit run app.py
```
