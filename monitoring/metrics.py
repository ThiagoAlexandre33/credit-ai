"""Medição monotônica de operações, sem argumentos, respostas ou tracebacks."""

from datetime import datetime
from functools import wraps
import sqlite3
import time

from database import database


def medir_operacao(operacao, *, modelo=None, ferramenta=None, status_sucesso="sucesso", agente_origem=None, agente_destino=None):
    """Decora uma operação preservando seu retorno e suas exceções.

    A latência exclui a gravação da métrica. Falhas de persistência não derrubam
    a operação principal. Erros usam códigos fixos, nunca o texto da exceção.
    """
    def decorar(funcao):
        @wraps(funcao)
        def executar(*args, **kwargs):
            inicio = time.perf_counter()
            status, erro = status_sucesso, None
            try:
                return funcao(*args, **kwargs)
            except Exception as excecao:
                status = "erro"
                # Não registra nem mesmo nomes arbitrários de classes externas.
                if isinstance(excecao, ValueError):
                    erro = "dados_invalidos"
                elif type(excecao).__name__ == "OllamaIndisponivel":
                    erro = "ollama_indisponivel"
                elif type(excecao).__name__ == "RespostaInvalida":
                    erro = "resposta_invalida"
                elif isinstance(excecao, OSError):
                    erro = "falha_de_acesso"
                else:
                    erro = "falha_na_operacao"
                raise
            finally:
                metrica = {
                    "operacao": operacao, "status": status,
                    "latencia_ms": round((time.perf_counter() - inicio) * 1000, 2),
                    "modelo": modelo, "ferramenta": ferramenta, "erro": erro,
                    "criado_em": datetime.now().astimezone().isoformat(),
                }
                if agente_origem is not None:
                    metrica.update(agente_origem=agente_origem, agente_destino=agente_destino)
                try:
                    database.salvar_metrica(metrica)
                except (sqlite3.Error, OSError):
                    pass  # Monitoramento indisponível não substitui o resultado original.
        return executar
    return decorar
