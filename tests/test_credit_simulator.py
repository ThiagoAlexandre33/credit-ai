"""Testes da ferramenta de simulação de crédito."""

import json

import pytest

from tools.credit_simulator import simular_credito


def test_simulacao_com_juros():
    resultado = simular_credito(5000, 12, 2)
    assert resultado == {
        "valor_solicitado": 5000.00,
        "parcelas": 12,
        "taxa_juros_mensal": 2.0,
        "valor_parcela": 472.80,
        "valor_total": 5673.58,
        "total_juros": 673.58,
    }
    assert json.loads(json.dumps(resultado, allow_nan=False)) == resultado


def test_simulacao_sem_juros():
    assert simular_credito(5000, 12, 0) == {
        "valor_solicitado": 5000.00,
        "parcelas": 12,
        "taxa_juros_mensal": 0.0,
        "valor_parcela": 416.67,
        "valor_total": 5000.00,
        "total_juros": 0.00,
    }


@pytest.mark.parametrize("valor", [0, -1, -5000, "5000", None, True, float("nan"), float("inf")])
def test_valor_invalido(valor):
    with pytest.raises(ValueError, match="valor solicitado"):
        simular_credito(valor, 12, 2)


@pytest.mark.parametrize("parcelas", [0, -1, -12, 1.5, 12.0, "12", None, True])
def test_parcelas_invalidas(parcelas):
    with pytest.raises(ValueError, match="parcelas.*inteiro maior que zero"):
        simular_credito(5000, parcelas, 2)


@pytest.mark.parametrize("taxa", [-1, -0.01, "2", None, True, float("nan"), float("inf")])
def test_taxa_invalida(taxa):
    with pytest.raises(ValueError, match="taxa de juros mensal"):
        simular_credito(5000, 12, taxa)


def test_parcela_unica():
    resultado = simular_credito(1000, 1, 2)
    assert resultado["valor_parcela"] == 1020.00
    assert resultado["valor_total"] == 1020.00
    assert resultado["total_juros"] == 20.00


def test_taxa_muito_pequena():
    resultado = simular_credito(5000, 12, 1e-15)
    assert resultado["valor_parcela"] == 416.67
    assert resultado["valor_total"] == 5000.00


def test_resultado_fora_do_limite_numerico():
    with pytest.raises(ValueError, match="limite numérico"):
        simular_credito(1e308, 12, 100)
