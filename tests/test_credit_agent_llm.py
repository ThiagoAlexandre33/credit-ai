"""Contrato do modelo e execução segura da única ferramenta permitida."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from agent import credit_agent as agente
from agent import ollama_client


COMPLETO = {"intencao": "simular_credito", "argumentos": {
    "valor": 5000, "parcelas": 12, "taxa_juros_mensal": 2,
}}


@pytest.fixture
def modelo(monkeypatch):
    fake = Mock(return_value=deepcopy(COMPLETO))
    monkeypatch.setattr(ollama_client, "consultar_modelo", fake)
    return fake


@pytest.mark.parametrize(("mensagem", "valor", "parcelas", "taxa"), [
    ("Quero pegar 5 mil em 12 vezes com juros de 2%", 5000, 12, 2),
    ("Simula 10000 para mim em 24 parcelas a 1,5%", 10000, 24, 1.5),
    ("Quanto fica 3 mil em 10x com taxa de 1%?", 3000, 10, 1),
])
def test_interpretacao_completa(modelo, mensagem, valor, parcelas, taxa):
    argumentos = {"valor": valor, "parcelas": parcelas, "taxa_juros_mensal": taxa}
    modelo.return_value = {"intencao": "simular_credito", "argumentos": argumentos}
    resposta = agente.processar_mensagem(mensagem)
    assert resposta["tipo"] == "simulacao_credito"
    assert resposta["argumentos"] == argumentos
    assert resposta["resultado"]["valor_solicitado"] == valor
    assert modelo.call_args.args[0][-1] == {"role": "user", "content": mensagem}


def test_ferramenta_obrigatoria(modelo, monkeypatch):
    ferramenta = Mock(return_value={"valor_parcela": 123.45})
    monkeypatch.setitem(agente.TOOLS_PERMITIDAS, "simular_credito", ferramenta)
    resposta = agente.processar_mensagem("Quanto fica 5 mil?")
    ferramenta.assert_called_once_with(valor=5000, parcelas=12, taxa_juros_mensal=2)
    assert resposta["resultado"] == ferramenta.return_value


@pytest.mark.parametrize("campo", ["valor", "parcelas", "taxa_juros_mensal"])
def test_incompleto(modelo, monkeypatch, campo):
    modelo.return_value["argumentos"][campo] = None
    ferramenta = Mock()
    monkeypatch.setitem(agente.TOOLS_PERMITIDAS, "simular_credito", ferramenta)
    resposta = agente.processar_mensagem("Quero simular")
    assert resposta["informacoes_faltantes"] == [campo]
    assert resposta["tipo"] == "dados_incompletos"
    ferramenta.assert_not_called()


@pytest.mark.parametrize("invalido", [
    None, [], "texto", {},
    {**COMPLETO, "intencao": "executar_python"},
    {**COMPLETO, "intencao": []},
    {**COMPLETO, "resultado": {"valor_parcela": 0.01}},
    {**COMPLETO, "argumentos": {"valor": 5000}},
    {**COMPLETO, "argumentos": {**COMPLETO["argumentos"], "valor": "5000"}},
    {**COMPLETO, "argumentos": {**COMPLETO["argumentos"], "valor": True}},
    {**COMPLETO, "argumentos": {**COMPLETO["argumentos"], "valor": float("inf")}},
    {**COMPLETO, "argumentos": {**COMPLETO["argumentos"], "parcelas": 1.5}},
    {**COMPLETO, "argumentos": {**COMPLETO["argumentos"], "taxa_juros_mensal": -2}},
])
def test_rejeita_modelo_invalido_sem_executar(modelo, monkeypatch, invalido):
    modelo.return_value = invalido
    ferramenta = Mock()
    monkeypatch.setitem(agente.TOOLS_PERMITIDAS, "simular_credito", ferramenta)
    resposta = agente.processar_mensagem("Simule")
    assert resposta["tipo"] == "resposta_invalida"
    assert "resultado" not in resposta
    ferramenta.assert_not_called()


def test_modelo_indisponivel(modelo):
    modelo.side_effect = ollama_client.OllamaIndisponivel()
    resposta = agente.processar_mensagem("Simule")
    assert resposta["tipo"] == "modelo_indisponivel"
    assert "Verifique se o Ollama" in resposta["mensagem"]


def test_historico_enviado_sem_mutacao(modelo):
    historico = [{"papel": "user", "texto": "Quero simular 5 mil em 12 vezes"},
                 {"papel": "assistant", "texto": "Qual é a taxa de juros mensal?"}]
    copia = deepcopy(historico)
    resposta = agente.processar_mensagem("2%", historico)
    assert resposta["resultado"]["valor_parcela"] == 472.80
    assert modelo.call_args.args[0][1:] == [
        {"role": "user", "content": historico[0]["texto"]},
        {"role": "assistant", "content": historico[1]["texto"]},
        {"role": "user", "content": "2%"},
    ]
    assert historico == copia
