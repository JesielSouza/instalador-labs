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
- [x] Task 4.9: Melhorar os relatorios para discriminar metodo de instalacao (`winget`, `fallback direto`, `manual`, `pending`).
- [x] Task 4.10: Validar e corrigir o workflow `qa-review.yml` ate obter comentario real do Gemini em PR.
- [x] Task 4.11: Validar o empacotamento atual em `.exe` com smoke test local.
- [x] Task 4.12: Validar o fluxo branch -> PR -> comentario do Gemini -> merge em caso real.

## PROXIMA FASE
- [x] Preparar distribuicao publica via GitHub Releases com pacote `.zip` do bundle funcional.
- [ ] Evoluir o catalogo para suportar multiplos perfis e selecao de subconjuntos de pacotes pelo operador.
- [x] Introduzir modos operacionais alem de instalar, preparando base para atualizar e desinstalar via WinGet.
- [x] Estruturar downloads oficiais catalogados para softwares fora do WinGet, com URL controlada, nome de arquivo e estrategia silenciosa quando houver.
- [ ] Evoluir a interface do `.exe` para expor a escolha de operacao ao operador com validacao visual em uso real.
- [ ] Popular o catalogo com pelo menos um item manual que use `official_download` em ambiente e URL oficialmente validados.
- [x] Eliminar o ruido do caminho legado de Python 3.14 nas execucoes locais e no build.
- [x] Reavaliar `config.py` e scripts de runtime para descoberta de Python mais aderente ao host real.
- [x] Adicionar script de verificacao rapida para validar perfil ADS e executar a suite antes de PR/build.
- [x] Adicionar workflow de verificacao rapida em PR para validar perfil ADS e suite automatizada no GitHub Actions.
- [x] Validar o `.exe` em campo e adicionar feedback visual ao operador ao final da execucao.
- [ ] Refinar ainda mais a experiencia do operador no `.exe`, incluindo estudo de interface com cara de instalador tradicional, selecao de perfil e escolha de pacotes.
- [ ] Avaliar se a janela de console deve permanecer aberta ate confirmacao do operador em todos os cenarios relevantes.
- [ ] Continuar expandindo a robustez do catalogo e a validacao em maquinas mais limpas ou VMs.
- [ ] Manter a memoria versionada em `brain/` sincronizada com mudancas relevantes de produto e processo.



