"""Síntese offline SAPI5; devolve WAV para o navegador, sem tocar no servidor."""
import html
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
import wave

from monitoring.metrics import medir_operacao
from voice import ErroVoz

MODELO_TTS = "Windows-SAPI5"
MAX_CARACTERES = 4000
_LOCK = Lock()


def _sintetizar(texto, caminho):
    # COM deve ser inicializado na thread de execução do Streamlit.
    import pythoncom
    import pyttsx3
    pythoncom.CoInitialize()
    engine = None
    try:
        engine = pyttsx3.init(driverName="sapi5")
        vozes = engine.getProperty("voices")
        portugues = next((v for v in vozes if any(termo in str(v.languages).lower() + v.name.lower()
                          for termo in ("pt-br", "pt_br", "portugu", "brazil"))), None)
        if portugues is None:
            raise ErroVoz("Não há voz portuguesa offline instalada no Windows. A resposta textual continua disponível.")
        engine.setProperty("voice", portugues.id)
        engine.setProperty("rate", 175)
        # Impede interpretação de marcação de voz/XML recebida como texto.
        engine.save_to_file(html.escape(texto), str(caminho))
        engine.runAndWait()
    finally:
        if engine is not None:
            engine.stop()
            del engine
        pythoncom.CoUninitialize()


@medir_operacao("text_to_speech", modelo=MODELO_TTS)
def gerar_audio(texto):
    if not isinstance(texto, str) or not texto.strip() or len(texto) > MAX_CARACTERES:
        raise ErroVoz("A resposta falada requer um texto de até 4.000 caracteres.")
    try:
        with _LOCK, TemporaryDirectory(prefix="creditai-tts-") as pasta:
            caminho = Path(pasta) / "resposta.wav"
            _sintetizar(texto, caminho)
            if not caminho.is_file() or caminho.stat().st_size > 30 * 1024 * 1024:
                raise ErroVoz("Não foi possível gerar o áudio da resposta.")
            with wave.open(str(caminho), "rb") as audio:
                if audio.getnframes() == 0:
                    raise ErroVoz("A síntese não produziu áudio.")
            return caminho.read_bytes()
    except ErroVoz:
        raise
    except Exception as erro:
        raise ErroVoz("A saída falada está indisponível. A resposta textual continua disponível.") from erro
