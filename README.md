# Documentação Técnica — Pipeline de Telemetria e Análise de Risco na Esteira de Crédito

> Projeto de portfólio. Dados, nomes de tabelas, colunas e parceiros são **fictícios/adaptados**.

## 1. Visão Geral

Pipeline de ETL em Python responsável por extrair diariamente as propostas
de crédito (cartão co-branded / private label) de um sistema transacional
de origem, aplicar regras de classificação socioeconômica e consolidar os
dados em um Data Warehouse PostgreSQL, servindo de base para um dashboard
de BI de acompanhamento da esteira de crédito.

## 2. Problema de Negócio

A originação de crédito recebe propostas vindas de múltiplos canais
(autoatendimento, balcão de lojas, promotoras de venda). As etapas de
análise — pré-aprovação automática, mesa de crédito, checagem de fraude e
consulta a bureaus externos — ficam espalhadas em sistemas diferentes,
dificultando a visibilidade sobre gargalos, motivos de recusa e exposição
financeira gerada pelos limites concedidos.

## 3. Arquitetura

```
Sistema Transacional de Origem (SQL Server)
        │
        ▼
Extração incremental (Python / pandas)
        │
        ▼
Classificação (classe profissional / faixa de renda)
        │
        ▼
Staging — PostgreSQL (staging.fato_propostas_credito)
        │
        ▼
Tabela Analítica Diária — PostgreSQL (analytics.fato_propostas_credito_diario)
        │
        ▼
Camada semântica / Dashboard de BI
```

## 4. Tecnologias

| Camada | Tecnologia |
|---|---|
| Extração e transformação | Python (pandas, SQLAlchemy) |
| Conexão com origem | SQL Server (via pyodbc) |
| Data Warehouse | PostgreSQL |
| Orquestração | Execução diária agendada (cron / Task Scheduler / Airflow) |
| Visualização | Power BI (fora do escopo deste repositório) |

## 5. Fluxo de Dados

1. **Definição do período** — calcula o intervalo do dia 01 do mês corrente até D-1.
2. **Extração** — consulta as propostas do período no sistema de origem, já
   unindo status, fase de análise, motivo de recusa, canal de atendimento
   e resultado do motor de crédito.
3. **Classificação**
   - *Classe profissional*: qualquer valor fora da lista padrão
     (Empregado, Autônomo, Aposentado/Pensionista, Funcionário Público) é
     agrupado em `OUTROS`.
   - *Faixa de renda*: renda convertida em faixas de salário mínimo
     (menos de 1 S.M. até mais de 5 S.M.).
4. **Carga na staging** — remove o período já carregado e insere os
   registros atualizados (padrão *delete + insert* para permitir
   reprocessamento idempotente).
5. **Atualização da tabela analítica** — reagrega os dados da staging por
   todas as dimensões relevantes, gerando a contagem de propostas por
   combinação de atributos, que alimenta o dashboard final.

## 6. Dicionário de Dados (fictício)

### `originacao.proposta_credito` (origem)
| Coluna | Descrição |
|---|---|
| `proposta_id` | Identificador único da proposta |
| `id_lojista` | Identificador do ponto de venda |
| `id_agente_originador` | Identificador do parceiro/agente originador |
| `data_emissao` | Data de criação da proposta |
| `status_id` | Status atual da proposta |
| `fase_atual_id` | Fase atual na esteira de análise |
| `motivo_recusa_id` | Motivo de recusa, se houver |
| `canal_id` | Canal de atendimento de origem |
| `limite_credito_aprovado` | Limite de crédito atribuído |

### `staging.fato_propostas_credito`
Réplica higienizada da extração, granularidade de proposta individual.

### `analytics.fato_propostas_credito_diario`
Tabela agregada por dia/status/canal/perfil, com `quantidade_propostas`
como métrica de contagem — é a tabela consumida pelo BI.

## 7. Regras de Negócio Principais

- **Normalização de motivos de recusa**: motivos vindos do motor de
  decisão são padronizados em blocos lógicos (restrição de bureau,
  política interna, documentação/fraude, perfil de crédito).
- **Funil sem distorção**: propostas abandonadas ou expiradas são
  tratadas separadamente para não inflar/deflacionar a taxa real de
  aprovação do motor.
- **Exposição de crédito**: o limite médio concedido é acompanhado por
  classe profissional e faixa de renda para evitar sobre-exposição em
  públicos de menor estabilidade financeira.

## 8. Configuração e Execução

### Variáveis de ambiente necessárias

```
SOURCE_DB_HOST=
SOURCE_DB_PORT=1433
SOURCE_DB_NAME=
SOURCE_DB_USER=
SOURCE_DB_PASSWORD=

WAREHOUSE_DB_HOST=
WAREHOUSE_DB_PORT=5432
WAREHOUSE_DB_NAME=
WAREHOUSE_DB_USER=
WAREHOUSE_DB_PASSWORD=
```

### Dependências

```bash
pip install pandas sqlalchemy psycopg2-binary pyodbc python-dotenv
```

### Execução

```bash
python pipeline_originacao_credito.py
```

## 9. Resultado

O pipeline entrega uma base analítica confiável para os times de Risco de
Crédito, Produtos e Prevenção à Fraude, permitindo recalibrar scores de
corte, ajustar limites por perfil socioeconômico e priorizar canais com
melhor taxa de conversão.
