# Regras e Padroes do Projeto

## Tecnologias Obrigatorias
* **Linguagem:** Python 3.10+.
* **Gerenciador de Pacotes:** WinGet (Windows Package Manager).
* **Formato de Configuracao:** JSON para o catalogo de softwares.
* **Documentacao:** Obsidian `brain/` como memoria operacional versionada no repositorio.

## Seguranca e Governanca
* **Permissoes:** O script deve validar privilegios de Administrador antes de iniciar.
* **Idempotencia:** O codigo deve poder rodar varias vezes sem reinstalacoes desnecessarias.
* **Validacao:** Nenhum software deve sair de `winget_pending` para automacao sem validacao manual previa.
* **Privacidade:** Logs, relatorios locais, artefatos temporarios e segredos nao devem ser enviados ao GitHub. A pasta `brain/` passa a ser versionada como memoria oficial do projeto.

## Fluxo de Trabalho e Deploy
* **Trabalho por Fases:** O projeto evolui por Tasks definidas em `brain/05-tarefa-atual.md`.
* **Branches Obrigatorias:** Todo desenvolvimento acontece em branch dedicada; nunca commitar diretamente na `main`.
* **PR por Entrega:** Cada feature ou correcao deve gerar um Pull Request individual.
* **QA Automatizado:** Ao abrir ou atualizar um PR, o workflow `qa-review.yml` deve disparar automaticamente para analise do Gemini sobre o diff.
* **Leitura Obrigatoria do QA:** O Codex deve ler o comentario do Gemini antes de qualquer decisao tecnica, resposta no PR ou merge.
* **Merge Condicional:** O Codex pode fazer merge automatico apenas quando o Gemini classificar o PR como aprovado e sem erros criticos.
* **Bloqueios de Merge:** O Codex deve bloquear o merge e notificar o humano se o Gemini identificar erro de logica, ausencia de tratamento de erro, risco de falha em producao ou comportamento indefinido em cenarios de excecao.
* **Integracao na Main:** Ao finalizar uma Task com sucesso, o fluxo correto e commitar na branch, publicar a branch, abrir PR e integrar na `main` somente apos o QA.
* **Higiene de Codigo:** Antes de cada push, validar o comportamento da mudanca e atualizar a memoria versionada em `brain/`.

## Observabilidade
* **Localizacao:** Logs devem ser salvos em `logs/` e relatorios em `reports/`.
* **Conteudo:** Cada entrada de log deve conter timestamp, maquina, usuario, status e pacote.
* **Persistencia:** Erros criticos devem ser detalhados para facilitar troubleshooting remoto.
