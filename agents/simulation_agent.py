"""Especialista de simulação: valida argumentos e delega o cálculo."""
import math
from tools.credit_simulator import simular_credito
from agents.models import CAMPOS_SIMULACAO


class SimulationAgent:
    ferramentas_permitidas = frozenset({"simular_credito"})

    def __init__(self, ferramenta=None):
        self._simular = ferramenta or simular_credito

    def executar(self, argumentos, base):
        if not isinstance(argumentos, dict) or set(argumentos) != set(CAMPOS_SIMULACAO):
            raise ValueError("Argumentos de simulação inválidos.")
        for campo, valor in argumentos.items():
            if valor is None:
                continue
            if (type(valor) not in (int, float) or not math.isfinite(valor)
                    or (campo == "parcelas" and type(valor) is not int)
                    or (valor < 0 if campo == "taxa_juros_mensal" else valor <= 0)):
                raise ValueError("Dados de simulação inválidos.")
        base = {**base, "argumentos": {k: v for k, v in argumentos.items() if v is not None}}
        faltantes = [k for k in CAMPOS_SIMULACAO if argumentos[k] is None]
        if faltantes:
            perguntas = {"valor": "Qual é o valor solicitado em reais?", "parcelas": "Em quantas parcelas?",
                         "taxa_juros_mensal": "Qual é a taxa de juros mensal?"}
            return {**base, "tipo": "dados_incompletos", "informacoes_faltantes": faltantes,
                    "mensagem": perguntas[faltantes[0]]}
        try:
            resultado = self._simular(**argumentos)
        except ValueError as erro:
            return {**base, "tipo": "dados_invalidos", "mensagem": str(erro)}
        return {**base, "tipo": "simulacao_credito", "tool_utilizada": "simular_credito",
                "resultado": resultado, "mensagem": "Simulação concluída! Veja as condições calculadas:"}
