"""Testes de persistência isolados em bancos temporários."""

import sqlite3
from contextlib import closing
from datetime import datetime

import pytest

from database.database import inicializar_banco, listar_simulacoes, salvar_simulacao
from tools.credit_simulator import simular_credito


@pytest.fixture
def banco(tmp_path):
    caminho = tmp_path / "teste.db"
    inicializar_banco(caminho)
    return caminho


def test_inicializar_banco(tmp_path):
    caminho = tmp_path / "novo.db"
    inicializar_banco(caminho)
    assert caminho.is_file()
    with closing(sqlite3.connect(caminho)) as conexao:
        colunas = conexao.execute("PRAGMA table_info(simulacoes)").fetchall()
    assert [(coluna[1], coluna[2]) for coluna in colunas] == [
        ("id", "INTEGER"),
        ("valor_solicitado", "REAL"),
        ("parcelas", "INTEGER"),
        ("taxa_juros_mensal", "REAL"),
        ("valor_parcela", "REAL"),
        ("valor_total", "REAL"),
        ("total_juros", "REAL"),
        ("criado_em", "TEXT"),
    ]
    assert colunas[0][5] == 1  # Chave primária.
    assert all(coluna[3] == 1 for coluna in colunas[1:])
    assert listar_simulacoes(caminho_banco=caminho) == []


def test_salvar_e_ler_simulacao(banco):
    resultado = simular_credito(5000, 12, 2)
    antes = datetime.now().astimezone()
    identificador = salvar_simulacao(resultado, banco)
    depois = datetime.now().astimezone()
    registros = listar_simulacoes(caminho_banco=banco)
    assert len(registros) == 1
    registro = registros[0]
    assert registro["id"] == identificador == 1
    assert {chave: registro[chave] for chave in resultado} == resultado
    assert antes <= datetime.fromisoformat(registro["criado_em"]) <= depois
    assert "criado_em" not in resultado


def test_reinicializar_preserva_registros(banco):
    salvar_simulacao(simular_credito(1000, 5, 0), banco)
    inicializar_banco(banco)
    assert len(listar_simulacoes(caminho_banco=banco)) == 1


def test_multiplas_simulacoes_em_ordem_mais_recente(banco):
    ids = [salvar_simulacao(simular_credito(valor, 12, 2), banco)
           for valor in (1000, 2000, 3000)]
    registros = listar_simulacoes(caminho_banco=banco)
    assert len(registros) == 3
    assert [registro["id"] for registro in registros] == ids[::-1]
    assert [registro["valor_solicitado"] for registro in registros] == [3000, 2000, 1000]


def test_limite_personalizado(banco):
    for valor in (1000, 2000, 3000):
        salvar_simulacao(simular_credito(valor, 12, 2), banco)
    registros = listar_simulacoes(limite=2, caminho_banco=banco)
    assert [registro["valor_solicitado"] for registro in registros] == [3000, 2000]


def test_limite_padrao_de_dez(banco):
    for _ in range(12):
        salvar_simulacao(simular_credito(1000, 12, 2), banco)
    registros = listar_simulacoes(caminho_banco=banco)
    assert len(registros) == 10
    assert [registro["id"] for registro in registros] == list(range(12, 2, -1))


@pytest.mark.parametrize("limite", [0, -1, 1.5, "10", True])
def test_limite_invalido(banco, limite):
    with pytest.raises(ValueError, match="limite.*inteiro maior que zero"):
        listar_simulacoes(limite, banco)
