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

