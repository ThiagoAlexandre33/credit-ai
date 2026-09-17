"""Simulação de crédito com parcelas fixas pela Tabela Price."""

import math
from monitoring.metrics import medir_operacao


@medir_operacao("tool_call", ferramenta="simular_credito")
def simular_credito(valor, parcelas, taxa_juros_mensal):
    """Retorna uma simulação em reais; a taxa mensal é dada em porcentagem.

    O total e os juros usam a parcela antes do arredondamento. Apenas os
    valores monetários retornados são arredondados para duas casas decimais.
    """
    def validar_numero(numero, mensagem):
        if isinstance(numero, bool) or not isinstance(numero, (int, float)):
            raise ValueError(mensagem)
        try:
            numero = float(numero)
        except (OverflowError, ValueError):
            raise ValueError(mensagem) from None
        if not math.isfinite(numero):
            raise ValueError(mensagem)
        return numero

    valor = validar_numero(valor, "O valor solicitado deve ser um número finito maior que zero.")
    if valor <= 0:
        raise ValueError("O valor solicitado deve ser maior que zero.")
    if isinstance(parcelas, bool) or not isinstance(parcelas, int) or parcelas <= 0:
        raise ValueError("A quantidade de parcelas deve ser um número inteiro maior que zero.")
    taxa = validar_numero(
        taxa_juros_mensal,
        "A taxa de juros mensal deve ser um número finito e não pode ser negativa.",
    )
    if taxa < 0:
        raise ValueError("A taxa de juros mensal não pode ser negativa.")

    taxa_decimal = taxa / 100
    try:
        if taxa_decimal == 0:
            parcela = valor / parcelas
        else:
            # Equivalente a valor * i / (1 - (1 + i) ** (-n)).
            # log1p e expm1 preservam a precisão para taxas pequenas.
            denominador = -math.expm1(-parcelas * math.log1p(taxa_decimal))
            parcela = valor * (taxa_decimal / denominador)
        total = parcela * parcelas
    except OverflowError:
        raise ValueError("Os valores informados excedem o limite numérico da simulação.") from None
    if not math.isfinite(parcela) or not math.isfinite(total):
        raise ValueError("Os valores informados excedem o limite numérico da simulação.")

    return {
        "valor_solicitado": round(valor, 2),
        "parcelas": parcelas,
        "taxa_juros_mensal": taxa,
        "valor_parcela": round(parcela, 2),
        "valor_total": round(total, 2),
        "total_juros": round(total - valor, 2),
    }
