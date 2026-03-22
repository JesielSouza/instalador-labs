# Tarefa Atual: Bootstrap de Ambiente Priorizando WinGet

**Status:** Fluxo do `.exe` validado em campo com instalacao real, feedback visual ao operador consolidado e base do catalogo evoluindo para selecao de perfil e pacotes antes da execucao
**Objetivo:** Evoluir o instalador de um perfil fixo de laboratorio para uma ferramenta flexivel, com escolha de perfil e de pacotes, preservando a estabilidade operacional do `.exe` e o fluxo de QA do projeto.

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

## Resultado da Validacao
- `bootstrap.bat` e `run.bat` funcionaram em maquina real com elevacao administrativa.
- Em Windows 10 Enterprise LTSC 2019 versao 1809 build 17763 sem WinGet acessivel, `Visual Studio Code` e `Python 3.12` foram baixados e instalados com sucesso via fallback direto oficial.
- O resultado real da execucao foi: `2 installed`, `0 already_installed`, `3 pending`, `1 manual`, `0 failed`, `0 blocked`.
- O relatorio correspondente foi gerado em `reports/execution_report_20260321_141328.csv`.
- O bootstrap agora tenta recuperar o WinGet via `Microsoft.WinGet.Client` e `Repair-WinGetPackageManager -AllUsers` antes de depender de Python.
- Se o Python nao existir, o bootstrap tenta primeiro instalar `Python 3.12` via WinGet e, se necessario, cai para instalador direto oficial.
- O relatorio agora inclui uma secao por pacote com `status`, `install_method`, `install_type`, `winget_id` e `detail`.
- O resumo agregado foi preservado no topo do CSV para leitura rapida.
- O workflow `qa-review.yml` foi corrigido ate comentar com sucesso em PR real usando Gemini.
- O fluxo completo de governanca foi exercitado na pratica: branch dedicada, PR, comentario automatizado do Gemini e merge posterior.
- `build_exe.ps1` gerou `dist\InstaladorLabs\InstaladorLabs.exe` com sucesso, e o executavel abriu corretamente ate o bloqueio esperado por falta de privilegio administrativo.

## Validacao Mais Recente
- O InstaladorLabs.exe reconstruido executou com sucesso em maquina real e exibiu feedback visual ao operador ao final da execucao.
- O fluxo passou a mostrar um resumo com totais e caminho do relatorio, evitando a percepcao de encerramento silencioso.
- Em maquina ja preparada por testes anteriores, o resultado observado foi `0 installed`, `5 already_installed`, `0 pending`, `1 manual`, `0 failed`, `0 blocked`.
- O relatorio correspondente foi gerado em `dist\\InstaladorLabs\\reports\\execution_report_20260322_113118.csv`.
- Logs, relatorios e downloads do executavel agora devem permanecer ao lado do `.exe`, enquanto o catalogo continua vindo do bundle empacotado.

## Iteracao em Andamento
- O carregador de catalogo agora deve evoluir para listar perfis disponiveis e permitir filtragem explicita dos pacotes selecionados pelo operador.
- A interface do `.exe` agora deve consolidar a escolha de perfil, pacotes e operacao (`instalar`, `atualizar`, `desinstalar`) antes de avancar para automacoes fora do WinGet.
- Itens fora do WinGet devem evoluir para downloads oficiais catalogados, nao para busca aberta e generica na web; quando o fornecedor descontinuar o produto, o catalogo deve apontar para a referencia oficial e manter o fluxo manual.

## Instrucoes para o Codex
> A proxima iteracao deve priorizar polish de operador e estabilidade de distribuicao, sem perder o foco em uso real controlado e sem abrir PRs desnecessarias.

- A memoria versionada em `brain/` deve acompanhar cada iteracao relevante do produto.
- Consolidar mudancas relacionadas na `trabalho/codex` antes de abrir nova PR, para economizar cota do Gemini.
- Melhorias de UX do `.exe` com cara de instalador tradicional devem ser estudadas, mas nao sao prioridade acima da estabilidade operacional imediata.



