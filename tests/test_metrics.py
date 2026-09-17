"""Métricas locais com relógio controlado, banco temporário e Ollama falso."""

import io
import json
import sqlite3
from unittest.mock import Mock
from urllib.error import URLError

import pytest

from database import database as db
from monitoring import metrics
from agent import ollama_client
from knowledge.knowledge_base import buscar_conhecimento
from tools.credit_simulator import simular_credito


def test_medicao_sucesso(monkeypatch):
    monkeypatch.setattr(metrics.time, "perf_counter", Mock(side_effect=[1.0, 1.125]))
    @metrics.medir_operacao("teste")
    def operacao():
        return 42
    assert operacao() == 42
    registro = db.listar_metricas()[0]
    assert registro["latencia_ms"] == 125.0
    assert registro["status"] == "sucesso"
    assert registro["erro"] is None
    assert registro["criado_em"]


def test_erro_seguro_sem_mensagem_pessoal():
    segredo = "Nome pessoal CPF 123 caminho C:/privado mensagem completa"
    @metrics.medir_operacao("teste")
    def operacao(texto):
        raise ValueError(texto)
    with pytest.raises(ValueError):
        operacao(segredo)
    registro = db.listar_metricas()[0]
    assert registro["status"] == "erro"
    assert registro["erro"] == "dados_invalidos"
    assert segredo not in json.dumps(registro)
    assert set(registro) == {"id", "operacao", "status", "latencia_ms", "modelo", "ferramenta", "erro", "criado_em"}


def test_salvar_listar_resumir(tmp_path):
    caminho = tmp_path / "metricas.db"
    for operacao, status, latencia, ferramenta in [("ollama", "sucesso", 100, None),
        ("ollama", "erro", 200, None), ("tool_call", "sucesso", 3, "simular_credito")]:
        db.salvar_metrica({"operacao": operacao, "status": status, "latencia_ms": latencia,
            "modelo": "llama3.2:3b" if operacao == "ollama" else None,
            "ferramenta": ferramenta, "erro": "ollama_indisponivel" if status == "erro" else None,
            "criado_em": "2026-09-16T12:00:00-03:00"}, caminho)
    assert [r["id"] for r in db.listar_metricas(2, caminho)] == [3, 2]
    assert db.obter_resumo_metricas(caminho) == {"total_operacoes": 3, "sucessos": 2, "erros": 1,
        "latencia_media_ms": 101, "maior_latencia_ms": 200, "chamadas_llm": 2, "chamadas_simular_credito": 1}


def test_banco_sem_metricas():
    db.inicializar_banco()
    assert db.listar_metricas() == []
    assert all(valor == 0 for valor in db.obter_resumo_metricas().values())


def test_tool_instrumentada():
    assert simular_credito(5000, 12, 2)["valor_parcela"] == 472.8
    registro = db.listar_metricas()[0]
    assert registro["operacao"] == "tool_call"
    assert registro["ferramenta"] == "simular_credito"
    assert registro["modelo"] is None
    assert registro["status"] == "sucesso"


def test_tool_erro():
    with pytest.raises(ValueError):
        simular_credito(-1, 12, 2)
    assert db.listar_metricas()[0]["status"] == "erro"


def test_busca_instrumentada():
    buscar_conhecimento("Como funciona a Tabela Price?")
    registro = db.listar_metricas()[0]
    assert registro["operacao"] == "knowledge_search"
    assert registro["status"] == "sucesso"
    assert "Tabela Price" not in json.dumps(registro)


def test_ollama_mock_sem_armazenar_mensagem(monkeypatch):
    transporte = Mock()
    transporte.open.return_value = io.BytesIO(b'{"done":true,"message":{"content":"{}"}}')
    monkeypatch.setattr(ollama_client, "build_opener", Mock(return_value=transporte))
    assert ollama_client.consultar_modelo([{"role": "user", "content": "MENSAGEM PRIVADA"}], {}) == {}
    registro = db.listar_metricas()[0]
    assert registro["operacao"] == "ollama"
    assert registro["modelo"] == "llama3.2:3b"
    assert registro["status"] == "sucesso"
    assert "MENSAGEM PRIVADA" not in json.dumps(registro)


def test_ollama_indisponivel_registra_erro(monkeypatch):
    transporte = Mock()
    transporte.open.side_effect = URLError("URL interna e dados privados")
    monkeypatch.setattr(ollama_client, "build_opener", Mock(return_value=transporte))
    with pytest.raises(ollama_client.OllamaIndisponivel):
        ollama_client.consultar_modelo([], {})
    registro = db.listar_metricas()[0]
    assert registro["status"] == "erro"
    assert registro["erro"] == "ollama_indisponivel"


def test_falha_monitoramento_nao_quebra_operacao(monkeypatch):
    monkeypatch.setattr(db, "salvar_metrica", Mock(side_effect=sqlite3.OperationalError("bloqueado")))
    assert simular_credito(5000, 12, 2)["valor_parcela"] == 472.8
    with pytest.raises(ValueError):
        simular_credito(0, 12, 2)


@pytest.mark.parametrize("limite", [0, -1, True, 1.5])
def test_limite_invalido(limite):
    with pytest.raises(ValueError):
        db.listar_metricas(limite)
