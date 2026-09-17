"""Persistência local das simulações de crédito usando SQLite."""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path


CAMINHO_BANCO = Path(__file__).resolve().parent / "credit_ai.db"


def inicializar_banco(caminho_banco=None):
    """Cria o banco e a tabela, preservando registros existentes."""
    caminho = CAMINHO_BANCO if caminho_banco is None else caminho_banco
    with closing(sqlite3.connect(caminho)) as conexao:
        with conexao:
            conexao.execute("""
                CREATE TABLE IF NOT EXISTS execucoes_automacao (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('iniciada', 'concluida', 'erro')),
                    simulacao_id INTEGER,
                    arquivo TEXT,
                    erro TEXT,
                    criado_em TEXT NOT NULL
                )
            """)

            conexao.execute("""
                CREATE TABLE IF NOT EXISTS solicitacoes_proposta (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    simulacao_id INTEGER,
                    valor_solicitado REAL NOT NULL,
                    parcelas INTEGER NOT NULL,
                    taxa_juros_mensal REAL NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pendente', 'aprovada', 'cancelada')),
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT
                )
            """)
            conexao.execute("""
                CREATE TABLE IF NOT EXISTS simulacoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    valor_solicitado REAL NOT NULL,
                    parcelas INTEGER NOT NULL,
                    taxa_juros_mensal REAL NOT NULL,
                    valor_parcela REAL NOT NULL,
                    valor_total REAL NOT NULL,
                    total_juros REAL NOT NULL,
                    criado_em TEXT NOT NULL
                )
            """)
            conexao.execute("""
                CREATE TABLE IF NOT EXISTS metricas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operacao TEXT NOT NULL,
                    status TEXT NOT NULL,
                    latencia_ms REAL NOT NULL,
                    modelo TEXT,
                    ferramenta TEXT,
                    erro TEXT,
                    criado_em TEXT NOT NULL
                )
            """)


            # Migração aditiva e idempotente: registros anteriores permanecem.
            colunas = {linha[1] for linha in conexao.execute("PRAGMA table_info(metricas)")}
            if "agente_origem" not in colunas:
                conexao.execute("ALTER TABLE metricas ADD COLUMN agente_origem TEXT")
            if "agente_destino" not in colunas:
                conexao.execute("ALTER TABLE metricas ADD COLUMN agente_destino TEXT")


def salvar_simulacao(resultado, caminho_banco=None):
    """Salva o resultado em um banco inicializado e retorna o ID criado.

    A data e hora usam o horário local com indicação do fuso em formato ISO.
    """
    caminho = CAMINHO_BANCO if caminho_banco is None else caminho_banco
    with closing(sqlite3.connect(caminho)) as conexao:
        with conexao:
            cursor = conexao.execute(
                """
                INSERT INTO simulacoes (
                    valor_solicitado, parcelas, taxa_juros_mensal,
                    valor_parcela, valor_total, total_juros, criado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resultado["valor_solicitado"],
                    resultado["parcelas"],
                    resultado["taxa_juros_mensal"],
                    resultado["valor_parcela"],
                    resultado["valor_total"],
                    resultado["total_juros"],
                    datetime.now().astimezone().isoformat(),
                ),
            )
            return cursor.lastrowid


def listar_simulacoes(limite=10, caminho_banco=None):
    """Retorna dicionários em ordem de inserção, dos mais novos aos antigos."""
    if isinstance(limite, bool) or not isinstance(limite, int) or limite <= 0:
        raise ValueError("O limite deve ser um número inteiro maior que zero.")
    caminho = CAMINHO_BANCO if caminho_banco is None else caminho_banco
    with closing(sqlite3.connect(caminho)) as conexao:
        conexao.row_factory = sqlite3.Row
        registros = conexao.execute(
            "SELECT * FROM simulacoes ORDER BY id DESC LIMIT ?", (limite,)
        ).fetchall()
        return [dict(registro) for registro in registros]


def salvar_metrica(metrica, caminho_banco=None):
    """Grava somente os campos técnicos definidos, sem payloads da operação."""
    inicializar_banco(caminho_banco)
    caminho = CAMINHO_BANCO if caminho_banco is None else caminho_banco
    campos = ("operacao", "status", "latencia_ms", "modelo", "ferramenta", "erro", "criado_em", "agente_origem", "agente_destino")
    with closing(sqlite3.connect(caminho)) as conexao:
        with conexao:
            cursor = conexao.execute(
                """INSERT INTO metricas
                (operacao, status, latencia_ms, modelo, ferramenta, erro, criado_em, agente_origem, agente_destino)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", tuple(metrica.get(campo) for campo in campos)
            )
            return cursor.lastrowid


def listar_metricas(limite=50, caminho_banco=None):
    """Lista os registros técnicos mais recentes primeiro."""
    if isinstance(limite, bool) or not isinstance(limite, int) or limite <= 0:
        raise ValueError("O limite deve ser um inteiro maior que zero.")
    caminho = CAMINHO_BANCO if caminho_banco is None else caminho_banco
    with closing(sqlite3.connect(caminho)) as conexao:
        conexao.row_factory = sqlite3.Row
        return [{k: v for k, v in dict(linha).items() if k not in ("agente_origem", "agente_destino") or v is not None} for linha in conexao.execute(
            "SELECT * FROM metricas ORDER BY id DESC LIMIT ?", (limite,)
        ).fetchall()]


def obter_resumo_handoffs(caminho_banco=None):
    """Resumo complementar; preserva o contrato anterior de métricas gerais."""
    caminho = CAMINHO_BANCO if caminho_banco is None else caminho_banco
    with closing(sqlite3.connect(caminho)) as conexao:
        chamadas = {nome: 0 for nome in ("simulation", "knowledge", "market_data")}
        for nome, quantidade in conexao.execute("""SELECT agente_destino, COUNT(*) FROM metricas
                WHERE operacao = 'agent_handoff' GROUP BY agente_destino"""):
            if nome in chamadas:
                chamadas[nome] = quantidade
        return {"quantidade_handoffs": sum(chamadas.values()), "chamadas_por_agente": chamadas}


def obter_resumo_metricas(caminho_banco=None):
    """Agrega todas as operações; a média não fica limitada aos registros recentes."""
    caminho = CAMINHO_BANCO if caminho_banco is None else caminho_banco
    with closing(sqlite3.connect(caminho)) as conexao:
        conexao.row_factory = sqlite3.Row
        return dict(conexao.execute("""
            SELECT COUNT(*) AS total_operacoes,
                COALESCE(SUM(status IN ('sucesso', 'pendente', 'aprovada', 'cancelada')), 0) AS sucessos,
                COALESCE(SUM(status = 'erro'), 0) AS erros,
                COALESCE(AVG(latencia_ms), 0) AS latencia_media_ms,
                COALESCE(MAX(latencia_ms), 0) AS maior_latencia_ms,
                COALESCE(SUM(operacao = 'ollama'), 0) AS chamadas_llm,
                COALESCE(SUM(operacao = 'tool_call' AND ferramenta = 'simular_credito'), 0) AS chamadas_simular_credito
            FROM metricas
        """).fetchone())


STATUS_SOLICITACAO = {"pendente", "aprovada", "cancelada"}


def obter_simulacao(simulacao_id, caminho_banco=None):
    caminho = CAMINHO_BANCO if caminho_banco is None else caminho_banco
    with closing(sqlite3.connect(caminho)) as conexao:
        conexao.row_factory = sqlite3.Row
        registro = conexao.execute("SELECT * FROM simulacoes WHERE id = ?", (simulacao_id,)).fetchone()
        return dict(registro) if registro else None


def iniciar_automacao(caminho_banco=None):
    inicializar_banco(caminho_banco)
    caminho = CAMINHO_BANCO if caminho_banco is None else caminho_banco
    with closing(sqlite3.connect(caminho)) as conexao:
        with conexao:
            return conexao.execute("""INSERT INTO execucoes_automacao (tipo, status, criado_em)
                VALUES ('gerar_relatorio', 'iniciada', ?)""",
                (datetime.now().astimezone().isoformat(),)).lastrowid


def finalizar_automacao(identificador, status, simulacao_id=None, arquivo=None, erro=None, caminho_banco=None):
    if status not in ("concluida", "erro"):
        raise ValueError("Status final da automação inválido.")
    caminho = CAMINHO_BANCO if caminho_banco is None else caminho_banco
    with closing(sqlite3.connect(caminho)) as conexao:
        with conexao:
            cursor = conexao.execute("""UPDATE execucoes_automacao
                SET status = ?, simulacao_id = ?, arquivo = ?, erro = ?
                WHERE id = ? AND status = 'iniciada'""", (status, simulacao_id, arquivo, erro, identificador))
            if cursor.rowcount != 1:
                raise ValueError("Execução inexistente ou já encerrada.")


def listar_execucoes_automacao(limite=10, caminho_banco=None):
    if type(limite) is not int or limite <= 0:
        raise ValueError("O limite deve ser um inteiro positivo.")
    caminho = CAMINHO_BANCO if caminho_banco is None else caminho_banco
    with closing(sqlite3.connect(caminho)) as conexao:
        conexao.row_factory = sqlite3.Row
        return [dict(r) for r in conexao.execute(
            "SELECT * FROM execucoes_automacao ORDER BY id DESC LIMIT ?", (limite,)).fetchall()]


def salvar_solicitacao(solicitacao, caminho_banco=None):
    """Só permite criar solicitações pendentes, nunca pré-aprovadas."""
    if solicitacao.get("status") != "pendente":
        raise ValueError("Uma nova solicitação deve estar pendente.")
    inicializar_banco(caminho_banco)
    caminho = CAMINHO_BANCO if caminho_banco is None else caminho_banco
    with closing(sqlite3.connect(caminho)) as conexao:
        with conexao:
            cursor = conexao.execute("""
                INSERT INTO solicitacoes_proposta
                (simulacao_id, valor_solicitado, parcelas, taxa_juros_mensal, status, criado_em)
                VALUES (?, ?, ?, ?, 'pendente', ?)
            """, (solicitacao.get("simulacao_id"), solicitacao["valor_solicitado"],
                  solicitacao["parcelas"], solicitacao["taxa_juros_mensal"],
                  datetime.now().astimezone().isoformat()))
            return cursor.lastrowid


def obter_solicitacao(solicitacao_id, caminho_banco=None):
    caminho = CAMINHO_BANCO if caminho_banco is None else caminho_banco
    with closing(sqlite3.connect(caminho)) as conexao:
        conexao.row_factory = sqlite3.Row
        linha = conexao.execute("SELECT * FROM solicitacoes_proposta WHERE id = ?", (solicitacao_id,)).fetchone()
        return dict(linha) if linha else None


def listar_solicitacoes(limite=10, caminho_banco=None):
    if type(limite) is not int or limite <= 0:
        raise ValueError("O limite deve ser um inteiro maior que zero.")
    caminho = CAMINHO_BANCO if caminho_banco is None else caminho_banco
    with closing(sqlite3.connect(caminho)) as conexao:
        conexao.row_factory = sqlite3.Row
        return [dict(linha) for linha in conexao.execute(
            "SELECT * FROM solicitacoes_proposta ORDER BY id DESC LIMIT ?", (limite,)
        ).fetchall()]


def atualizar_status_solicitacao(solicitacao_id, status, caminho_banco=None, *, confirmacao_humana=False):
    """Transição atômica de pendente para estado final, pelo controlador confiável.

    Esta API interna não é exposta ao modelo. O sinal de confirmação nunca deve
    vir de argumentos ou texto produzido pelo LLM.
    """
    if not isinstance(status, str) or status not in STATUS_SOLICITACAO or status == "pendente":
        raise ValueError("Status final inválido.")
    if confirmacao_humana is not True:
        raise ValueError("É necessária uma confirmação explícita na interface.")
    caminho = CAMINHO_BANCO if caminho_banco is None else caminho_banco
    with closing(sqlite3.connect(caminho)) as conexao:
        with conexao:
            cursor = conexao.execute("""
                UPDATE solicitacoes_proposta SET status = ?, atualizado_em = ?
                WHERE id = ? AND status = 'pendente'
            """, (status, datetime.now().astimezone().isoformat(), solicitacao_id))
            if cursor.rowcount != 1:
                raise ValueError("A solicitação não existe ou já foi encerrada.")
