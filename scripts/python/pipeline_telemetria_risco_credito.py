# %%
"""
Pipeline ETL — Telemetria de Originação de Crédito
====================================================

Projeto de portfólio (projeto real com dados e regras de negócio adaptados para garantir a anonimalidade dos dados).

Objetivo
--------
Extrair diariamente as propostas de crédito (cartão co-branded / private
label) do sistema de origem, classificar o perfil socioeconômico dos
proponentes e consolidar os dados em um Data Warehouse PostgreSQL para
consumo posterior em um dashboard de BI (conversão da esteira, motivos de
recusa, exposição de limite de crédito etc.).

Arquitetura
-----------
Sistema de Origem (SQL Server) Extração (Python)
    Classificação (renda / classe profissional)
    taging (PostgreSQL)
    Tabela analítica diária (PostgreSQL)

Dependências
------------
    pip install pandas sqlalchemy psycopg2-binary pyodbc python-dotenv
"""

import logging
import os
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("pipeline_originacao_credito")

# %%

# ---------------------------------------------------------------------------
# Configuração (dados de conexão)
# ---------------------------------------------------------------------------
SOURCE_DB = {
    "host": os.getenv("SOURCE_DB_HOST", "SEU_HOST_AQUI"),
    "port": os.getenv("SOURCE_DB_PORT", "1433"),
    "database": os.getenv("SOURCE_DB_NAME", "SEU_BANCO_AQUI"),
    "user": os.getenv("SOURCE_DB_USER", "SEU_USUARIO_AQUI"),
    "password": os.getenv("SOURCE_DB_PASSWORD", "SUA_SENHA_AQUI"),
}

WAREHOUSE_DB = {
    "host": os.getenv("WAREHOUSE_DB_HOST", "SEU_HOST_AQUI"),
    "port": os.getenv("WAREHOUSE_DB_PORT", "5432"),
    "database": os.getenv("WAREHOUSE_DB_NAME", "SEU_BANCO_AQUI"),
    "user": os.getenv("WAREHOUSE_DB_USER", "SEU_USUARIO_AQUI"),
    "password": os.getenv("WAREHOUSE_DB_PASSWORD", "SUA_SENHA_AQUI"),
}

STAGING_TABLE = "staging.fato_propostas_credito"
ANALYTICS_TABLE = "analytics.fato_propostas_credito_diario"

# Agentes/parceiros adaptados que originam propostas
PARCEIROS_ORIGINADORES = ("PARCEIRO_REGIAO_NORTE", "PARCEIRO_REGIAO_SUL", "PARCEIRO_CARTAO")

# %%
# ---------------------------------------------------------------------------
# Conexões (definindo as funções de conexão)
# ---------------------------------------------------------------------------

def get_source_engine():
    """Cria engine SQLAlchemy para o banco transacional de origem."""
    conn_str = (
        f"mssql+pyodbc://{SOURCE_DB['user']}:{SOURCE_DB['password']}"
        f"@{SOURCE_DB['host']}:{SOURCE_DB['port']}/{SOURCE_DB['database']}"
        "?driver=ODBC+Driver+17+for+SQL+Server"
    )
    return create_engine(conn_str)


def get_warehouse_engine():
    """Cria engine SQLAlchemy para o Data Warehouse PostgreSQL."""
    conn_str = (
        f"postgresql+psycopg2://{WAREHOUSE_DB['user']}:{WAREHOUSE_DB['password']}"
        f"@{WAREHOUSE_DB['host']}:{WAREHOUSE_DB['port']}/{WAREHOUSE_DB['database']}"
    )
    return create_engine(conn_str)


# ---------------------------------------------------------------------------
# Definição do período de carga (mês corrente, D-1)
# ---------------------------------------------------------------------------

def definir_periodo_referencia():
    """Retorna (data_inicio, data_fim) cobrindo do dia 01 até D-1 do mês corrente."""
    ontem = datetime.now() - timedelta(days=1)
    data_inicio = ontem.replace(day=1).strftime("%Y-%m-%d")
    data_fim = ontem.strftime("%Y-%m-%d")
    logger.info("Período de referência: %s a %s", data_inicio, data_fim)
    return data_inicio, data_fim


# ---------------------------------------------------------------------------
# Definindo função para extração das propostas na origem
# ---------------------------------------------------------------------------
def montar_query_extracao(data_inicio: str, data_fim: str) -> str:
    """
    Monta a query de extração das propostas de crédito no período informado.

    A query original combina múltiplas subconsultas para resolver o motivo
    de recusa e o perfil de score a partir do motor de decisão. Aqui a
    lógica foi simplificada para fins de portfólio, mas mantém a mesma
    estrutura geral: propostas + status + fase de análise + motivo de
    recusa + canal de origem + classe profissional + renda.
    """
    parceiros = ", ".join(f"'{p}'" for p in PARCEIROS_ORIGINADORES)
    return f"""
        SELECT DISTINCT
            p.id_lojista,
            p.id_agente_originador,
            p.data_emissao,
            FORMAT(p.data_emissao, 'yyyyMM')          AS safra_referencia,
            st.codigo_status                          AS status_codigo,
            st.descricao_status,
            fa.nome_fase_analise,
            cp.classe_profissional,
            cp.renda_informada,
            mr.descricao_motivo_recusa,
            COALESCE(co.descricao_canal, 'Balcao')    AS canal_atendimento,
            p.limite_credito_aprovado,
            ps.perfil_score
        FROM originacao.proposta_credito AS p
        LEFT JOIN originacao.status_proposta        AS st ON p.status_id = st.id
        LEFT JOIN originacao.fase_analise_proposta   AS fa ON p.fase_atual_id = fa.id
        LEFT JOIN originacao.classe_profissional_cliente AS cp ON p.proposta_id = cp.proposta_id
        LEFT JOIN originacao.motivo_recusa           AS mr ON p.motivo_recusa_id = mr.id
        LEFT JOIN originacao.canal_atendimento        AS co ON p.canal_id = co.id
        LEFT JOIN originacao.resultado_motor_credito  AS ps ON p.proposta_id = ps.proposta_id
        WHERE p.id_agente_originador IN ({parceiros})
          AND p.data_emissao BETWEEN '{data_inicio}' AND '{data_fim}'
    """

def extrair_propostas(engine, data_inicio: str, data_fim: str) -> pd.DataFrame:
    """Executa a extração das propostas no banco de origem."""
    query = montar_query_extracao(data_inicio, data_fim)
    logger.info("Extraindo propostas do sistema de origem...")
    df = pd.read_sql(query, engine)
    logger.info("Total de propostas extraídas: %d", len(df))
    return df

# %%
# ---------------------------------------------------------------------------
# Regras de classificação (perfil socioeconômico)
# ---------------------------------------------------------------------------
CLASSES_PROFISSIONAIS_VALIDAS = {
    "EMPREGADO",
    "AUTONOMO",
    "APOSENTADO, PENSIONISTA",
    "FUNCIONARIO PUBLICO",
}

def classificar_classe_profissional(df: pd.DataFrame) -> pd.DataFrame:
    """Agrupa classes profissionais fora da lista padrão em 'OUTROS'."""
    df = df.copy()
    classe_upper = df["classe_profissional"].str.upper()
    df["classe_profissional"] = classe_upper.where(
        classe_upper.isin(CLASSES_PROFISSIONAIS_VALIDAS), "OUTROS"
    )
    return df

FAIXAS_RENDA = [
    (5500, "MAIS DE 5 S.M."),
    (4400, "4 A 5 S.M."),
    (3300, "3 A 4 S.M."),
    (2200, "2 A 3 S.M."),
    (1100, "1 A 2 S.M."),
    (0, "MENOS DE 1 S.M."),
]


def classificar_faixa_renda(df: pd.DataFrame) -> pd.DataFrame:
    """Converte a renda informada em faixas de salário mínimo."""
    df = df.copy()
    renda = pd.to_numeric(
        df["renda_informada"].astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    ).fillna(0)

    def _faixa(valor):
        for limite, rotulo in FAIXAS_RENDA:
            if valor >= limite:
                return rotulo
        return FAIXAS_RENDA[-1][1]

    df["faixa_renda"] = renda.apply(_faixa)
    return df


# ---------------------------------------------------------------------------
# Carga no DW
# ---------------------------------------------------------------------------
def carregar_staging(df: pd.DataFrame, engine, data_inicio: str, data_fim: str):
    """Remove o período já carregado e insere os dados atualizados na staging."""
    with engine.begin() as conn:
        logger.info("Removendo período anterior da staging...")
        conn.execute(
            text(
                f"""
                DELETE FROM {STAGING_TABLE}
                WHERE data_emissao BETWEEN :inicio AND :fim
                """
            ),
            {"inicio": data_inicio, "fim": data_fim},
        )
        logger.info("Inserindo %d registros na staging...", len(df))
        df.to_sql(
            STAGING_TABLE.split(".")[-1],
            con=conn,
            schema=STAGING_TABLE.split(".")[0],
            if_exists="append",
            index=False,
            method="multi",
            chunksize=5000,
        )


def atualizar_tabela_analitica(engine, data_inicio: str, data_fim: str):
    """Recalcula a tabela analítica diária a partir da staging."""
    logger.info("Atualizando tabela analítica diária...")
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                DELETE FROM {ANALYTICS_TABLE}
                WHERE data_emissao BETWEEN :inicio AND :fim
                """
            ),
            {"inicio": data_inicio, "fim": data_fim},
        )
        conn.execute(
            text(
                f"""
                INSERT INTO {ANALYTICS_TABLE}
                SELECT
                    id_lojista,
                    id_agente_originador,
                    data_emissao,
                    status_codigo,
                    descricao_status,
                    classe_profissional,
                    faixa_renda,
                    descricao_motivo_recusa,
                    canal_atendimento,
                    limite_credito_aprovado,
                    perfil_score,
                    COUNT(*) AS quantidade_propostas
                FROM {STAGING_TABLE}
                WHERE data_emissao BETWEEN :inicio AND :fim
                GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11
                """
            ),
            {"inicio": data_inicio, "fim": data_fim},
        )


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
def main():
    data_inicio, data_fim = definir_periodo_referencia()

    source_engine = get_source_engine()
    warehouse_engine = get_warehouse_engine()

    try:
        df_propostas = extrair_propostas(source_engine, data_inicio, data_fim)
        df_propostas = classificar_classe_profissional(df_propostas)
        df_propostas = classificar_faixa_renda(df_propostas)

        carregar_staging(df_propostas, warehouse_engine, data_inicio, data_fim)
        atualizar_tabela_analitica(warehouse_engine, data_inicio, data_fim)

        logger.info("Pipeline concluído com sucesso.")
    except Exception:
        logger.exception("Falha na execução do pipeline.")
        raise
    finally:
        source_engine.dispose()
        warehouse_engine.dispose()


if __name__ == "__main__":
    main()
