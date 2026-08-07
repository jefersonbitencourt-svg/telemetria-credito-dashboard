# Documentação Técnica — Pipeline de Telemetria e Análise de Risco na Esteira de Crédito

> **Projeto de Portfólio:** Desenvolvido com base em um contexto corporativo real. Dados, nomes de tabelas, colunas, parceiros e métricas sensíveis foram **fictícios/adaptados** para garantir a confidencialidade e segurança das informações.

## 1. Visão Geral

Centralização e análise end-to-end da esteira de originação de crédito (cartão co-branded / private label). 
O projeto abrange desde a ingestão diária via pipeline Python/SQL até o consumo por um modelo semântico no Power BI, dando visibilidade total sobre a taxa de conversão das propostas, eficácia das políticas do motor de decisão e exposição financeira por perfil socioeconômico.

## 2. O desafio do Negócio

A operação de crédito recebia propostas vindas de múltiplos canais (*autoatendimento, balcão de lojas, promotoras de venda*). 
As etapas de análise — *pré-aprovação automática, mesa de crédito, checagem de fraude e consulta a bureaus externos* — ficavam espalhadas em sistemas diferentes.

### Principais Dores:

* **Esteira Fragmentada:** Ausência de uma visão unificada do funil de conversão.
* **Motivos de Recusa Não Padronizados:** Centenas de *strings* de recusa divergentes retornadas pelo motor de decisão sem agrupamento de negócio.
* **Exposição de Risco Sem Visibilidade:** Falta de acompanhamento consolidado do limite médio concedido por perfil socioeconômico.

## 3. Arquitetura

```
Sistema do Emissor (SQL Server)
        │
        ▼ (Extração Incremental)
Pipeline Python / SQL (ETL, Sanitização e Regras de Negócio)
        │
        ▼ (Carga Idempotente - Delete + Insert)
Data Warehouse PostgreSQL (Staging e Analytics)
        │
        ▼ (Conexão via Gateway On-Premises)
Power BI Dataflow (Fluxo de Dados)
        │
        ▼ (Modelo Semântico & Medidas DAX)
Dashboard de Telemetria (Power BI Service)
```

## 4. Tecnologias

| Camada | Tecnologia |
|---|---|
| Extração e transformação | Python (pandas, SQL) |
| Conexão com origem | SQL Server (via pyodbc) |
| Data Warehouse | PostgreSQL |
| Orquestração | Execução diária via Script .bat + Agendador de Tarefas do Windows (Task Scheduler) |
| Visualização | Power BI |
| Camada Semântica & Ingestão BI | Power BI Dataflow (Fluxo de Dados) via On-Premises Data Gateway |
| Modelagem & Métricas | Power BI Desktop (DAX) |

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
   reprocessamento).
5. **Atualização da tabela analítica** — reagrega os dados da staging por
   todas as dimensões relevantes, gerando a contagem de propostas por
   combinação de atributos, que alimenta o dashboard final.

## 6. Dicionário de Dados (fictício/adaptado)

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
