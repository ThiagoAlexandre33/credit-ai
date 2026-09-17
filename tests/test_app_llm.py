"""Fluxo de múltiplas mensagens com modelo falso e banco temporário."""

from pathlib import Path
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from agent import ollama_client
from database import database


def test_conversa_completa_e_indisponibilidade(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "CAMINHO_BANCO", tmp_path / "conversa.db")
    modelo = Mock(side_effect=[
        {"intencao": "simular_credito", "argumentos": {"valor": 5000, "parcelas": None, "taxa_juros_mensal": None}},
        {"intencao": "simular_credito", "argumentos": {"valor": 5000, "parcelas": 12, "taxa_juros_mensal": None}},
        {"intencao": "simular_credito", "argumentos": {"valor": 5000, "parcelas": 12, "taxa_juros_mensal": 2}},
        ollama_client.OllamaIndisponivel(),
    ])
    monkeypatch.setattr(ollama_client, "consultar_modelo", modelo)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20).run()
    app.chat_input[0].set_value("Quero simular 5 mil").run()
    assert "Em quantas parcelas?" in app.chat_message[-1].markdown[0].value
    app.chat_input[0].set_value("12").run()
    assert "taxa de juros mensal" in app.chat_message[-1].markdown[0].value
    assert database.listar_simulacoes() == []
    app.chat_input[0].set_value("2%").run()
    assert not app.exception
    assert app.chat_message[-1].metric[0].value == "R$ 472,80"
    assert len(database.listar_simulacoes()) == 1
    assert len(modelo.call_args.args[0]) == 6
    app.run()
    assert modelo.call_count == 3
    assert len(database.listar_simulacoes()) == 1
    app.chat_input[0].set_value("Quero outra simulação").run()
    assert not app.exception
    assert "não está disponível" in app.chat_message[-1].markdown[0].value
    assert len(database.listar_simulacoes()) == 1
