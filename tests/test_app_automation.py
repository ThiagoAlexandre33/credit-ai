"""Integração de chat, relatório e download seguro."""

from pathlib import Path
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from agent import ollama_client
from automations import report_automation
from database import database


def test_chat_relatorio_sem_repetir_em_rerun(monkeypatch):
    monkeypatch.setattr(ollama_client, "consultar_modelo", Mock(return_value={"intencao": "gerar_relatorio",
        "argumentos": {"valor": None, "parcelas": None, "taxa_juros_mensal": None}}))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20).run()
    app.button[0].click().run()
    app.chat_input[0].set_value("Crie um relatório da minha última simulação").run()
    assert not app.exception
    assert "Relatório gerado com sucesso" in app.chat_message[-1].markdown[0].value
    assert len(app.get("download_button")) == 1
    assert len(database.listar_execucoes_automacao()) == 1
    assert len(list(report_automation.PASTA_REPORTS.glob("*.md"))) == 1
    app.run()
    assert len(database.listar_execucoes_automacao()) == 1
    assert len(list(report_automation.PASTA_REPORTS.glob("*.md"))) == 1


def test_download_inseguro_nao_aparece(monkeypatch):
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20).run()
    app.session_state.conversa_credito = [{"papel": "assistant", "texto": "Teste", "automacao": {
        "status": "concluida", "simulacao_id": 1, "criado_em": "2026-09-16T12:00:00-03:00", "arquivo": "../../privado.md"}}]
    app.run()
    assert not app.exception
    assert len(app.get("download_button")) == 0
    assert any("não está disponível" in w.value for w in app.warning)
