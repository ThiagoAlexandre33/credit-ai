"""Adaptação do gravador à entrada textual existente, sem executar agentes."""
from streamlit.runtime.uploaded_file_manager import UploadedFile

from voice import ErroVoz
from voice.speech_to_text import MAX_BYTES, transcrever_audio
from voice.text_to_speech import gerar_audio


def receber_mensagem(texto, gravacao, estado):
    """Uma gravação é consumida uma vez, inclusive quando a transcrição falha."""
    if texto:
        # Se ambos chegarem no mesmo rerun, mantém texto e descarta áudio concorrente.
        if isinstance(gravacao, UploadedFile):
            estado["audio_processado"] = gravacao.file_id
        return texto, "texto"
    if gravacao is None:
        return None, None
    if not isinstance(gravacao, UploadedFile):
        raise ErroVoz("Utilize o gravador de áudio do CreditAI.")
    identificador = gravacao.file_id
    if estado.get("audio_processado") == identificador:
        return None, None
    estado["audio_processado"] = identificador
    if gravacao.size > MAX_BYTES:
        raise ErroVoz("A gravação ultrapassa o limite de 10 MB.")
    return transcrever_audio(gravacao.getvalue(), gravacao.type), "voz"


def resposta_falada(entrada):
    """Seleciona só a apresentação final: nunca prompts, histórico ou JSON privado."""
    texto = entrada["texto"]
    if "resultado" in entrada:
        resultado = entrada["resultado"]
        def reais(valor):
            return f"{valor:.2f}".replace(".", ",") + " reais"
        texto += (f' Parcela: {reais(resultado["valor_parcela"])}.'
                  f' Valor total: {reais(resultado["valor_total"])}.'
                  f' Juros: {reais(resultado["total_juros"])}.')
    return gerar_audio(texto)
