# CreditAI

CreditAI é um projeto educacional de portfólio com assistente de crédito em Python, Streamlit e modelo local llama3.2:3b via Ollama.

O objetivo é aprender com uma arquitetura simples e organizada, adicionando funcionalidades em pequenas etapas.

## Etapa atual

O projeto possui simulador pela Tabela Price, chat, SQLite, histórico, base educativa local, monitoramento, aprovação humana demonstrativa, avaliações e geração local de relatórios Markdown. Não há contratação real de crédito nem movimentação financeira.

O processamento do modelo ocorre localmente, sem APIs pagas, OpenAI API ou LangChain. A consulta opcional à Selic usa a API pública externa do Banco Central do Brasil e requer internet.

## Tecnologias

- **Python:** linguagem principal.
- **Streamlit:** interface do assistente.
- **SQLite:** armazenamento local, usando o módulo `sqlite3` do Python.
- **JSON:** formato para dados, usando o módulo `json` do Python.
- **pytest:** testes automatizados independentes da internet e do Ollama real.
- **Ollama:** interpretação local com llama3.2:3b.
- **urllib:** cliente HTTP da biblioteca padrão para Ollama e BCB, em módulos separados.

SQLite e JSON fazem parte da biblioteca padrão do Python e não precisam ser instalados pelo pip.

## Estrutura

```text
credit-ai/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── agent/                  # Orquestração e cliente Ollama
├── integrations/           # Cliente da API pública do BCB
├── actions/                # Aprovação humana demonstrativa
├── automations/            # Relatórios locais
├── knowledge/              # Busca lexical nos documentos
├── monitoring/             # Métricas técnicas
├── evaluation/             # Cenários e avaliador isolado
├── reports/                # Relatórios gerados (ignorados pelo Git)
├── tools/
│   ├── __init__.py
│   └── credit_simulator.py
├── database/
│   ├── __init__.py
│   └── database.py
├── tests/
│   ├── __init__.py
│   └── test_credit_simulator.py
└── documents/
    └── .gitkeep
```

| Arquivo ou pasta | Finalidade |
| --- | --- |
| `app.py` | Interface Streamlit, chat e painéis. |
| `requirements.txt` | Dependências externas: Streamlit, pytest, SDK MCP, faster-whisper e pyttsx3. |
| `README.md` | Apresentação do projeto e instruções de instalação. |
| `.gitignore` | Impede que caches, ambientes virtuais, segredos e bancos locais sejam versionados. |
| `tools/__init__.py` | Identifica a pasta de ferramentas como um pacote Python. |
| `tools/credit_simulator.py` | Cálculo de parcelas fixas pela Tabela Price. |
| `database/__init__.py` | Identifica a pasta de banco de dados como um pacote Python. |
| `database/database.py` | Persistência em SQLite. |
| `tests/__init__.py` | Identifica a pasta de testes como um pacote Python. |
| `tests/test_credit_simulator.py` | Testes do simulador; os demais módulos também possuem testes. |
| `documents/` | Base de conhecimento demonstrativa e educativa em Markdown. |
| `documents/.gitkeep` | Mantém a pasta de documentos no Git enquanto estiver vazia. |

## Instalação no Windows (PowerShell)

Com o Python instalado, abra um terminal na pasta `credit-ai` e execute:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Esses comandos criam um ambiente virtual e instalam as dependências nele, sem precisar ativá-lo. A instalação requer acesso à internet para baixar os pacotes; não requer serviços pagos.

Com o Ollama e o modelo llama3.2:3b já disponíveis, abra a aplicação:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m evaluation.evaluator --modo mock
```

## Indicador público do Banco Central

O cliente `integrations/bcb_client.py` consulta a série SGS **1178 — Taxa de juros - Selic anualizada base 252**, publicada em **percentual ao ano**. Veja a [descrição oficial do BCB](https://dadosabertos.bcb.gov.br/dataset/1178-taxa-de-juros---selic-anualizada-base-252).

Endpoint fixo: `https://api.bcb.gov.br/dados/serie/bcdata.sgs.1178/dados`, com `formato=json` e filtros de data para os últimos 30 dias. O cliente valida HTTP, JSON, datas e valores, selecionando a data mais recente, independentemente da ordem da resposta.

No chat, pergunte **“Qual é a Selic?”** ou **“Consulte a taxa Selic mais recente.”** O valor e a data vêm da API, nunca de uma taxa fixada no código ou inventada pelo modelo. Valores fictícios aparecem somente nos testes e nas avaliações mock.

**Essa série é apenas um indicador econômico de referência. Não é automaticamente uma taxa de empréstimo, uma oferta ao cliente ou uma recomendação financeira.** Não existe conversão automática de taxa anual para taxa mensal de crédito. O simulador continua usando a taxa explicitamente informada pelo usuário. Para **“Simule 5000 usando a Selic”**, o sistema pede uma taxa mensal explícita sem executar a simulação.

O cache é em memória, por até uma hora, invalidado também na mudança de dia. O retorno identifica `origem: api` ou `origem: cache`. Não há fallback para dados expirados ou inventados. Em caso de indisponibilidade ou resposta inválida, o chat informa a falha sem traceback e sem alterar simulações.

O usuário e o modelo não podem fornecer URLs. O cliente valida HTTPS, host e caminho fixos, desativa proxies e recusa redirecionamentos. A lista `APIS_PERMITIDAS` contém somente `bcb_selic`. Não são enviados ao BCB mensagens, dados pessoais, dados das simulações ou parâmetros do modelo.

As chamadas de rede registram métricas `external_api` / `bcb_selic`, sem o corpo da resposta; acertos de cache não contam como nova chamada externa. Os testes e o modo mock das avaliações usam transporte falso, sem internet. O modo real consulta o Ollama e o BCB nos cenários normais; os cenários de falha da API continuam controlados por fakes para serem reproduzíveis.

## Servidor local CreditAI MCP

O servidor usa o [SDK oficial MCP para Python](https://github.com/modelcontextprotocol/python-sdk), versão `mcp==2.2.0`, e transporte **stdio**. É um adaptador das funções existentes, sem LLM próprio. A interface Streamlit continua independente.

Na pasta do projeto, pelo PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m mcp_server.server
```

O servidor aguarda mensagens do protocolo MCP pela entrada padrão; não abre página web nem aceita conversa em texto livre. Um cliente MCP compatível deve iniciar esse mesmo comando na pasta do projeto. Encerre uma execução manual com Ctrl+C. Nenhuma porta HTTP é publicada.

As únicas ferramentas disponíveis são:

| Ferramenta | Argumentos JSON | Retorno estruturado |
| --- | --- | --- |
| `simular_credito` | `{"valor":5000,"parcelas":12,"taxa_juros_mensal":2}` | Dicionário do simulador original. |
| `consultar_selic` | `{}` | Indicador anual, data, fonte e observação educativa; consulta exclusivamente o cliente BCB existente. |
| `buscar_conhecimento` | `{"pergunta":"Como funciona a Tabela Price?"}` | `{"trechos":[{"arquivo":"...","trecho":"...","score":5}]}` com somente resultados reais; lista vazia quando nada é encontrado. |

O cliente usa `tools/list` para descobrir os esquemas e `tools/call` para enviar nome e argumentos. Resultados ficam em `structuredContent` e também em JSON no conteúdo textual. Erros retornam `isError: true`, com mensagem controlada, sem traceback. Valor e parcelas devem ser positivos, parcelas inteiras, taxa não negativa. A pergunta deve conter texto e ter até 4.000 caracteres. Argumentos adicionais são rejeitados.

### Teste local sem cliente externo

```powershell
.\.venv\Scripts\python.exe -m mcp_server.smoke_test
```

Esse comando utiliza o cliente do SDK em memória, negocia o protocolo, lista ferramentas e chama a simulação. Usa um banco temporário para métricas, removido ao terminar, sem gravar no banco da aplicação. Não acessa Ollama nem BCB. A chamada com 5000, 12 e 2 retorna:

```json
{
  "valor_solicitado": 5000.0,
  "parcelas": 12,
  "taxa_juros_mensal": 2.0,
  "valor_parcela": 472.8,
  "valor_total": 5673.58,
  "total_juros": 673.58
}
```

### Arquitetura e limites

```text
Cliente MCP → stdio → mcp_server/server.py → registro explícito
  simular_credito     → tools/credit_simulator.py
  consultar_selic     → integrations/bcb_client.py → endpoint fixo BCB
  buscar_conhecimento → knowledge/knowledge_base.py → documents/
                      → monitoring/metrics.py → SQLite local
```

`MCP_TOOLS_PERMITIDAS` contém somente os três nomes; o despacho usa um mapa fixo de funções, sem resolução dinâmica por nome, eval ou execução de comandos. Aprovação e cancelamento de propostas não estão registrados. O fluxo de aprovação humana permanece na interface existente. URLs, diretórios e caminhos de saída não são parâmetros aceitos. A busca retorna documentos educativos, não políticas de uma instituição financeira.

Cada tentativa despachada registra `mcp_tool_call`, ferramenta, status, latência e data/hora. Nomes desconhecidos são registrados como `nao_permitida`; argumentos, perguntas e mensagens de exceções não entram nas métricas. As camadas reutilizadas também podem registrar suas próprias métricas. A simulação MCP calcula o resultado sem acrescentá-lo automaticamente ao histórico de simulações.

Stdio restringe o transporte ao processo cliente local, mas não é um sandbox de sistema operacional nem adiciona autenticação. Execute com um cliente local confiável e proteja o acesso à conta e aos arquivos. A consulta Selic pode acessar a internet pelo endpoint público já configurado; não exige API paga. Não há conversão automática de Selic anual em taxa mensal. Falhas da API retornam erro e as demais ferramentas continuam disponíveis.

### Verificações

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m evaluation.evaluator --modo mock
```

Na etapa de MCP: **267 testes** e **40 cenários mock**, incluindo dez cenários MCP. Pytest usa o protocolo em memória, sem iniciar clientes externos. As avaliações verificam chamadas válidas, whitelist, aprovação bloqueada, shell bloqueado, URL arbitrária, argumentos inválidos, falha do BCB e continuidade das ferramentas. O modo mock não consulta serviços externos.


## Fluxo com especialistas

`agent.credit_agent.processar_mensagem()` continua sendo a entrada pública do chat.
No modo LLM, encaminha para `agents.orchestrator.OrchestratorAgent`. O mesmo Ollama
local `llama3.2:3b` interpreta intenção, argumentos e lista de especialistas. Não há
modelo novo, dependência adicional ou serviço pago nesta etapa.

| Agente | Responsabilidade | Capacidade disponível |
| --- | --- | --- |
| `OrchestratorAgent` | Validar o plano, encaminhar tarefas e consolidar resultados | Registro fixo de três especialistas; automação de relatório existente |
| `SimulationAgent` | Validar os dados interpretados, pedir os faltantes e simular | `simular_credito` |
| `KnowledgeAgent` | Recuperar evidências e produzir explicação com fontes pelo Ollama | `buscar_conhecimento` |
| `MarketDataAgent` | Consultar o indicador anual e apresentar fonte/data | `consultar_selic` pelo cliente BCB fixo |

Os especialistas são componentes Python com capacidades limitadas. Não é feita uma
chamada adicional ao LLM só para dar personalidade a cada agente: o orquestrador
interpreta a linguagem e o especialista de conhecimento utiliza o mesmo modelo para
redigir a resposta baseada nos documentos. Cálculos continuam na ferramenta original.

Exemplos no chat:

- `Simule 5000 em 12 parcelas a 2%` → SimulationAgent.
- `Como funciona a Tabela Price?` → KnowledgeAgent.
- `Qual é a Selic?` → MarketDataAgent.
- `O que é Tabela Price e quanto fica 5000 em 12x a 2%?` → KnowledgeAgent → SimulationAgent.
- `Qual é a Selic e o que são juros?` → MarketDataAgent → KnowledgeAgent.

O chat mostra discretamente o fluxo. Em uma resposta composta, as mensagens são
reunidas em Python e os valores, fontes e trechos permanecem os retornados pelos
especialistas. A simulação é salva uma única vez no envio; reexibir a conversa não
executa novamente ferramentas. Se um especialista falhar, sua parte informa a falha
e os demais continuam. O plano não é refeito automaticamente.

### Limites e estado

`AGENTES_PERMITIDOS` contém apenas `simulation`, `knowledge` e `market_data`.
O limite é `MAX_HANDOFFS = 3` por mensagem, sem agentes repetidos. Planos acima do
limite, nomes desconhecidos e campos não previstos são rejeitados antes de executar
qualquer especialista. Não existe descoberta dinâmica de classes, código gerado ou
encaminhamento recursivo entre especialistas.

Cada especialista recebe somente sua função permitida e os dados da tarefa. Não
recebe o registro dos outros, histórico completo ou prompts do orquestrador.
`EstadoCompartilhado` limita os dados internos ao ID da última simulação e argumentos
numéricos validados. A conversa permanece no `session_state` e só o orquestrador usa
seus campos de papel/texto para interpretar continuações. SQLite preserva os dados já
persistidos. Isso é separação de capacidades no código, não um sandbox para plugins
Python não confiáveis; não se carregam plugins ou agentes enviados pelo modelo.

Nenhum especialista ou orquestrador aprova ou cancela propostas. A intenção de
prosseguir apenas devolve uma solicitação de revisão à interface; a aprovação humana
continua nos botões existentes. Relatórios continuam passando por
`AUTOMACOES_PERMITIDAS`, sem criar um agente extra. O MCP mantém somente suas três
ferramentas anteriores e não expõe agentes ou aprovação.

### Monitoramento e testes

Cada handoff registra `operacao=agent_handoff`, `agente_origem`, `agente_destino`,
status, latência e data/hora. Não registra a pergunta, argumentos ou prompts internos.
A migração SQLite adiciona duas colunas opcionais sem remover registros anteriores.
O painel técnico mostra o total de handoffs e chamadas por especialista; o resumo
complementar é obtido por `obter_resumo_handoffs()`.

A suíte usa modelos falsos e bancos temporários. A avaliação inclui doze cenários
multiagente controlados, inclusive no modo de avaliação local, para reproduzir ataques,
falhas e limites. Esses cenários validam a execução e o isolamento; não medem a precisão
do roteamento do modelo real. Os demais cenários mantêm seu modo mock/real anterior.

Para abrir e testar manualmente, na pasta do projeto:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Com o Ollama já iniciado, envie os exemplos acima e confira o fluxo, os resultados e
as fontes no chat. Abra **Monitoramento técnico** para ver os handoffs. Complete uma
simulação em várias mensagens para testar a memória e peça um relatório para verificar
a automação existente. Execute a suíte e atualize a avaliação com:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m evaluation.evaluator --modo mock
```

Verificação da etapa multiagente: **297 testes aprovados** (267 anteriores e 30 novos),
**52 cenários mock aprovados** (40 anteriores e 12 novos). O Streamlit respondeu
`200 ok` na verificação local. Um pedido composto também foi executado com o Ollama
real, em banco temporário: parcela de R$ 472,80, total de R$ 5.673,58 e juros de
R$ 673,58, com fontes `faq_credito.md` e `glossario_credito.md`. A ordem dos especialistas
pode variar conforme o plano validado do modelo; os resultados são independentes.


## Conversa por voz local

A entrada de voz usa `st.audio_input` (verificado com Streamlit 1.64.0). O chat por
texto permanece disponível. A voz é uma camada de entrada e apresentação: não cria
outro caminho de execução nem dá autoridade adicional aos agentes.

```text
Gravador no navegador → voice/session.py → speech_to_text.py (Whisper local)
  → mesmo processar_mensagem() → OrchestratorAgent → especialistas existentes
  → resposta textual obrigatória → text_to_speech.py opcional → player no navegador
```

### Dependências e modelo

Dependências diretas adicionadas: `faster-whisper==1.2.1` e `pyttsx3==2.99`.
O [faster-whisper](https://github.com/SYSTRAN/faster-whisper) executa os pesos Whisper
localmente; não usa a API da OpenAI. A implementação usa **base multilíngue**, idioma
preferencial `pt`, CPU, quatro threads e precisão `int8`. Um vocabulário fixo com
nomes como CreditAI, Tabela Price e Selic orienta o reconhecimento, sem fornecer
valores ou inventar transcrições. Os arquivos baixados de
`Systran/faster-whisper-base` ocupam aproximadamente **148 MB** (cerca de 141 MiB),
fora as bibliotecas e o ambiente virtual. Ficam em `voice/models/faster-whisper-base/`,
ignorado pelo Git. Não é o modelo `base.en`, exclusivo de inglês.

O [pyttsx3](https://github.com/nateshmbhat/pyttsx3) usa **SAPI5 do Windows** e uma voz
portuguesa offline já instalada. Não baixa uma voz e não toca som no computador do
servidor: gera um WAV para o player do navegador. Sem voz portuguesa instalada ou
quando há falha de síntese, a interface mantém a resposta escrita e mostra um aviso.

Não é necessária GPU. Há consumo de CPU e memória além do Ollama; reserve alguns GB
de RAM livres para os dois modelos e bibliotecas. O consumo e a latência dependem
do hardware e da duração do áudio; não há garantia de tempo real. O modelo STT é
carregado sob demanda e reutilizado no processo. A execução de voz é serializada
para evitar múltiplos carregamentos/sínteses simultâneos.

### Preparação e execução (PowerShell)

Na pasta do projeto:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m voice.speech_to_text --preparar
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address=127.0.0.1
```

O download inicial dos pesos é público, gratuito e precisa de internet. Ele já foi
feito neste ambiente. A preparação é separada da transcrição: o chat carrega somente
arquivos locais (`local_files_only=True`) e não baixa modelos automaticamente.
Após a preparação, STT e TTS funcionam sem internet. O Ollama também permanece local;
a consulta opcional à Selic continua exigindo acesso ao BCB, como antes.

### Como usar

1. Com o Ollama iniciado, abra o endereço local exibido pelo Streamlit.
2. Em **Assistente de crédito**, use **Ou fale com o CreditAI** e autorize o microfone
   no navegador. O navegador precisa de localhost ou contexto HTTPS para gravação.
3. Fale por até **60 segundos**, pare a gravação e aguarde a transcrição local.
4. A transcrição aparece antes da resposta e fica identificada no histórico da sessão.
5. Para receber também áudio, marque **Habilitar resposta falada (local)** antes de
   enviar a próxima mensagem. Use o player para ouvi-la; não há reprodução automática.

Exemplo: **“Explique Tabela Price e simule cinco mil reais em doze parcelas a dois por cento.”**
O texto transcrito entra no orquestrador e pode utilizar KnowledgeAgent e SimulationAgent.
Números e palavras podem ser reconhecidos incorretamente; confira a transcrição e use
uma nova mensagem de texto ou gravação para corrigir. Ruído, sotaques e microfones
ruins afetam a qualidade. A gravação é consumida uma vez por envio; reruns não repetem
simulações. Para tentar de novo após falha, faça uma nova gravação. Se texto e gravação
chegarem juntos, o texto tem prioridade e a gravação concorrente é descartada.

### Limites, privacidade e confirmação humana

Somente o widget de gravação fornece áudio à interface. Não existe campo para URL,
caminho de arquivo ou upload genérico. Além do MIME, o conteúdo WAV é validado como
PCM de 16 bits, um ou dois canais, 8 a 48 kHz, até 60 segundos e **10 MB**. Arquivos
vazios, truncados, excessivos e formatos não suportados são recusados antes do modelo.
O gravador é configurado para 16 kHz. Silêncio sem fala reconhecida produz aviso.

O áudio de entrada vai para um arquivo de nome fixo dentro de uma pasta temporária
aleatória. Essa pasta é removida ao terminar, inclusive em caso de exceção. O TTS
segue o mesmo padrão: lê o WAV gerado para memória e remove o temporário. Não há
arquivos de áudio permanentes no projeto. O widget e o player mantêm dados em memória
da sessão do Streamlit; o texto transcrito integra a conversa da sessão como qualquer
mensagem digitada. As simulações continuam persistidas no SQLite.

Quando executado em localhost, o processamento de voz ocorre neste computador.
Não são enviados áudio ou transcrições para APIs externas de STT/TTS. A síntese recebe
somente a resposta final visível e os valores finais da simulação, sem prompts ou
histórico privado; texto não é interpretado como comandos ou marcação de voz.
Respostas faladas são limitadas a 4.000 caracteres e a WAVs de até 30 MB.

As métricas `speech_to_text` e `text_to_speech` registram status, latência, modelo e
horário, sem áudio, transcrição ou texto sintetizado. Aparecem no monitoramento técnico
existente. **“Eu confirmo, aprove agora” falado não equivale ao clique de confirmação.**
Aprovação e cancelamento continuam exclusivamente nos botões confiáveis. Transcrições
são entradas não confiáveis, submetidas às mesmas validações, listas de ferramentas e
limites de agentes do chat por texto.

### Testes de voz

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m evaluation.evaluator --modo mock
```

Os testes não usam microfone, voz do Windows ou modelo STT real: geram WAVs sintéticos
e usam fakes dos mecanismos de voz. A avaliação adiciona dez cenários controlados,
mesmo no modo local, para testar simulação, conhecimento, Selic, pedido composto,
dados incompletos, aprovação bloqueada, prompt injection, comando proibido, falha de
STT e continuidade do texto. Esses cenários avaliam integração, não precisão acústica.
Também foi verificada a síntese/transcrição real local de uma frase sintética:
**“Simule 5.000 reais em 12 parcelas a 2%.”** O microfone físico depende do teste manual.

Verificação final de voz: **329 testes aprovados** (297 anteriores e 32 novos).
Avaliação final: **62 cenários mock aprovados**, incluindo os dez cenários de voz;
relatório atualizado em `evaluation/results/ultimo.json` (ignorado pelo Git).
O Streamlit iniciou e respondeu `200 ok`. STT e TTS reais foram verificados com fala
sintética, inclusive síntese em thread. Um fluxo real com Ollama encaminhou a fala
para os especialistas e calculou parcela de R$ 472,80, total de R$ 5.673,58 e juros
de R$ 673,58. O vocabulário fixo melhorou o reconhecimento de “Tabela Price”, mas
não elimina erros de transcrição; confira sempre o texto reconhecido.
