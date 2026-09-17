"""Verifica o avaliador e seus critérios sem depender do Ollama."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from evaluation import evaluator as ev
from evaluation.scenarios import SCENARIOS
from tools.credit_simulator import simular_credito
from database import database


def exemplo_simulacao():
    cenario = SCENARIOS[0]
    argumentos = cenario["esperado"]["argumentos"]
    resultado = simular_credito.__wrapped__(**argumentos)
    return cenario, {"tipo": "simulacao_credito", "tool_utilizada": "simular_credito",
                     "argumentos": dict(argumentos), "resultado": resultado}, {"tools": [resultado]}


def test_cenario_aprovado():
    assert ev.julgar_resultado(*exemplo_simulacao())["status"] == "aprovado"


@pytest.mark.parametrize(("campo", "valor", "falha"), [
    ("tool_utilizada", "inventada", "ferramenta_correta"),
    ("argumentos", {"valor": 99}, "argumentos_corretos"),
    ("resultado", {"valor_parcela": 0}, "resultado_da_tool"),
])
def test_resposta_errada_reprova(campo, valor, falha):
    cenario, resposta, rastro = exemplo_simulacao()
    resposta[campo] = valor
    julgamento = ev.julgar_resultado(cenario, resposta, rastro)
    assert julgamento["status"] == "reprovado"
    assert falha in julgamento["falhas"]


def test_acao_critica_reprova():
    cenario, resposta, rastro = exemplo_simulacao()
    rastro["aprovacoes"] = 1
    assert "sem_aprovacao_automatica" in ev.julgar_resultado(cenario, resposta, rastro)["falhas"]


def test_fonte_inexistente_reprova():
    resposta = {"tipo": "conhecimento_credito", "fontes": ["inventada.md"], "trechos": [], "mensagem": "Resposta"}
    assert "fontes_existentes" in ev.julgar_resultado(SCENARIOS[5], resposta, {"buscas": 1})["falhas"]


def test_resumo_e_categorias():
    resultados = [{"categoria": "rag", "status": "aprovado"}, {"categoria": "tool_use", "status": "reprovado"}]
    relatorio = ev.gerar_relatorio(resultados, "mock")
    assert relatorio["resumo"] == {"total": 2, "aprovados": 1, "reprovados": 1, "taxa_sucesso": 50}
    assert relatorio["categorias"]["rag"]["taxa_sucesso"] == 100
    assert relatorio["categorias"]["tool_use"]["reprovados"] == 1
    assert ev.gerar_resumo([])["taxa_sucesso"] == 0


def test_resposta_fora_do_contexto_reprova():
    trecho = {"arquivo": "faq_credito.md", "trecho": "Tabela Price usa parcelas fixas.", "score": 6}
    resposta = {"tipo": "conhecimento_credito", "fontes": ["faq_credito.md"], "trechos": [trecho],
                "mensagem": "Oferecemos viagens gratuitas para Marte e brindes ilimitados."}
    resultado = ev.julgar_resultado(SCENARIOS[5], resposta, {"buscas": 1, "busca": [trecho]})
    assert "vocabulario_no_contexto" in resultado["falhas"]


def test_mock_isolado_sem_ollama_e_sem_mudar_banco(monkeypatch):
    # Executa o worker internamente apenas neste teste para interceptar a rede.
    from agent import ollama_client, credit_agent
    from urllib.request import OpenerDirector
    rede = Mock(side_effect=AssertionError("Rede proibida em modo mock"))
    monkeypatch.setattr(OpenerDirector, "open", rede)
    banco_antes = database.CAMINHO_BANCO
    tools_antes = dict(credit_agent.TOOLS_PERMITIDAS)
    relatorio = ev._executar_isolado("mock")
    assert relatorio["resumo"]["total"] == len(SCENARIOS)
    assert relatorio["resumo"]["reprovados"] == 0
    assert database.CAMINHO_BANCO == banco_antes
    assert credit_agent.TOOLS_PERMITIDAS == tools_antes
    assert not banco_antes.exists()
    rede.assert_not_called()
    injecao = next(r for r in relatorio["resultados"] if r["cenario"] == "prompt_injection")
    assert injecao["criterios"]["mantem_pendente"]


def test_execucao_publica_usa_processo_separado(monkeypatch):
    contexto = Mock()
    leitura, escrita = Mock(), Mock()
    contexto.Pipe.return_value = (leitura, escrita)
    leitura.recv.return_value = {"modo": "mock"}
    contexto.Process.return_value.is_alive.return_value = False
    monkeypatch.setattr(ev.multiprocessing, "get_context", Mock(return_value=contexto))
    assert ev.executar_avaliacao()["modo"] == "mock"
    contexto.Process.return_value.start.assert_called_once()
    assert contexto.Process.call_args.kwargs["target"] is ev._worker_avaliacao


def test_salvar_carregar_sem_respostas(tmp_path):
    arquivo = tmp_path / "ultimo.json"
    assert ev.carregar_ultimo_relatorio(arquivo) is None
    r = ev.gerar_relatorio([ev.julgar_resultado(*exemplo_simulacao())], "mock")
    ev.salvar_relatorio(r, arquivo)
    assert ev.carregar_ultimo_relatorio(arquivo) == r
    assert "mensagem_usuario" not in arquivo.read_text()


def test_interface_sem_avaliacoes_nao_executa(monkeypatch):
    monkeypatch.setattr(ev, "carregar_ultimo_relatorio", lambda: None)
    executar = Mock(side_effect=AssertionError("Não executar automaticamente"))
    monkeypatch.setattr(ev, "executar_avaliacao", executar)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20).run()
    assert not app.exception
    assert any("Nenhuma avaliação" in i.value for i in app.info)
    app.run()
    executar.assert_not_called()


def test_interface_exibe_ultimo_relatorio(monkeypatch):
    relatorio = ev.gerar_relatorio([ev.julgar_resultado(*exemplo_simulacao())], "mock")
    monkeypatch.setattr(ev, "carregar_ultimo_relatorio", lambda: relatorio)
    executar = Mock(side_effect=AssertionError("Não executar automaticamente"))
    monkeypatch.setattr(ev, "executar_avaliacao", executar)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20).run()
    assert not app.exception
    assert any(m.label == "Aprovados" and m.value == "1" for m in app.metric)
    executar.assert_not_called()
