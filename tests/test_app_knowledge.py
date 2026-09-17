"""A resposta educativa exibe fontes e não grava uma simulação."""

from pathlib import Path
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from agent import ollama_client
from database import database


def test_fontes_na_sessao_sem_gravacao_sqlite(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "CAMINHO_BANCO", tmp_path / "teste.db")
    modelo = Mock(side_effect=[
        {"intencao": "conhecimento_credito", "argumentos": {"valor": None, "parcelas": None, "taxa_juros_mensal": None}},
        {"encontrou": True, "resposta": "Na demonstração, a Tabela Price usa parcelas fixas.", "trechos_utilizados": [0]},
    ])
    monkeypatch.setattr(ollama_client, "consultar_modelo", modelo)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20).run()
    app.chat_input[0].set_value("Como funciona a Tabela Price?").run()
    assert not app.exception
    assert "Fontes da base:" in app.chat_message[-1].caption[0].value
    assert "faq_credito.md" in app.chat_message[-1].caption[0].value
    assert database.listar_simulacoes() == []
    app.run()
    assert modelo.call_count == 2
    assert "faq_credito.md" in app.chat_message[-1].caption[0].value
