"""Verifica integração e ausência de gravações duplicadas no chat."""

from pathlib import Path
from unittest.mock import patch
import sqlite3

import pytest
from streamlit.testing.v1 import AppTest

from database import database
from agent import credit_agent


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "CAMINHO_BANCO", tmp_path / "chat.db")
    processar_original = credit_agent.processar_mensagem
    monkeypatch.setattr(credit_agent, "processar_mensagem",
                        lambda mensagem, historico=None, **kwargs: processar_original(mensagem, usar_llm=False))
    return AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20
    ).run()


def test_chat_salva_uma_vez_e_preserva_formulario(app):
    app.chat_input[0].set_value("Quero simular 5000 reais em 12 parcelas com taxa de 2%").run()
    assert not app.exception
    assert len(app.chat_message) == 2
    assert app.chat_message[1].metric[0].value == "R$ 472,80"
    assert len(database.listar_simulacoes()) == 1
    app.run()
    assert len(app.chat_message) == 2
    assert len(database.listar_simulacoes()) == 1
    app.button[0].click().run()
    assert not app.exception
    assert len(app.chat_message) == 2
    assert len(database.listar_simulacoes()) == 2


@pytest.mark.parametrize(("mensagem", "esperado"), [
    ("Simular 5000 reais em 12 parcelas", "taxa de juros mensal"),
    ("Olá", "somente com simulações de crédito"),
    ("Simular -5000 reais em 12 parcelas a 2%", "maior que zero"),
])
def test_chat_sem_gravacao_para_pedidos_incompletos_ou_invalidos(app, mensagem, esperado):
    app.chat_input[0].set_value(mensagem).run()
    assert not app.exception
    assert esperado in app.chat_message[1].markdown[0].value
    assert database.listar_simulacoes() == []


def test_chat_falha_no_salvamento_preserva_resultado(app):
    with patch.object(database, "salvar_simulacao", side_effect=sqlite3.OperationalError("teste")):
        app.chat_input[0].set_value("Simular 5000 reais em 12 parcelas a 2%").run()
    assert not app.exception
    assert app.chat_message[1].metric[0].value == "R$ 472,80"
    assert "não foi salva" in app.chat_message[1].warning[0].value
    assert database.listar_simulacoes() == []
