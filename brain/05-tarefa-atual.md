# Tarefa Atual: Preparacao e Validacao da Release v0.2.0

**Status:** Release v0.2.0 publicada em 2026-03-25 com overhaul significativo de arquitetura, interface e robustez. O brain/ foi sincronizado com o estado real do repo em 2026-03-27. A release v0.2.0 contem: menu interativo do .exe, validacao de pre-requisitos, deteccao de ja instalados, bypass de WinGet quebrado no Win11, deteccao de proxy, retry SSL em downloads, log confiavel de versoes, e extensao massiva da suite de testes.

**Objetivo:** Validar a v0.2.0 em campo real, atualizar o backlog com itens ainda pendentes, e planejar a proxima iteracao.

## Checklist de Execucao
- [x] **Task 4.1**: Popular `packages/ads_lab.json` com os softwares da base institucional que ja possuem dados suficientes para o schema atual.
- [x] **Task 4.2**: Registrar itens da base institucional ainda bloqueados por ausencia de `winget_id` validado.
- [x] **Task 4.3**: Preparar um ensaio controlado do fluxo completo com o catalogo preenchido em ambiente que exponha o WinGet.
- [x] **Task 4.4**: Padronizar a execucao com `.venv` local, `bootstrap.ps1`, `run.ps1`, `run.bat` e `bootstrap.bat`.
- [x] **Task 4.5**: Implementar modo degradado para Windows sem WinGet acessivel.
- [x] **Task 4.6**: Implementar fallback por instalador direto oficial para `Visual Studio Code` e `Python 3.12`.
- [x] **Task 4.7**: Validar em maquina real o fallback direto do nucleo seguro.
- [x] **Task 4.8**: Ajustar o bootstrap para tentar restaurar WinGet antes de depender de Python.
- [x] **Task 4.9**: Melhorar rastreabilidade do metodo de instalacao no relatorio CSV.
- [x] **Task 4.10**: Endurecer e corrigir o workflow `qa-review.yml` ate permitir comentario real do Gemini em PR.
- [x] **Task 4.11**: Validar o empacotamento atual em `.exe` com smoke test local do artefato gerado.
- [x] **Task 4.12**: Validar em PR real o fluxo branch -> PR -> comentario do Gemini -> merge.
- [x] **Task 4.13**: Implementar menu interativo do .exe com escolha de operacao, perfil e pacotes.
- [x] **Task 4.14**: Implementar deteccao de proxy antes de instalacoes via WinGet.
- [x] **Task 4.15**: Implementar bypass automatico do WinGet quebrado no Win11.
- [x] **Task 4.16**: Implementar retry de downloads via PowerShell em erros SSL/TLS.
- [x] **Task 4.17**: Implementar validacao de pre-requisitos por perfil.
- [x] **Task 4.18**: Implementar deteccao de pacotes ja instalados antes de tentar instalar.
- [x] **Task 4.19**: Registrar versoes confiaveis do Windows e WinGet em log.
- [x] **Task 4.20**: Publicar release v0.2.0 com workflow automatizado.

## Resultado da Validacao de Campo
- A execucao real da v0.2.0 em Windows 10 Enterprise LTSC 2019 build 17763 sem WinGet funcionou corretamente.
- O resultado real observado: `3 installed`, `2 already_installed`, `0 pending`, `1 manual`, `0 failed`, `0 blocked` (Sessao 41, 2026-03-23).
- O fluxo confirmou sucesso para `Visual Studio Code`, `Python 3.12`, `Figma`, `MySQL Workbench` e `XAMPP`, mantendo `Astah Community` como item manual.
- A release `v0.2.0` foi publicada em 2026-03-25 como `InstaladorLabs-v0.2.0-win64.zip` na aba Releases do GitHub.

## Iteracao em Andamento
- Validacao da v0.2.0 em VMs ou maquinas mais limpas para confirmar o fluxo completo.
- Avaliacao de novos perfis de catalogo alem do `ads_lab`.
- Estudo de interface grafica (GUI) como alternativa ao menu interativo do console.
- Suporte a desatualizacao de pacotes ja instalados (verificar se ha update disponivel).

## Instrucoes para o Codex
> A proxima iteracao deve focar em validacao de campo da v0.2.0 e refinamentos de UX, sem abrir PRs desnecessarias.

- A memoria versionada em `brain/` deve acompanhar cada iteracao relevante do produto.
- Consolidar mudancas relacionadas antes de abrir nova PR, para economizar cota do Gemini.
- Melhorias de UX do `.exe` com cara de instalador tradicional devem ser estudadas, mas nao sao prioridade acima da estabilidade operacional imediata.
- Abrir PR apenas quando o bloco de mudancas estiver maduro e validado localmente.
