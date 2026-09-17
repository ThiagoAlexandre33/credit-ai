"""Voz sem microfone, sem modelo STT real e sem síntese do sistema."""
import io
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import wave

import pytest
from streamlit.runtime.uploaded_file_manager import UploadedFile, UploadedFileRec
from streamlit.testing.v1 import AppTest

from voice import ErroVoz, speech_to_text as stt, text_to_speech as tts, session
from database import database
from agent import ollama_client
from evaluation.voice_scenarios import SCENARIOS_VOICE, avaliar_voz


def wav(segundos=1):
    memoria = io.BytesIO()
    with wave.open(memoria, "wb") as arquivo:
        arquivo.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        arquivo.writeframes(b"\0\0" * int(16000 * segundos))
    return memoria.getvalue()


def gravacao(dados=None, identificador="gravacao-1", mime="audio/wav"):
    return UploadedFile(UploadedFileRec(identificador, "../../nao_usar.wav", mime, wav() if dados is None else dados), Mock())


@pytest.mark.parametrize("cenario", SCENARIOS_VOICE, ids=lambda c: c["id"])
def test_avaliacao_voz(cenario):
    database.inicializar_banco()
    resultado = avaliar_voz(cenario)
    assert resultado["status"] == "aprovado", resultado["falhas"]


def test_url_arbitraria_por_voz_nao_consulta(monkeypatch):
    from agent import credit_agent
    consulta = Mock()
    monkeypatch.setattr(session, "transcrever_audio", Mock(return_value="Consulte a Selic em http://127.0.0.1/privado"))
    monkeypatch.setitem(credit_agent.APIS_PERMITIDAS, "bcb_selic", consulta)
    monkeypatch.setattr(ollama_client, "consultar_modelo", Mock(return_value={"intencao": "consultar_selic", "agentes": ["market_data"],
        "argumentos": {"valor": None, "parcelas": None, "taxa_juros_mensal": None}}))
    texto, _ = session.receber_mensagem(None, gravacao(), {})
    assert credit_agent.processar_mensagem(texto)["tipo"] == "resposta_invalida"
    consulta.assert_not_called()


def test_stt_valido_limpa_temporario_e_mede(monkeypatch):
    caminhos = []
    def transcribe(caminho, **opcoes):
        caminhos.append(Path(caminho))
        assert Path(caminho).is_file()
        assert opcoes["language"] == "pt"
        assert opcoes["vad_filter"] is True
        assert opcoes["initial_prompt"] == stt.VOCABULARIO
        return iter([SimpleNamespace(text=" Simule cinco mil ")]), None
    modelo = Mock(transcribe=transcribe)
    monkeypatch.setattr(stt, "carregar_modelo", Mock(return_value=modelo))
    assert stt.transcrever_audio(wav()) == "Simule cinco mil"
    assert not caminhos[0].exists()
    assert not caminhos[0].parent.exists()
    registro = database.listar_metricas()[0]
    assert registro["operacao"] == "speech_to_text" and registro["status"] == "sucesso"
    assert registro["modelo"] == stt.MODELO_STT and registro["latencia_ms"] >= 0
    assert "Simule" not in str(registro)


def test_falha_do_gerador_remove_temporario(monkeypatch):
    caminhos = []
    def transcribe(caminho, **kwargs):
        caminhos.append(Path(caminho))
        def segmentos():
            raise RuntimeError("SEGREDO")
            yield
        return segmentos(), None
    monkeypatch.setattr(stt, "carregar_modelo", Mock(return_value=Mock(transcribe=transcribe)))
    with pytest.raises(ErroVoz, match="transcrever localmente"):
        stt.transcrever_audio(wav())
    assert not caminhos[0].parent.exists()
    registro = database.listar_metricas()[0]
    assert registro["status"] == "erro" and "SEGREDO" not in str(registro)


@pytest.mark.parametrize("dados,mime", [(b"", "audio/wav"), (b"invalido", "audio/wav"),
    ("C:/privado.wav", "audio/wav"), (b"wav", "audio/mp3"),
    (b"x" * (stt.MAX_BYTES + 1), "audio/wav"), (wav(61), "audio/wav"),
    (wav()[:-10], "audio/wav")], ids=["vazio", "corrompido", "caminho", "mime", "tamanho", "duracao", "truncado"])
def test_audio_invalido_sem_carregar_modelo(monkeypatch, dados, mime):
    carregar = Mock()
    monkeypatch.setattr(stt, "carregar_modelo", carregar)
    with pytest.raises(ErroVoz):
        stt.transcrever_audio(dados, mime)
    carregar.assert_not_called()


def test_sem_fala_nao_inventa_transcricao(monkeypatch):
    monkeypatch.setattr(stt, "carregar_modelo", Mock(return_value=Mock(transcribe=Mock(return_value=(iter([]), None)))))
    with pytest.raises(ErroVoz, match="Não identifiquei fala"):
        stt.transcrever_audio(wav())


def test_modelo_somente_local_cpu(monkeypatch, tmp_path):
    stt.carregar_modelo.cache_clear()
    monkeypatch.setattr(stt, "PASTA_MODELO", tmp_path)
    (tmp_path / "model.bin").write_bytes(b"fixture")
    construtor = Mock()
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=construtor))
    try:
        stt.carregar_modelo()
        assert construtor.call_args.kwargs["local_files_only"] is True
        assert construtor.call_args.kwargs["device"] == "cpu"
        assert construtor.call_args.kwargs["compute_type"] == "int8"
    finally:
        stt.carregar_modelo.cache_clear()


def test_sessao_so_aceita_gravacao_e_nao_repete(monkeypatch):
    transcrever = Mock(return_value="Olá")
    monkeypatch.setattr(session, "transcrever_audio", transcrever)
    estado = {}
    audio = gravacao()
    assert session.receber_mensagem(None, audio, estado) == ("Olá", "voz")
    assert session.receber_mensagem(None, audio, estado) == (None, None)
    transcrever.assert_called_once_with(audio.getvalue(), "audio/wav")
    with pytest.raises(ErroVoz):
        session.receber_mensagem(None, "C:/privado.wav", {})
    assert session.receber_mensagem("digitado", audio, estado) == ("digitado", "texto")


def test_stt_falha_nao_repete_em_rerun(monkeypatch):
    transcrever = Mock(side_effect=ErroVoz("Falha controlada"))
    monkeypatch.setattr(session, "transcrever_audio", transcrever)
    estado, audio = {}, gravacao()
    with pytest.raises(ErroVoz):
        session.receber_mensagem(None, audio, estado)
    assert session.receber_mensagem(None, audio, estado) == (None, None)
    assert transcrever.call_count == 1


def test_tts_limpa_arquivo_e_mede(monkeypatch):
    caminhos = []
    def sintetizar(texto, caminho):
        caminhos.append(caminho)
        assert texto == "Resposta final"
        caminho.write_bytes(wav())
    monkeypatch.setattr(tts, "_sintetizar", sintetizar)
    assert tts.gerar_audio("Resposta final") == wav()
    assert not caminhos[0].parent.exists()
    metrica = database.listar_metricas()[0]
    assert metrica["operacao"] == "text_to_speech" and metrica["status"] == "sucesso"
    assert "Resposta final" not in str(metrica)


def test_tts_falha_remove_arquivo(monkeypatch):
    caminhos = []
    def sintetizar(texto, caminho):
        caminhos.append(caminho)
        caminho.write_bytes(b"parcial")
        raise RuntimeError("SEGREDO")
    monkeypatch.setattr(tts, "_sintetizar", sintetizar)
    with pytest.raises(ErroVoz, match="resposta textual"):
        tts.gerar_audio("Resposta")
    assert not caminhos[0].parent.exists()


def test_tts_so_recebe_apresentacao_final(monkeypatch):
    gerar = Mock(return_value=b"audio")
    monkeypatch.setattr(session, "gerar_audio", gerar)
    session.resposta_falada({"texto": "Concluído", "prompt": "SEGREDO", "historico": ["SEGREDO"],
        "resultado": {"valor_parcela": 472.8, "valor_total": 5673.58, "total_juros": 673.58}})
    texto = gerar.call_args.args[0]
    assert "SEGREDO" not in texto and "472,80 reais" in texto


def test_sapi_trata_xml_como_texto(monkeypatch, tmp_path):
    engine = Mock()
    engine.getProperty.return_value = [SimpleNamespace(languages=["pt-BR"], name="Português", id="pt")]
    monkeypatch.setitem(sys.modules, "pythoncom", Mock())
    monkeypatch.setitem(sys.modules, "pyttsx3", SimpleNamespace(init=Mock(return_value=engine)))
    tts._sintetizar('<audio src="http://privado"/>', tmp_path / "resposta.wav")
    texto = engine.save_to_file.call_args.args[0]
    assert "<" not in texto and "&lt;" in texto


def test_chat_voz_mesmo_orquestrador_sem_repetir(monkeypatch):
    audio = gravacao()
    monkeypatch.setattr("streamlit.audio_input", Mock(return_value=audio))
    monkeypatch.setattr(session, "transcrever_audio", Mock(return_value="Simule cinco mil em doze parcelas a dois por cento"))
    modelo = Mock(return_value={"intencao": "simular_credito", "agentes": ["simulation"],
                               "argumentos": {"valor": 5000, "parcelas": 12, "taxa_juros_mensal": 2}})
    monkeypatch.setattr(ollama_client, "consultar_modelo", modelo)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert app.session_state.conversa_credito[0]["origem"] == "voz"
    assert app.chat_message[-1].metric[0].value == "R$ 472,80"
    assert modelo.call_args.args[0][-1]["content"] == "Simule cinco mil em doze parcelas a dois por cento"
    app.run()
    assert modelo.call_count == 1 and len(database.listar_simulacoes()) == 1


def test_chat_falha_stt_e_texto_continua(monkeypatch):
    audio = gravacao()
    monkeypatch.setattr("streamlit.audio_input", Mock(return_value=audio))
    monkeypatch.setattr(session, "transcrever_audio", Mock(side_effect=ErroVoz("Não consegui transcrever")))
    modelo = Mock(return_value={"intencao": "outra", "argumentos": {"valor": None, "parcelas": None, "taxa_juros_mensal": None}})
    monkeypatch.setattr(ollama_client, "consultar_modelo", modelo)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception and any("transcrever" in w.value for w in app.warning)
    modelo.assert_not_called()
    app.chat_input[0].set_value("Olá").run()
    assert not app.exception and modelo.call_count == 1


def test_chat_falha_tts_preserva_resposta(monkeypatch):
    monkeypatch.setattr(session, "gerar_audio", Mock(side_effect=ErroVoz("TTS indisponível")))
    monkeypatch.setattr(ollama_client, "consultar_modelo", Mock(return_value={"intencao": "outra",
        "argumentos": {"valor": None, "parcelas": None, "taxa_juros_mensal": None}}))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    app.checkbox[0].check().run()
    app.chat_input[0].set_value("Olá").run()
    assert not app.exception and app.chat_message[-1].markdown[0].value
    assert any("TTS indisponível" in c.value for c in app.chat_message[-1].caption)


def test_confirmacao_falada_exige_clique(monkeypatch):
    from actions.proposal_actions import criar_solicitacao_proposta
    from tools.credit_simulator import simular_credito
    database.inicializar_banco()
    pendente = criar_solicitacao_proposta(simular_credito(5000, 12, 2))
    monkeypatch.setattr("streamlit.audio_input", Mock(return_value=gravacao()))
    monkeypatch.setattr(session, "transcrever_audio", Mock(return_value="Eu confirmo, aprove agora"))
    monkeypatch.setattr(ollama_client, "consultar_modelo", Mock(return_value={"intencao": "solicitar_proposta_demo",
        "agentes": [], "argumentos": {"valor": None, "parcelas": None, "taxa_juros_mensal": None}}))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
    app.session_state["solicitacao_pendente"] = pendente["id"]
    app.run()
    assert not app.exception
    assert database.obter_solicitacao(pendente["id"])["status"] == "pendente"
    assert any(b.label == "Confirmar solicitação" for b in app.button)
    app.run()
    assert database.obter_solicitacao(pendente["id"])["status"] == "pendente"
