"""Protocolo MCP em memória, sem processos externos ou rede."""

import asyncio
import json
from unittest.mock import Mock

import pytest
from mcp import Client

from database import database
from mcp_server import server

ARGUMENTOS = {"valor": 5000, "parcelas": 12, "taxa_juros_mensal": 2}


def chamar(nome, argumentos):
    async def executar():
        async with Client(server.criar_servidor(), raise_exceptions=True) as cliente:
            return await cliente.call_tool(nome, argumentos)
    return asyncio.run(executar())


def test_inicializacao_e_registro_exclusivo():
    async def executar():
        async with Client(server.criar_servidor(), raise_exceptions=True) as cliente:
            tools = (await cliente.list_tools()).tools
            assert {t.name for t in tools} == server.MCP_TOOLS_PERMITIDAS
            assert len(tools) == 3
            assert all(t.input_schema["additionalProperties"] is False for t in tools)
    asyncio.run(executar())


def test_simulacao_delega_e_retorna_json(monkeypatch):
    original = server.credit_simulator.simular_credito
    funcao = Mock(wraps=original)
    monkeypatch.setattr(server.credit_simulator, "simular_credito", funcao)
    resposta = chamar("simular_credito", ARGUMENTOS)
    funcao.assert_called_once_with(**ARGUMENTOS)
    assert not resposta.is_error
    assert resposta.structured_content["valor_parcela"] == 472.8
    assert resposta.structured_content["valor_total"] == 5673.58
    assert resposta.structured_content["total_juros"] == 673.58
    assert json.loads(resposta.content[0].text) == resposta.structured_content


def test_selic_delega_sem_argumentos(monkeypatch):
    dado = {"serie_sgs": 1178, "valor_percentual_ano": 13.25,
            "data_referencia": "2026-09-16", "fonte": "Banco Central"}
    funcao = Mock(return_value=dado)
    monkeypatch.setattr(server.bcb_client, "consultar_selic_recente", funcao)
    resposta = chamar("consultar_selic", {})
    funcao.assert_called_once_with()
    assert not resposta.is_error
    assert all(resposta.structured_content[k] == v for k, v in dado.items())


@pytest.mark.parametrize("trechos", [[], [{"arquivo": "faq_credito.md", "trecho": "Tabela Price", "score": 5}]])
def test_busca_delega_sem_inventar_fontes(monkeypatch, trechos):
    funcao = Mock(return_value=trechos)
    monkeypatch.setattr(server.knowledge_base, "buscar_conhecimento", funcao)
    resposta = chamar("buscar_conhecimento", {"pergunta": "Tabela Price"})
    funcao.assert_called_once_with("Tabela Price")
    assert not resposta.is_error
    assert resposta.structured_content == {"trechos": trechos}


@pytest.mark.parametrize("alteracao", [
    {"valor": 0}, {"valor": -1}, {"valor": True}, {"valor": "5000"},
    {"parcelas": 0}, {"parcelas": -1}, {"parcelas": 1.5}, {"parcelas": True},
    {"taxa_juros_mensal": -1}, {"taxa_juros_mensal": "2"}, {"arquivo": "../privado"},
])
def test_argumentos_invalidos_nao_chamam_simulador(monkeypatch, alteracao):
    funcao = Mock()
    monkeypatch.setattr(server.credit_simulator, "simular_credito", funcao)
    assert chamar("simular_credito", {**ARGUMENTOS, **alteracao}).is_error
    funcao.assert_not_called()


@pytest.mark.parametrize("nome,args", [
    ("simular_credito", {}), ("consultar_selic", {"url": "http://127.0.0.1/segredo"}),
    ("buscar_conhecimento", {"pergunta": "Price", "pasta_documentos": "../"}),
    ("buscar_conhecimento", {"pergunta": ""}), ("buscar_conhecimento", {"pergunta": "  "}),
    ("buscar_conhecimento", {"pergunta": 123}), ("buscar_conhecimento", {"pergunta": "x" * 4001}),
])
def test_argumentos_restritos(monkeypatch, nome, args):
    funcoes = [Mock(), Mock(), Mock()]
    monkeypatch.setattr(server.credit_simulator, "simular_credito", funcoes[0])
    monkeypatch.setattr(server.bcb_client, "consultar_selic_recente", funcoes[1])
    monkeypatch.setattr(server.knowledge_base, "buscar_conhecimento", funcoes[2])
    assert chamar(nome, args).is_error
    for funcao in funcoes:
        funcao.assert_not_called()


@pytest.mark.parametrize("nome", ["inexistente", "aprovar_solicitacao", "cancelar_solicitacao",
    "subprocess", "shell", "os.system", "eval", "exec", "escrever_arquivo"])
def test_whitelist_rejeita_funcoes_perigosas(nome):
    assert chamar(nome, {}).is_error
    assert nome not in server.MCP_TOOLS_PERMITIDAS


@pytest.mark.parametrize("erro", [server.bcb_client.BCBIndisponivel,
    server.bcb_client.BCBRespostaInvalida, RuntimeError])
def test_falha_bcb_segura_e_servidor_continua(monkeypatch, erro):
    monkeypatch.setattr(server.bcb_client, "consultar_selic_recente", Mock(side_effect=erro("SEGREDO")))
    async def executar():
        async with Client(server.criar_servidor(), raise_exceptions=True) as cliente:
            falha = await cliente.call_tool("consultar_selic", {})
            assert falha.is_error
            assert "SEGREDO" not in falha.content[0].text
            sucesso = await cliente.call_tool("simular_credito", ARGUMENTOS)
            assert not sucesso.is_error
    asyncio.run(executar())
    metricas = [m for m in database.listar_metricas() if m["operacao"] == "mcp_tool_call"]
    assert {m["status"] for m in metricas} == {"erro", "sucesso"}
    assert all(m["latencia_ms"] >= 0 and m["criado_em"] for m in metricas)
    assert "SEGREDO" not in json.dumps(metricas)


def test_metrica_nao_armazena_nome_arbitrario():
    chamar("SEGREDO nome pessoal", {})
    metrica = database.listar_metricas()[0]
    assert metrica["ferramenta"] == "nao_permitida"
    assert metrica["status"] == "erro"
    assert "SEGREDO" not in json.dumps(metrica)
