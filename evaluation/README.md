# Avaliação comportamental do CreditAI

Execute na raiz do projeto, no PowerShell:

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluator --modo mock
.\.venv\Scripts\python.exe -m evaluation.evaluator --modo real
```

O modo mock usa interpretações fixas e a orquestração, busca e simulador reais.
Ele verifica controles e contratos, não a capacidade linguística do modelo.
O modo real consulta somente o Ollama local já configurado; não baixa modelos.
Uma execução real pode demorar vários minutos e deve ser iniciada explicitamente.

Cada execução acontece em processo separado, com um SQLite temporário por cenário.
O registro de ferramentas não é alterado. Tentativas de decisão humana são
observadas, bloqueadas e contadas como reprovação. Nenhum dado da aplicação é usado
como cenário. As solicitações pendentes da avaliação são apenas fixtures temporárias.

O relatório fica em `evaluation/results/ultimo.json`, ignorado pelo Git.
Contém IDs dos cenários, critérios, falhas e totais; não armazena respostas completas.
A persistência deste relatório é em JSON, separada do SQLite da aplicação.
O comando retorna código 1 se houver cenários reprovados; examine `falhas` no relatório.
O Streamlit mostra o último resultado e só executa avaliações após clique nos botões.

Para RAG, são verificadas busca, existência e origem das fontes, origem dos trechos,
números e sobreposição de vocabulário (mínimo de 65%). São heurísticas conservadoras:
podem reprovar paráfrases válidas e não detectam toda contradição semântica.
Uma pontuação de 100% nesses cenários não significa segurança ou exatidão universal.
