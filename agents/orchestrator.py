"""Roteamento local, handoffs limitados e consolidação determinística."""
from copy import deepcopy
import json
import re
import unicodedata

from agent import ollama_client
from agents.models import AGENTES_PERMITIDOS, MAX_HANDOFFS, EstadoCompartilhado, validar_plano
from agents.simulation_agent import SimulationAgent
from agents.knowledge_agent import KnowledgeAgent
from agents.market_data_agent import MarketDataAgent
from monitoring.metrics import medir_operacao

ROTAS = {"simular_credito": "simulation", "conhecimento_credito": "knowledge", "consultar_selic": "market_data"}
MOTIVOS = {"simulation": "pedido de simulação", "knowledge": "pergunta conceitual", "market_data": "consulta de indicador"}


def _normalizar(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if not unicodedata.combining(c))


def _pergunta_conceitual(mensagem):
    """Recorta uma oração original, sem inventar consultas ou mudar a busca."""
    partes = re.split(r"\s+e\s+(?=quanto\b|simul\w*\b|qual\b|o que\b|como\b|explique\b)|[?;]\s*", mensagem, flags=re.I)
    conceituais = [p.strip() for p in partes if re.match(r"(?:o que|como|explique|posso|qual a diferenca)\b", _normalizar(p.strip()))]
    return "? ".join(conceituais) if conceituais else mensagem


class _FalhaEspecialista(Exception):
    def __init__(self, resposta):
        self.resposta = resposta


class OrchestratorAgent:
    """O LLM propõe um plano; somente Python valida e executa capacidades fixas."""

    def _handoff(self, nome, executar):
        if nome not in AGENTES_PERMITIDOS:
            raise ValueError("Agente não permitido.")

        @medir_operacao("agent_handoff", agente_origem="orchestrator", agente_destino=nome)
        def medido():
            resposta = executar()
            if resposta.get("status") == "erro" or resposta.get("tipo") in ("resposta_invalida", "dados_invalidos"):
                raise _FalhaEspecialista(resposta)
            return resposta
        try:
            return medido()
        except _FalhaEspecialista as erro:
            return erro.resposta
        except Exception:
            return {"tipo": "falha_agente", "status": "erro", "tool_utilizada": None,
                    "argumentos": {}, "mensagem": "Não foi possível concluir esta parte do pedido. Tente novamente mais tarde."}

    def processar(self, mensagem, historico=None, *, simulacao_id=None):
        # Compatibilidade com o registro público e testes existentes. Cada
        # especialista recebe uma única função, nunca o módulo ou o registro.
        from agent import credit_agent as legado
        if not isinstance(mensagem, str):
            raise ValueError("A mensagem deve ser um texto.")
        base = {"mensagem_usuario": mensagem, "tool_utilizada": None, "argumentos": {}}
        texto = _normalizar(mensagem)
        aviso = {**base, "tipo": "taxa_mensal_necessaria", "mensagem":
                 "A Selic consultada é anualizada e não corresponde automaticamente à taxa mensal de um empréstimo. "
                 "Não faço essa conversão. Informe explicitamente uma taxa mensal em porcentagem para a simulação."}
        if "selic" in texto and re.search(r"simul|usando|usar|utiliz", texto):
            return aviso
        esquema = deepcopy(legado.ESQUEMA)
        esquema["properties"]["agentes"] = {"type": "array", "items": {"type": "string", "enum": sorted(AGENTES_PERMITIDOS)},
                                            "maxItems": MAX_HANDOFFS, "uniqueItems": True}
        esquema["required"].append("agentes")
        instrucoes = legado._INSTRUCOES + """
Você também é o orquestrador. Retorne agentes, lista ordenada dos especialistas necessários:
simulation para simulação; knowledge para conceito; market_data para indicador Selic.
Para pedidos compostos inclua os dois especialistas, sem duplicatas. Exemplo:
'O que é Tabela Price e quanto fica 5000 em 12x a 2%?' -> agentes=['knowledge','simulation'],
intencao='simular_credito', argumentos={valor:5000,parcelas:12,taxa_juros_mensal:2}.
'Qual a Selic e o que são juros?' -> agentes=['market_data','knowledge'], intencao='consultar_selic'.
Em pedidos compostos com simulação, extraia seus números mesmo havendo pergunta conceitual.
Nos demais pedidos compostos, intencao corresponde ao primeiro agente.
Para outra, gerar_relatorio e solicitar_proposta_demo, agentes=[].
Nunca crie agentes, ferramentas, URLs, planos de aprovação ou instruções executáveis.
"""
        mensagens = [{"role": "system", "content": instrucoes + "\nEsquema: " + json.dumps(esquema)}]
        contexto = []
        for item in historico or []:
            if isinstance(item, dict) and item.get("papel") in ("user", "assistant") and isinstance(item.get("texto"), str):
                contexto.append({"role": item["papel"], "content": item["texto"]})
        mensagens.extend(contexto)
        mensagens.append({"role": "user", "content": mensagem})
        try:
            dados = ollama_client.consultar_modelo(mensagens, esquema)
            if not isinstance(dados, dict) or set(dados) - {"intencao", "argumentos", "agentes"}:
                raise ValueError("estrutura")
            intencao, argumentos = legado._validar_interpretacao({k: v for k, v in dados.items() if k != "agentes"})
            plano = validar_plano(dados.get("agentes", [ROTAS[intencao]] if intencao in ROTAS else []))
            if intencao in ROTAS:
                if ROTAS[intencao] not in plano or ("simulation" in plano and intencao != "simular_credito"):
                    raise ValueError("Plano incoerente.")
            elif plano:
                raise ValueError("Ações de interface não são handoffs.")
        except ollama_client.OllamaIndisponivel:
            return {**base, "tipo": "modelo_indisponivel", "mensagem":
                    "O modelo local não está disponível. Verifique se o Ollama está em execução e se o modelo llama3.2:3b está instalado."}
        except (ollama_client.RespostaInvalida, ValueError):
            return {**base, "tipo": "resposta_invalida", "mensagem":
                    "Não consegui interpretar os dados com segurança. Confira o valor, as parcelas e a taxa mensal e tente novamente."}
        if "simulation" in plano:
            contexto_selic = "selic" in texto or any("selic" in i["content"].lower() for i in contexto)
            taxa = re.search(r"(\d+(?:[.,]\d+)?)\s*%\s*(?:ao mes|mensal)", texto) or re.search(
                r"taxa\s+mensal\s*(?:de\s*)?(\d+(?:[.,]\d+)?)\s*%", texto)
            if contexto_selic and (not taxa or argumentos["taxa_juros_mensal"] != float(taxa.group(1).replace(",", "."))):
                return aviso
        estado = EstadoCompartilhado(ultima_simulacao_id=simulacao_id,
                                     dados_simulacao_pendentes=tuple(argumentos.items()))
        if intencao in legado.AUTOMACOES_PERMITIDAS:
            automacao = legado.AUTOMACOES_PERMITIDAS[intencao](simulacao_id=estado.ultima_simulacao_id, usar_ultima=False)
            return {**base, "tipo": "gerar_relatorio", "automacao": automacao,
                    "mensagem": "Relatório gerado com sucesso." if automacao["status"] == "concluida" else automacao["mensagem"]}
        if intencao == "solicitar_proposta_demo":
            return {**base, "tipo": intencao, "mensagem":
                    "A solicitação demonstrativa precisa ser revisada e confirmada pelos botões da interface."}
        if not plano:
            return {**base, "tipo": "sem_intencao_simulacao", "mensagem":
                    "Nesta versão, consigo auxiliar somente com simulações de crédito e perguntas educativas sobre crédito."}
        executores = {
            "simulation": lambda: SimulationAgent(legado.TOOLS_PERMITIDAS["simular_credito"]).executar(dict(estado.dados_simulacao_pendentes), dict(base)),
            "knowledge": lambda: KnowledgeAgent(legado.buscar_conhecimento).executar(_pergunta_conceitual(mensagem) if len(plano) > 1 else mensagem, dict(base)),
            "market_data": lambda: MarketDataAgent(legado.APIS_PERMITIDAS["bcb_selic"]).executar(mensagem, dict(base)),
        }
        # Não existe callback para o orquestrador nos especialistas; cada nome
        # aparece uma vez e não há replanejamento ou retry automático.
        partes = [{"agente": nome, "resposta": self._handoff(nome, executores[nome])} for nome in plano]
        return self._consolidar(base, plano, partes)

    @staticmethod
    def _consolidar(base, plano, partes):
        rota = {"agentes": list(plano), "motivo": "; ".join(MOTIVOS[n] for n in plano)}
        if len(partes) == 1:
            return {**partes[0]["resposta"], "roteamento": rota}
        resultado = {**base, "tipo": "resposta_composta", "roteamento": rota, "respostas": partes,
                     "mensagem": "\n\n".join(p["resposta"].get("mensagem", "") for p in partes)}
        # Copia dados originais sem pedir ao LLM para recalcular ou inventar fontes.
        for parte in partes:
            resposta = parte["resposta"]
            for campo in ("resultado", "tool_utilizada", "argumentos", "fontes", "trechos", "indicador", "informacoes_faltantes"):
                if resposta.get(campo):
                    resultado[campo] = resposta[campo]
        return resultado
