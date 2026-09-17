"""Whisper local: WAV limitado, temporário e sem downloads durante o chat."""
from functools import lru_cache
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
import wave

from monitoring.metrics import medir_operacao
from voice import ErroVoz

MODELO_STT = "faster-whisper-base"
REPOSITORIO_MODELO = "Systran/faster-whisper-base"
PASTA_MODELO = Path(__file__).resolve().parent / "models" / MODELO_STT
IDIOMA = "pt"
VOCABULARIO = "CreditAI. Tabela Price. Selic. Taxa de juros mensal. Parcelas."
MAX_BYTES = 10 * 1024 * 1024
MAX_SEGUNDOS = 60
_LOCK = Lock()


def validar_audio(dados, tipo_mime):
    """Valida conteúdo real, tamanho e duração antes de carregar o modelo."""
    if not isinstance(dados, bytes) or tipo_mime not in ("audio/wav", "audio/x-wav"):
        raise ErroVoz("Grave um áudio WAV pelo gravador do CreditAI.")
    if not dados or len(dados) > MAX_BYTES:
        raise ErroVoz("O áudio deve ter conteúdo e no máximo 10 MB.")
    try:
        with wave.open(io.BytesIO(dados), "rb") as audio:
            canais, largura, frequencia, quadros = audio.getparams()[:4]
            if (audio.getcomptype() != "NONE" or canais not in (1, 2) or largura != 2
                    or not 8000 <= frequencia <= 48000 or not 0 < quadros / frequencia <= MAX_SEGUNDOS):
                raise ErroVoz("Grave até 60 segundos de áudio WAV PCM de 16 bits.")
            if len(audio.readframes(quadros)) != quadros * canais * largura:
                raise ErroVoz("O áudio está incompleto. Grave novamente.")
    except (wave.Error, EOFError, ValueError, OverflowError) as erro:
        raise ErroVoz("Não consegui ler a gravação. Grave novamente pelo CreditAI.") from erro


@lru_cache(maxsize=1)
def carregar_modelo():
    if not (PASTA_MODELO / "model.bin").is_file():
        raise ErroVoz("O modelo de voz não está preparado. Execute python -m voice.speech_to_text --preparar na .venv.")
    from faster_whisper import WhisperModel
    return WhisperModel(str(PASTA_MODELO), device="cpu", compute_type="int8",
                        cpu_threads=4, num_workers=1, local_files_only=True)


@medir_operacao("speech_to_text", modelo=MODELO_STT)
def transcrever_audio(dados, tipo_mime="audio/wav"):
    validar_audio(dados, tipo_mime)
    try:
        with TemporaryDirectory(prefix="creditai-stt-") as pasta:
            caminho = Path(pasta) / "gravacao.wav"
            caminho.write_bytes(dados)
            with _LOCK:
                modelo = carregar_modelo()
                segmentos, _ = modelo.transcribe(str(caminho), language=IDIOMA,
                    beam_size=3, vad_filter=True, condition_on_previous_text=False,
                    initial_prompt=VOCABULARIO)
                # O gerador executa dentro do contexto para preservar o temporário.
                texto = " ".join(s.text.strip() for s in segmentos).strip()
        if not texto:
            raise ErroVoz("Não identifiquei fala na gravação. Tente novamente em um ambiente mais silencioso.")
        if len(texto) > 4000:
            raise ErroVoz("A transcrição ficou longa demais. Grave uma mensagem mais curta.")
        return texto
    except ErroVoz:
        raise
    except Exception as erro:
        raise ErroVoz("Não foi possível transcrever localmente. Verifique a instalação de voz e tente novamente.") from erro


def preparar_modelo():
    """Download explícito único; inferência nunca faz chamadas ao repositório."""
    from huggingface_hub import snapshot_download
    PASTA_MODELO.mkdir(parents=True, exist_ok=True)
    snapshot_download(REPOSITORIO_MODELO, local_dir=str(PASTA_MODELO),
                      allow_patterns=["model.bin", "config.json", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"])
    print("Modelo local preparado:", PASTA_MODELO)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preparar", action="store_true", required=True)
    parser.parse_args()
    preparar_modelo()
