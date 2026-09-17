"""Contratos e limites do fluxo, independentes das respostas do modelo."""
from dataclasses import dataclass

AGENTES_PERMITIDOS = frozenset({"simulation", "knowledge", "market_data"})
MAX_HANDOFFS = 3
CAMPOS_SIMULACAO = ("valor", "parcelas", "taxa_juros_mensal")


@dataclass(frozen=True)
class EstadoCompartilhado:
    ultima_simulacao_id: int | None = None
    # Apenas números validados; histórico e prompts nunca chegam aos especialistas.
    dados_simulacao_pendentes: tuple = ()


def validar_plano(agentes):
    if (not isinstance(agentes, list) or len(agentes) > MAX_HANDOFFS
            or any(not isinstance(a, str) or a not in AGENTES_PERMITIDOS for a in agentes)
            or len(set(agentes)) != len(agentes)):
        raise ValueError("Plano de agentes não permitido.")
    return tuple(agentes)
