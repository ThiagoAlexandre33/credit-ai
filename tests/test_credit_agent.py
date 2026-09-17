"""Testes da orquestração por regras, sem LLM ou serviços externos."""

import json
from functools import partial
from unittest.mock import patch

import pytest

from agent.credit_agent import processar_mensagem

# Preserva a cobertura da interpretação anterior sem depender do modelo local.
processar_mensagem = partial(processar_mensagem, usar_llm=False)


def test_identificacao_e_resultado():
    mensagem = "Quero simular 5000 reais em 12 parcelas com taxa de 2%"
    resposta = processar_mensagem(mensagem)
    assert resposta["tipo"] == "simulacao_credito"
    assert resposta["mensagem_usuario"] == mensagem
    assert resposta["tool_utilizada"] == "simular_credito"
    assert resposta["argumentos"] == {"valor": 5000, "parcelas": 12, "taxa_juros_mensal": 2}
    assert resposta["resultado"]["valor_parcela"] == 472.80
    assert json.loads(json.dumps(resposta, allow_nan=False)) == resposta


def test_chamada_da_ferramenta():
    with patch("tools.credit_simulator.simular_credito", return_value={"teste": True}) as ferramenta:
        resposta = processar_mensagem("Simular 5000 reais em 12 parcelas a 2%")
    ferramenta.assert_called_once_with(valor=5000, parcelas=12, taxa_juros_mensal=2)
    assert resposta["resultado"] == {"teste": True}


@pytest.mark.parametrize(("mensagem", "faltantes"), [
    ("Quero simular em 12 parcelas com taxa de 2%", ["valor"]),
    ("Quero simular 5000 reais com taxa de 2%", ["parcelas"]),
    ("Quero simular 5000 reais em 12 parcelas", ["taxa_juros_mensal"]),
    ("Quero simular", ["valor", "parcelas", "taxa_juros_mensal"]),
])
def test_informacoes_ausentes(mensagem, faltantes):
    with patch("tools.credit_simulator.simular_credito") as ferramenta:
        resposta = processar_mensagem(mensagem)
    assert resposta["tipo"] == "dados_incompletos"
    assert resposta["informacoes_faltantes"] == faltantes
    assert resposta["tool_utilizada"] is None
    ferramenta.assert_not_called()


@pytest.mark.parametrize("mensagem", ["Olá, tudo bem?", "", "Paguei 5000 reais em 12 parcelas a 2%"])
def test_sem_intencao_de_simular(mensagem):
    with patch("tools.credit_simulator.simular_credito") as ferramenta:
        resposta = processar_mensagem(mensagem)
    assert resposta["tipo"] == "sem_intencao_simulacao"
    ferramenta.assert_not_called()


@pytest.mark.parametrize("mensagem", [
    "Simulação de R$ 5.000,00 em 12 parcelas a 2,00% ao mês",
    "SIMULAR valor de 5000 em 12 parcelas com taxa de 2 por cento",
    "Simular 5000 em 12 parcelas a 2%",
])
def test_variacoes_de_formato(mensagem):
    resposta = processar_mensagem(mensagem)
    assert resposta["argumentos"] == {"valor": 5000, "parcelas": 12, "taxa_juros_mensal": 2}
    assert resposta["tipo"] == "simulacao_credito"


def test_taxa_zero():
    resposta = processar_mensagem("Simular 5000 reais em 12 parcelas a 0%")
    assert resposta["resultado"]["total_juros"] == 0


@pytest.mark.parametrize("mensagem", [
    "Simular -5000 reais em 12 parcelas a 2%",
    "Simular 5000 reais em 0 parcelas a 2%",
    "Simular 5000 reais em 1,5 parcelas a 2%",
    "Simular 5000 reais em 12 parcelas a -2%",
])
def test_validacao_pela_ferramenta(mensagem):
    resposta = processar_mensagem(mensagem)
    assert resposta["tipo"] == "dados_invalidos"
    assert resposta["tool_utilizada"] == "simular_credito"
    assert resposta["mensagem"]
    assert "resultado" not in resposta


def test_mensagem_deve_ser_texto():
    with pytest.raises(ValueError, match="mensagem deve ser um texto"):
        processar_mensagem(None)
