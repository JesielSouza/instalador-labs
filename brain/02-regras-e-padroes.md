# ⚖️ Regras e Padrões do Projeto

## 🛠️ Tecnologias Obrigatórias
* [cite_start]**Linguagem:** Python 3.10+[cite: 7].
* [cite_start]**Gerenciador de Pacotes:** WinGet (Windows Package Manager)[cite: 5, 7].
* [cite_start]**Formato de Configuração:** JSON para o catálogo de softwares[cite: 7, 30].
* [cite_start]**Documentação:** Obsidian como Single Source of Truth[cite: 22, 38].

## 🛡️ Segurança e Governança
* [cite_start]**Permissões:** O script deve validar se possui privilégios de Administrador antes de iniciar[cite: 46].
* [cite_start]**Idempotência:** O código deve ser capaz de rodar múltiplas vezes sem causar erros ou reinstalações desnecessárias[cite: 16, 17].
* [cite_start]**Validação:** Nenhum software deve ser automatizado sem antes passar pelo status `winget_pending` para teste manual[cite: 33, 48].

## 🚀 Fluxo de Trabalho e Deploy
* **Trabalho por Fases**: O projeto evolui por Tasks definidas em `05-tarefa-atual.md`.
* **Sincronização**: Ao finalizar uma Task com sucesso, o Codex DEVE realizar o `git commit` e `git push`.
* **Privacidade Absoluta**: É PROIBIDO subir a pasta `brain/` ou arquivos `.env`/`logs` para o GitHub. 
* **Higiene de Código**: Antes de cada push, validar a compilação e atualizar a memória no Obsidian.

## 📊 Observabilidade (Logs)
* [cite_start]**Localização:** Todos os logs devem ser salvos na pasta `/logs`[cite: 29].
* [cite_start]**Conteúdo:** Cada entrada de log deve conter: Timestamp, Nome da Máquina, Usuário e Status do Pacote[cite: 32, 37].
* [cite_start]**Persistência:** Erros críticos devem ser detalhados para facilitar o troubleshooting remoto[cite: 37, 45].