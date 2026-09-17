"""Interface web do simulador de crédito CreditAI."""

from datetime import datetime
from sqlite3 import Error as ErroBanco

import streamlit as st

from agent.credit_agent import processar_mensagem
from actions.proposal_actions import criar_solicitacao_proposta, aprovar_solicitacao, cancelar_solicitacao
from database.database import obter_solicitacao, listar_solicitacoes
from database.database import inicializar_banco, listar_simulacoes, salvar_simulacao
from database.database import listar_metricas, obter_resumo_metricas, obter_resumo_handoffs
from tools.credit_simulator import simular_credito
from evaluation.evaluator import executar_avaliacao, salvar_relatorio, carregar_ultimo_relatorio
from automations.report_automation import ler_relatorio_seguro
from database.database import listar_execucoes_automacao
from voice import ErroVoz
from voice.session import receber_mensagem, resposta_falada


def formatar_numero_br(valor):
    """Formata números para exibição, preservando os dados da simulação."""
    return f"{valor:,.2f}".translate(str.maketrans({",": ".", ".": ","}))


def formatar_reais(valor):
    return f"R$ {formatar_numero_br(valor)}"


def salvar_resultado(resultado, banco_disponivel):
    """Compartilha o tratamento de salvamento entre formulário e chat."""
    st.session_state.ultima_simulacao = None
    if banco_disponivel:
        try:
            identificador = salvar_simulacao(resultado)
        except ErroBanco:
            pass
        else:
            st.session_state.ultima_simulacao = {**resultado, "id": identificador}
            return True
    return False


st.set_page_config(page_title="CreditAI | Simulação de crédito", page_icon="💳", layout="centered")

st.title("CreditAI")
st.markdown("### Assistente Inteligente de Crédito")
st.caption("Projeto de portfólio • Conversa com modelo local e cálculos pela ferramenta Python.")
st.divider()

banco_disponivel = True
try:
    inicializar_banco()
except ErroBanco:
    banco_disponivel = False
    st.warning("O banco de dados está indisponível. As simulações não poderão ser salvas agora.")

st.header("Simulação de crédito")
st.write("Informe as condições para calcular parcelas fixas pela Tabela Price.")

with st.form("simulacao_credito"):
    valor = st.number_input(
        "Valor solicitado (R$)", min_value=0.0, value=5000.0, step=100.0, format="%.2f"
    )
    coluna_parcelas, coluna_taxa = st.columns(2)
    with coluna_parcelas:
        parcelas = st.number_input("Número de parcelas", min_value=1, value=12, step=1)
    with coluna_taxa:
        taxa = st.number_input(
            "Taxa de juros mensal (%)", min_value=0.0, value=2.0, step=0.1, format="%.2f"
        )
    simular = st.form_submit_button("Simular crédito", type="primary", use_container_width=True)

if simular:
    try:
        resultado = simular_credito(valor, parcelas, taxa)
    except ValueError as erro:
        st.error(f"Não foi possível simular o crédito. {erro} Confira os campos e tente novamente.")
    else:
        if salvar_resultado(resultado, banco_disponivel):
            st.success("Simulação salva no histórico.")
        else:
            st.warning("A simulação foi calculada, mas não foi salva. Tente novamente mais tarde.")
        st.subheader("Resultado da simulação")
        with st.container(border=True):
            st.metric("Valor da parcela", formatar_reais(resultado["valor_parcela"]))

        coluna_valor, coluna_quantidade, coluna_juros = st.columns(3)
        coluna_valor.metric("Valor solicitado", formatar_reais(resultado["valor_solicitado"]))
        coluna_quantidade.metric("Número de parcelas", resultado["parcelas"])
        coluna_juros.metric(
            "Taxa mensal", f'{formatar_numero_br(resultado["taxa_juros_mensal"])}% ao mês'
        )

        coluna_total, coluna_total_juros = st.columns(2)
        coluna_total.metric("Valor total pago", formatar_reais(resultado["valor_total"]))
        coluna_total_juros.metric("Total de juros", formatar_reais(resultado["total_juros"]))
        st.caption(
            "Os totais são calculados antes do arredondamento da parcela. "
            "Por isso, pode haver uma pequena diferença ao multiplicar a parcela exibida."
        )

        with st.expander("Ver resultado estruturado"):
            st.json(resultado)

st.divider()
st.header("Assistente de crédito")
st.caption("Modelo local: llama3.2:3b via Ollama. Sem serviços de IA pagos.")
st.write('Exemplo: "Quero simular 5 mil reais em 12 parcelas com taxa de 2%"')
st.write('Você também pode perguntar: "Como funciona a Tabela Price?"')
st.caption('Para consultar o indicador público do Banco Central, pergunte: "Qual é a Selic?"')
st.caption('Para baixar um resumo, peça: "Crie um relatório da minha última simulação."')
st.caption('Após simular, diga "Quero seguir com essa proposta" para preparar uma solicitação demonstrativa.')
st.caption("As explicações usam documentos locais fictícios e educativos, não políticas de bancos.")
st.caption(
    "Você pode completar os dados ao longo da conversa. A conversa fica apenas nesta sessão; "
    "as simulações são armazenadas no SQLite."
)
if "conversa_credito" not in st.session_state:
    st.session_state.conversa_credito = []

# O processamento e o salvamento ocorrem somente no envio de uma nova mensagem.
# Reexibir a conversa em um rerun não chama novamente as ferramentas.
with st.container():
    texto_digitado = st.chat_input("Peça uma simulação ou tire uma dúvida sobre crédito")
    gravacao = st.audio_input("Ou fale com o CreditAI", sample_rate=16000, key="gravacao_credito")
    st.caption("Voz local: grave até 60 segundos (10 MB). A transcrição é enviada ao mesmo assistente. Aprovações exigem clique nos botões.")
    habilitar_tts = st.checkbox("Habilitar resposta falada (local)", value=False)
mensagem, origem = None, None
try:
    if gravacao is not None and not texto_digitado and st.session_state.get("audio_processado") != getattr(gravacao, "file_id", None):
        with st.spinner("Transcrevendo áudio localmente..."):
            mensagem, origem = receber_mensagem(texto_digitado, gravacao, st.session_state)
    else:
        mensagem, origem = receber_mensagem(texto_digitado, gravacao, st.session_state)
except ErroVoz as erro:
    st.warning(str(erro))
if mensagem:
    if origem == "voz":
        st.info("Transcrição: " + mensagem)
    with st.spinner("Interpretando com o modelo local..."):
        resposta = processar_mensagem(mensagem, historico=st.session_state.conversa_credito,
                                      simulacao_id=(st.session_state.get("ultima_simulacao") or {}).get("id"))
    st.session_state.conversa_credito.append({"papel": "user", "texto": mensagem, "origem": origem})
    entrada = {"papel": "assistant"}
    if "resultado" in resposta and resposta["tipo"] in ("simulacao_credito", "resposta_composta"):
        entrada.update(
            texto=resposta.get("mensagem", "Simulação concluída! Veja as condições calculadas:"),
            resultado=resposta["resultado"],
            salvo=salvar_resultado(resposta["resultado"], banco_disponivel),
        )
    elif resposta["tipo"] == "solicitar_proposta_demo":
        if st.session_state.get("solicitacao_pendente"):
            entrada["texto"] = "Já existe uma solicitação pendente. Revise os dados e use os botões abaixo."
        elif not st.session_state.get("ultima_simulacao"):
            entrada["texto"] = "Faça primeiro uma simulação nesta sessão e salve-a no histórico."
        else:
            try:
                solicitacao = criar_solicitacao_proposta(st.session_state.ultima_simulacao)
            except (ErroBanco, ValueError):
                entrada["texto"] = "Não foi possível preparar a solicitação demonstrativa. Tente novamente."
            else:
                st.session_state.solicitacao_pendente = solicitacao["id"]
                entrada["texto"] = (
                    "Preparei uma solicitação demonstrativa baseada na sua simulação. "
                    "Nenhuma ação foi executada ainda. Revise os dados abaixo e confirme para continuar."
                )
    elif resposta["tipo"] == "dados_incompletos":
        entrada["texto"] = resposta["mensagem"]
    elif resposta["tipo"] == "sem_intencao_simulacao":
        entrada["texto"] = (
            "Nesta versão, consigo auxiliar somente com simulações de crédito e perguntas educativas sobre crédito. "
            "Peça uma simulação ou consulte a base local."
        )
    else:
        entrada["texto"] = resposta["mensagem"]
    if resposta.get("automacao"):
        entrada["automacao"] = resposta["automacao"]
    if resposta.get("indicador"):
        entrada["indicador"] = resposta["indicador"]
    if resposta.get("fontes"):
        entrada["fontes"] = resposta["fontes"]
        entrada["trechos"] = resposta["trechos"]
    if resposta.get("roteamento"):
        entrada["roteamento"] = resposta["roteamento"]
    if habilitar_tts:
        with st.spinner("Gerando resposta falada localmente..."):
            try:
                entrada["audio_resposta"] = resposta_falada(entrada)
            except ErroVoz as erro:
                entrada["aviso_voz"] = str(erro)
    st.session_state.conversa_credito.append(entrada)

for indice_mensagem, entrada in enumerate(st.session_state.conversa_credito):
    with st.chat_message(entrada["papel"]):
        st.write(entrada["texto"])
        if entrada.get("origem") == "voz":
            st.caption("Mensagem transcrita da gravação")
        if entrada.get("audio_resposta"):
            st.audio(entrada["audio_resposta"], format="audio/wav")
        if entrada.get("aviso_voz"):
            st.caption(entrada["aviso_voz"])
        if entrada.get("indicador"):
            st.caption("Fonte: Banco Central do Brasil • Série SGS: 1178 • Unidade: % ao ano")
        if entrada.get("automacao", {}).get("status") == "concluida":
            automacao = entrada["automacao"]
            st.caption(f'Simulação #{automacao["simulacao_id"]} • Status: {automacao["status"]}')
            st.caption("Data: " + datetime.fromisoformat(automacao["criado_em"]).strftime("%d/%m/%Y %H:%M:%S"))
            try:
                conteudo_relatorio = ler_relatorio_seguro(automacao["arquivo"])
                nome_relatorio = automacao["arquivo"].split("/")[-1]
                st.caption("Arquivo: " + nome_relatorio)
                st.download_button("Baixar relatório Markdown", data=conteudo_relatorio,
                                   file_name=nome_relatorio, mime="text/markdown",
                                   key=f"download_relatorio_{indice_mensagem}", on_click="ignore")
            except (OSError, ValueError):
                st.warning("O arquivo do relatório não está disponível para download.")
        if entrada.get("fontes"):
            st.caption("Fontes da base: " + ", ".join(entrada["fontes"]))
            with st.expander("Ver trechos da base"):
                for trecho in entrada["trechos"]:
                    st.caption(trecho["arquivo"])
                    st.text(trecho["trecho"])
        if "resultado" in entrada:
            resultado_chat = entrada["resultado"]
            st.metric("Valor da parcela", formatar_reais(resultado_chat["valor_parcela"]))
            st.write(f'Valor total: {formatar_reais(resultado_chat["valor_total"])}')
            st.write(f'Total de juros: {formatar_reais(resultado_chat["total_juros"])}')
            st.caption("Ferramenta utilizada: simular_credito")
            if entrada["salvo"]:
                st.success("Simulação salva no histórico.")
            else:
                st.warning("A simulação foi calculada, mas não foi salva. Tente novamente mais tarde.")
        if entrada.get("roteamento", {}).get("agentes"):
            nomes = {"simulation": "SimulationAgent", "knowledge": "KnowledgeAgent", "market_data": "MarketDataAgent"}
            st.caption("Fluxo: " + " → ".join(nomes[n] for n in entrada["roteamento"]["agentes"] if n in nomes))

st.divider()
st.header("Solicitações demonstrativas")
st.caption("Esta funcionalidade é apenas demonstrativa e não representa contratação real de crédito.")
if banco_disponivel:
    try:
        identificador = st.session_state.get("solicitacao_pendente")
        pendente = obter_solicitacao(identificador) if identificador else None
        if pendente and pendente["status"] == "pendente":
            with st.container(border=True):
                st.write(f'Solicitação #{pendente["id"]} — pendente')
                st.write(f'Valor: {formatar_reais(pendente["valor_solicitado"])}')
                st.write(f'Parcelas: {pendente["parcelas"]}')
                st.write(f'Taxa: {formatar_numero_br(pendente["taxa_juros_mensal"])}% ao mês')
                st.caption("Nenhum envio, contratação ou movimentação financeira será realizado.")
                confirmar, cancelar = st.columns(2)
                # A autorização vem exclusivamente dos widgets, nunca do texto do chat.
                if confirmar.button("Confirmar solicitação", key=f"confirmar_{identificador}"):
                    aprovar_solicitacao(identificador, confirmacao_humana=True)
                    st.session_state.solicitacao_pendente = None
                    st.session_state.aviso_solicitacao = "Solicitação aprovada e registrada localmente. Nenhum envio real foi realizado."
                    st.rerun()
                if cancelar.button("Cancelar", key=f"cancelar_{identificador}"):
                    cancelar_solicitacao(identificador, confirmacao_humana=True)
                    st.session_state.solicitacao_pendente = None
                    st.session_state.aviso_solicitacao = "Solicitação demonstrativa cancelada."
                    st.rerun()
        elif identificador:
            st.session_state.solicitacao_pendente = None
        if st.session_state.get("aviso_solicitacao"):
            st.info(st.session_state.pop("aviso_solicitacao"))
        solicitacoes = listar_solicitacoes()
        if solicitacoes:
            st.dataframe([{
                "ID": s["id"], "Valor": formatar_reais(s["valor_solicitado"]),
                "Parcelas": s["parcelas"], "Status": s["status"],
                "Data": datetime.fromisoformat(s["criado_em"]).strftime("%d/%m/%Y %H:%M:%S"),
            } for s in solicitacoes], hide_index=True, width="stretch")
        else:
            st.caption("Nenhuma solicitação demonstrativa registrada.")
    except (ErroBanco, ValueError):
        st.warning("Não foi possível atualizar as solicitações. Nenhuma confirmação deve ser presumida; consulte o status antes de tentar novamente.")

st.divider()
st.header("Histórico de simulações")
st.caption("Últimas 10 simulações, da mais recente para a mais antiga.")
if banco_disponivel:
    try:
        historico = listar_simulacoes(limite=10)
    except ErroBanco:
        st.warning("Não foi possível carregar o histórico. Tente novamente mais tarde.")
    else:
        if not historico:
            st.info("Nenhuma simulação salva. Faça sua primeira simulação acima.")
        else:
            linhas = [
                {
                    "Valor solicitado": formatar_reais(registro["valor_solicitado"]),
                    "Parcelas": registro["parcelas"],
                    "Taxa mensal": f'{formatar_numero_br(registro["taxa_juros_mensal"])}% ao mês',
                    "Valor da parcela": formatar_reais(registro["valor_parcela"]),
                    "Valor total": formatar_reais(registro["valor_total"]),
                    "Juros": formatar_reais(registro["total_juros"]),
                    "Data/hora": datetime.fromisoformat(registro["criado_em"]).strftime(
                        "%d/%m/%Y %H:%M:%S"
                    ),
                }
                for registro in historico
            ]
            st.dataframe(linhas, hide_index=True, width="stretch")

with st.expander("Automações recentes"):
    if banco_disponivel:
        try:
            execucoes = listar_execucoes_automacao()
            if execucoes:
                st.dataframe([{"Tipo": e["tipo"], "Simulação": e["simulacao_id"],
                               "Status": e["status"], "Data": datetime.fromisoformat(e["criado_em"]).strftime("%d/%m/%Y %H:%M:%S")}
                              for e in execucoes], hide_index=True, width="stretch")
            else:
                st.caption("Nenhuma automação executada ainda.")
        except ErroBanco:
            st.warning("Não foi possível consultar as automações recentes.")

with st.expander("Monitoramento técnico"):
    st.caption("Métricas locais acumuladas. Sem conteúdo das conversas ou custos por chamada. Latências em milissegundos.")
    if banco_disponivel:
        try:
            resumo = obter_resumo_metricas()
            recentes = listar_metricas(limite=20)
            handoffs = obter_resumo_handoffs()
        except ErroBanco:
            st.warning("O monitoramento está indisponível no momento.")
        else:
            colunas = st.columns(3)
            colunas[0].metric("Operações registradas", resumo["total_operacoes"])
            colunas[1].metric("Sucessos", resumo["sucessos"])
            colunas[2].metric("Erros", resumo["erros"])
            colunas = st.columns(2)
            colunas[0].metric("Latência média (ms)", formatar_numero_br(resumo["latencia_media_ms"]))
            colunas[1].metric("Maior latência (ms)", formatar_numero_br(resumo["maior_latencia_ms"]))
            colunas = st.columns(2)
            colunas[0].metric("Chamadas ao modelo", resumo["chamadas_llm"])
            colunas[1].metric("Chamadas ao simulador", resumo["chamadas_simular_credito"])
            st.metric("Handoffs entre agentes", handoffs["quantidade_handoffs"])
            st.caption("Chamadas por agente: " + ", ".join(f"{nome}: {quantidade}" for nome, quantidade in handoffs["chamadas_por_agente"].items()))
            if recentes:
                st.dataframe([{
                    "Operação": item["operacao"], "Status": item["status"],
                    "Latência (ms)": item["latencia_ms"], "Modelo": item["modelo"],
                    "Ferramenta": item["ferramenta"], "Erro técnico": item["erro"],
                    "Agente origem": item.get("agente_origem"), "Agente destino": item.get("agente_destino"),
                    "Data/hora": datetime.fromisoformat(item["criado_em"]).strftime("%d/%m/%Y %H:%M:%S"),
                } for item in recentes], hide_index=True, width="stretch")
            else:
                st.info("Nenhuma métrica registrada ainda.")
    else:
        st.info("O monitoramento depende da disponibilidade do banco local.")

with st.expander("Avaliação do agente"):
    st.caption("Cenários isolados do histórico principal. Mock verifica a orquestração; real consulta o Ollama local e pode demorar alguns minutos.")
    mock, real = st.columns(2)
    modo_avaliacao = None
    if mock.button("Executar avaliação mock"):
        modo_avaliacao = "mock"
    if real.button("Executar avaliação local"):
        modo_avaliacao = "real"
    if modo_avaliacao:
        try:
            with st.spinner("Executando cenários em ambiente isolado..."):
                relatorio_avaliacao = executar_avaliacao(modo_avaliacao)
                salvar_relatorio(relatorio_avaliacao)
        except (RuntimeError, OSError, ValueError):
            st.warning("A avaliação não foi concluída. O relatório anterior foi preservado.")
    ultimo_relatorio = carregar_ultimo_relatorio()
    if ultimo_relatorio is None:
        st.info("Nenhuma avaliação anterior disponível.")
    else:
        st.caption(f'Modo: {ultimo_relatorio["modo"]} • Execução: {ultimo_relatorio["criado_em"]}')
        resumo_avaliacao = ultimo_relatorio["resumo"]
        colunas = st.columns(4)
        for coluna, campo, rotulo in zip(colunas,
                ("total", "aprovados", "reprovados", "taxa_sucesso"),
                ("Cenários", "Aprovados", "Reprovados", "Sucesso (%)")):
            coluna.metric(rotulo, resumo_avaliacao[campo])
        st.dataframe([{"Categoria": categoria, **resumo}
                      for categoria, resumo in ultimo_relatorio["categorias"].items()],
                     hide_index=True, width="stretch")
        for resultado_avaliacao in ultimo_relatorio["resultados"]:
            if resultado_avaliacao["status"] == "reprovado":
                st.warning(resultado_avaliacao["cenario"] + ": " + ", ".join(resultado_avaliacao["falhas"]))
        st.caption(ultimo_relatorio["limites"])
