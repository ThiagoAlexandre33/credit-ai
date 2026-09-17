"""Especialistas e protocolo de handoff com modelo falso."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from agent import credit_agent, ollama_client
from agents.models import validar_plano, MAX_HANDOFFS
from agents.simulation_agent import SimulationAgent
from agents.knowledge_agent import KnowledgeAgent
from agents.market_data_agent import MarketDataAgent
from database import database
from evaluation.multiagent_scenarios import SCENARIOS_MULTIAGENT, avaliar_multiagent, ARGS


@pytest.mark.parametrize("cenario", SCENARIOS_MULTIAGENT, ids=lambda c: c["id"])
def test_cenarios_multiagent(cenario):
    database.inicializar_banco()
    resultado = avaliar_multiagent(cenario)
    assert resultado["status"] == "aprovado", resultado["falhas"]


@pytest.mark.parametrize("plano", [["simulation"] * 4, ["simulation", "simulation"], ["admin"], [1], "simulation", None])
def test_plano_invalido(plano):
    with pytest.raises(ValueError):
        validar_plano(plano)


def test_limite_tres_sem_loops(monkeypatch):
    plano = {"intencao": "simular_credito", "argumentos": ARGS, "agentes": ["knowledge", "simulation", "market_data"]}
    monkeypatch.setattr(ollama_client, "consultar_modelo", Mock(return_value=plano))
    monkeypatch.setattr(credit_agent, "buscar_conhecimento", Mock(return_value=[]))
    monkeypatch.setitem(credit_agent.APIS_PERMITIDAS, "bcb_selic", Mock(side_effect=RuntimeError("SEGREDO")))
    resposta = credit_agent.processar_mensagem("Simule 5000 em 12 parcelas a 2%")
    assert len(resposta["respostas"]) == MAX_HANDOFFS
    assert resposta["resultado"]["valor_parcela"] == 472.8
    assert "SEGREDO" not in json.dumps(resposta)
    resumo = database.obter_resumo_handoffs()
    assert resumo == {"quantidade_handoffs": 3, "chamadas_por_agente": {"simulation": 1, "knowledge": 1, "market_data": 1}}
    metricas = [m for m in database.listar_metricas() if m["operacao"] == "agent_handoff"]
    assert all(m["agente_origem"] == "orchestrator" and m["criado_em"] for m in metricas)
    assert "SEGREDO" not in json.dumps(metricas)


@pytest.mark.parametrize("classe,permitida", [(SimulationAgent, "simular_credito"), (KnowledgeAgent, "buscar_conhecimento"), (MarketDataAgent, "consultar_selic")])
def test_capacidades_exclusivas(classe, permitida):
    assert classe.ferramentas_permitidas == {permitida}
    instancia = classe()
    assert not hasattr(instancia, "aprovar_solicitacao")
    assert not hasattr(instancia, "executar_automacao")
    # Nenhum executor genérico que aceite um nome livre de ferramenta.
    assert not hasattr(instancia, "call_tool")


@pytest.mark.parametrize("campo,valor", [("valor", False), ("parcelas", 1.5), ("taxa_juros_mensal", -1)])
def test_simulation_valida_antes_da_tool(campo, valor):
    ferramenta = Mock()
    with pytest.raises(ValueError):
        SimulationAgent(ferramenta).executar({**ARGS, campo: valor}, {})
    ferramenta.assert_not_called()


def test_simulation_pede_dados_sem_outras_ferramentas():
    ferramenta = Mock()
    resposta = SimulationAgent(ferramenta).executar({**ARGS, "taxa_juros_mensal": None}, {})
    assert resposta["informacoes_faltantes"] == ["taxa_juros_mensal"]
    ferramenta.assert_not_called()


def test_market_nao_aceita_url():
    consulta = Mock()
    assert MarketDataAgent(consulta).executar("Consulte http://localhost/privado", {})["tipo"] == "resposta_invalida"
    consulta.assert_not_called()


def test_especialistas_nao_recebem_historico_privado(monkeypatch):
    plano = {"intencao": "simular_credito", "argumentos": ARGS, "agentes": ["simulation"]}
    modelo = Mock(return_value=plano)
    monkeypatch.setattr(ollama_client, "consultar_modelo", modelo)
    executar = Mock(return_value={"tipo": "dados_incompletos", "mensagem": "Dados?"})
    monkeypatch.setattr(SimulationAgent, "executar", executar)
    historico = [{"papel": "user", "texto": "5 mil", "prompt_privado": "NAO_COMPARTILHAR"}]
    copia = deepcopy(historico)
    credit_agent.processar_mensagem("12 parcelas a 2%", historico, simulacao_id=10)
    assert historico == copia
    assert "NAO_COMPARTILHAR" not in repr(executar.call_args)
    assert "NAO_COMPARTILHAR" not in repr(modelo.call_args)
    assert executar.call_args.args[0] == ARGS


def test_migracao_preserva_metricas_antigas(tmp_path):
    caminho = tmp_path / "antigo.db"
    with sqlite3.connect(caminho) as conexao:
        conexao.execute("CREATE TABLE metricas (id INTEGER PRIMARY KEY, operacao TEXT, status TEXT, latencia_ms REAL, modelo TEXT, ferramenta TEXT, erro TEXT, criado_em TEXT)")
        conexao.execute("INSERT INTO metricas VALUES (1, 'teste', 'sucesso', 1, NULL, NULL, NULL, '2026-09-16')")
    database.inicializar_banco(caminho)
    database.inicializar_banco(caminho)
    assert database.listar_metricas(caminho_banco=caminho)[0]["operacao"] == "teste"
    assert database.obter_resumo_handoffs(caminho)["quantidade_handoffs"] == 0


def test_chat_composto_salva_uma_vez_e_mantem_sessao(monkeypatch):
    def modelo(mensagens, esquema):
        if "encontrou" in esquema["properties"]:
            contexto = json.loads(mensagens[-1]["content"])["contexto"]
            return {"encontrou": True, "resposta": contexto[0]["trecho"], "trechos_utilizados": [0]}
        return {"intencao": "simular_credito", "argumentos": ARGS, "agentes": ["knowledge", "simulation"]}
    fake = Mock(side_effect=modelo)
    monkeypatch.setattr(ollama_client, "consultar_modelo", fake)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    app.chat_input[0].set_value("O que é Tabela Price e quanto fica 5000 em 12x a 2%?").run()
    assert not app.exception
    assert app.chat_message[-1].metric[0].value == "R$ 472,80"
    assert any("KnowledgeAgent → SimulationAgent" in c.value for c in app.chat_message[-1].caption)
    assert len(database.listar_simulacoes()) == 1
    assert len(app.session_state.conversa_credito) == 2
    app.run()
    assert not app.exception
    assert fake.call_count == 2
    assert len(database.listar_simulacoes()) == 1
