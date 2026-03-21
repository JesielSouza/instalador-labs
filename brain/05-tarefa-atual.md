# Tarefa Atual: Bootstrap de Ambiente Priorizando WinGet

**Status:** Ensaio real validado e bootstrap reorganizado para ambiente hostil
**Objetivo:** Garantir que a automacao consiga preparar WinGet, Python e a `.venv` mesmo em maquinas que nao chegam prontas.

## Checklist de Execucao
- [x] **Task 4.1**: Popular `packages/ads_lab.json` com os softwares da base institucional que ja possuem dados suficientes para o schema atual.
- [x] **Task 4.2**: Registrar itens da base institucional ainda bloqueados por ausencia de `winget_id` validado.
- [x] **Task 4.3**: Preparar um ensaio controlado do fluxo completo com o catalogo preenchido em ambiente que exponha o WinGet.
- [x] **Task 4.4**: Padronizar a execucao com `.venv` local, `bootstrap.ps1`, `run.ps1`, `run.bat` e `bootstrap.bat`.
- [x] **Task 4.5**: Implementar modo degradado para Windows sem WinGet acessivel.
- [x] **Task 4.6**: Implementar fallback por instalador direto oficial para `Visual Studio Code` e `Python 3.12`.
- [x] **Task 4.7**: Validar em maquina real o fallback direto do nucleo seguro.
- [x] **Task 4.8**: Ajustar o bootstrap para tentar restaurar WinGet antes de depender de Python.

## Resultado da Validacao
- `bootstrap.bat` e `run.bat` funcionaram em maquina real com elevacao administrativa.
- Em Windows 10 Enterprise LTSC 2019 versao 1809 build 17763 sem WinGet acessivel, `Visual Studio Code` e `Python 3.12` foram baixados e instalados com sucesso via fallback direto oficial.
- O resultado real da execucao foi: `2 installed`, `0 already_installed`, `3 pending`, `1 manual`, `0 failed`, `0 blocked`.
- O relatorio correspondente foi gerado em `reports/execution_report_20260321_141328.csv`.
- O bootstrap agora tenta recuperar o WinGet via `Microsoft.WinGet.Client` e `Repair-WinGetPackageManager -AllUsers` antes de depender de Python.
- Se o Python nao existir, o bootstrap tenta primeiro instalar `Python 3.12` via WinGet e, se necessario, cai para instalador direto oficial.

## Instrucoes para o Codex
> A proxima iteracao deve melhorar rastreabilidade do metodo de instalacao no relatorio e, depois disso, avaliar empacotamento em `.exe`.
