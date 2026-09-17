"""Integração da busca com modelo falso e fontes verificadas em Python."""

import json
from unittest.mock import Mock

import pytest

from agent import credit_agent as agente
from agent import ollama_client

INTENCAO = {"intencao": "conhecimento_credito", "argumentos": {
    "valor": None, "parcelas": None, "taxa_juros_mensal": None}}
TRECHOS = [{"arquivo": "faq_credito.md", "trecho": "Tabela Price tem parcelas fixas. Conteúdo educativo.", "score": 6}]


@pytest.fixture
def fakes(monkeypatch):
    modelo = Mock(side_effect=[INTENCAO, {"encontrou": True, "resposta": "Na demonstração, as parcelas são fixas.", "trechos_utilizados": [0]}])
    busca = Mock(return_value=TRECHOS)
    ferramenta = Mock()
    monkeypatch.setattr(ollama_client, "consultar_modelo", modelo)
    monkeypatch.setattr(agente, "buscar_conhecimento", busca)
    monkeypatch.setitem(agente.TOOLS_PERMITIDAS, "simular_credito", ferramenta)
    return modelo, busca, ferramenta


def test_pergunta_usa_base_e_envia_contexto(fakes):
    modelo, busca, ferramenta = fakes
    resposta = agente.processar_mensagem("Como funciona a Tabela Price?")
    busca.assert_called_once_with("Como funciona a Tabela Price?")
    assert resposta["tipo"] == "conhecimento_credito"
    assert resposta["fontes"] == ["faq_credito.md"]
    assert resposta["trechos"] == TRECHOS
    contexto = json.loads(modelo.call_args.args[0][1]["content"])
    assert contexto["contexto"] == [{"id": 0, **TRECHOS[0]}]
    assert "SOMENTE" in modelo.call_args.args[0][0]["content"]
    ferramenta.assert_not_called()


def test_sem_trecho_nao_gera_resposta_com_modelo(fakes):
    modelo, busca, ferramenta = fakes
    busca.return_value = []
    resposta = agente.processar_mensagem("Qual é a taxa do banco imaginário?")
    assert "Não encontrei" in resposta["mensagem"]
    assert resposta["fontes"] == []
    assert modelo.call_count == 1
    ferramenta.assert_not_called()


def test_trechos_nao_respondem_pergunta(fakes):
    modelo, _, _ = fakes
    modelo.side_effect = [INTENCAO, {"encontrou": False, "resposta": "", "trechos_utilizados": []}]
    assert "Não encontrei" in agente.processar_mensagem("Pergunta específica")["mensagem"]


@pytest.mark.parametrize("resposta_modelo", [
    {"encontrou": True, "resposta": "Resposta", "trechos_utilizados": [9]},
    {"encontrou": True, "resposta": "Resposta", "trechos_utilizados": [-1]},
    {"encontrou": True, "resposta": "Resposta", "trechos_utilizados": [True]},
    {"encontrou": True, "resposta": "Resposta", "trechos_utilizados": []},
    {"encontrou": True, "resposta": "Resposta", "trechos_utilizados": [0], "fontes": ["inventada.md"]},
    "texto livre",
])
def test_rejeita_fontes_invalidas(fakes, resposta_modelo):
    modelo, _, _ = fakes
    modelo.side_effect = [INTENCAO, resposta_modelo]
    resposta = agente.processar_mensagem("Price?")
    assert resposta["fontes"] == []
    assert "fontes válidas" in resposta["mensagem"]


def test_fora_do_escopo_nao_busca_nem_calcula(fakes):
    modelo, busca, ferramenta = fakes
    modelo.side_effect = [{**INTENCAO, "intencao": "outra"}]
    assert agente.processar_mensagem("Previsão do tempo")["tipo"] == "sem_intencao_simulacao"
    busca.assert_not_called()
    ferramenta.assert_not_called()


def test_simulacao_nao_busca(fakes):
    modelo, busca, ferramenta = fakes
    modelo.side_effect = [{"intencao": "simular_credito", "argumentos": {"valor": 5000, "parcelas": 12, "taxa_juros_mensal": 2}}]
    assert agente.processar_mensagem("Simule 5000 em 12 parcelas com taxa de 2%.")["tipo"] == "simulacao_credito"
    ferramenta.assert_called_once_with(valor=5000, parcelas=12, taxa_juros_mensal=2)
    busca.assert_not_called()


def test_ollama_falha_apos_busca(fakes):
    modelo, _, _ = fakes
    modelo.side_effect = [INTENCAO, ollama_client.OllamaIndisponivel()]
    assert "não está disponível" in agente.processar_mensagem("Price?")["mensagem"]
