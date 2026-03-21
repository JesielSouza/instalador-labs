# Planejamento de Fases

## FASE 1: Estabilizacao do Ambiente
- [x] Task 1.1: Criar `.gitignore` robusto para proteger o "Cerebro" e logs.
- [x] Task 1.2: Inicializar repositorio Git local e conectar ao GitHub.
- [x] Task 1.3: Normalizar o acesso ao Python 3.14 e WinGet no `config.py`.

## FASE 2: Motor de Ingestao
- [x] Task 2.1: Implementar `utils/package_loader.py` para ler o `ads_lab.json`.
- [x] Task 2.2: Criar validacao de esquema JSON para evitar erros de digitacao nos IDs.

## FASE 3: Execucao e Relatorios
- [x] Task 3.1: Implementar loop de instalacao no `main.py`.
- [x] Task 3.2: Gerar relatorio final em CSV na pasta `reports/`.

## FASE 4: Curadoria do Catalogo e Runtime
- [x] Task 4.1: Popular `packages/ads_lab.json` com os itens da base institucional que ja possuem dados suficientes.
- [x] Task 4.2: Registrar e acompanhar itens ainda bloqueados por falta de `winget_id` validado.
- [x] Task 4.3: Preparar o ensaio do catalogo preenchido em ambiente com WinGet disponivel.
- [x] Task 4.4: Padronizar a execucao com `.venv` local e scripts de bootstrap/execucao.
- [x] Task 4.5: Implementar fallback para hosts sem WinGet acessivel.
- [x] Task 4.6: Implementar fallback por instalador direto oficial para o nucleo seguro do catalogo.
- [x] Task 4.7: Executar o primeiro teste real com `run.bat`, validando download e instalacao direta de `Visual Studio Code` e `Python 3.12`.
- [x] Task 4.8: Ajustar o bootstrap para restaurar WinGet antes de depender de Python.

## PROXIMA FASE
- [ ] Melhorar os relatorios para discriminar metodo de instalacao (`winget`, `fallback direto`, `manual`, `pending`).
- [ ] Avaliar empacotamento futuro em `.exe` depois do ensaio real.
