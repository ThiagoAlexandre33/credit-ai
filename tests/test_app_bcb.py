"""Indicador na interface, sem alterar formulário ou SQLite de simulações."""

from pathlib import Path
from unittest.mock import Mock
from streamlit.testing.v1 import AppTest

from agent import credit_agent, ollama_client
from database import database
from tests.test_agent_bcb import INDICADOR, INTENCAO


def test_chat_selic_sem_mudar_taxa(monkeypatch):
    monkeypatch.setattr(ollama_client, "consultar_modelo", Mock(return_value=INTENCAO))
    api = Mock(return_value=INDICADOR)
    monkeypatch.setitem(credit_agent.APIS_PERMITIDAS, "bcb_selic", api)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20).run()
    app.chat_input[0].set_value("Qual a Selic?").run()
    assert not app.exception
    assert "13,25% ao ano" in app.chat_message[-1].markdown[0].value
    assert "1178" in app.chat_message[-1].caption[0].value
    assert app.number_input[2].value == 2.0
    assert database.listar_simulacoes() == []
    app.run()
    api.assert_called_once_with()
