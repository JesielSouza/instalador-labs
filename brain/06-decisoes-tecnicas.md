# Registro de Decisoes Tecnicas (ADR)

## [ADR-001] - Estrutura Baseada em GSD/Obsidian
* **Contexto**: Necessidade de manter a memoria do projeto integrada a IDE.
* **Decisao**: Utilizar a pasta `brain/` dentro do workspace como fonte da verdade operacional.
* **Status**: Implementado.

## [ADR-002] - Uso do WinGet Nativo
* **Contexto**: Evitar dependencias externas complexas para instalacao.
* **Decisao**: Orquestrar comandos `winget` via Python `subprocess`.
* **Status**: Planejado.

## [ADR-003] - Bootstrap conservador com foco em estrutura
* **Contexto**: O workspace ja continha `main.py`, `utils/logger.py` e `utils/winget.py` compativeis com a tarefa inicial, mas ainda faltava materializar a estrutura restante do projeto.
* **Decisao**: Preservar o codigo-base existente e completar apenas os diretorios, arquivos auxiliares e registros de memoria definidos em [[brain/03-arquitetura]].
* **Status**: Implementado.

## [ADR-004] - Registro explicito de limitacoes do ambiente
* **Contexto**: A validacao inicial mostrou que `winget` nao estava no PATH, a pasta atual nao era um repositorio Git e o shell padrao nao possuia uma versao Python ativa por causa dos shims do `pyenv`.
* **Decisao**: Registrar os bloqueios no Obsidian, usar o interpretador real encontrado em `AppData` para validar dependencias e nao simular validacao positiva do WinGet enquanto o binario continuar indisponivel.
* **Status**: Implementado.

## [ADR-005] - Estrategia para WinGet fora do PATH
* **Contexto**: O shell atual nao resolve `winget`, e a validacao do bootstrap tambem nao encontrou os caminhos absolutos mais comuns do `WindowsApps`.
* **Decisao**: Centralizar em `config.py` a descoberta do executavel do WinGet com ordem de tentativa bem definida: `PATH` do sistema via `shutil.which`, alias absoluto em `C:\Users\Administrador\AppData\Local\Microsoft\WindowsApps\winget.exe` e caminho conhecido do App Installer. Se nenhum caminho existir, o sistema deve falhar cedo com diagnostico objetivo.
* **Status**: Implementado.

## [ADR-006] - Separacao entre memoria local e codigo versionado
* **Contexto**: As novas regras de governanca proibem subir `brain/`, logs e segredos para o GitHub.
* **Decisao**: Tratar `brain/` como memoria privada local do operador e proteger esse material com `.gitignore`, mantendo o historico tecnico tambem registrado fora do remoto.
* **Status**: Implementado.

## [ADR-007] - Push dependente de remoto explicito
* **Contexto**: O repositorio foi inicializado localmente, mas `git remote -v` veio vazio e `git push origin main` falhou no ambiente atual.
* **Decisao**: Concluir o bootstrap local com commit inicial e tratar o push como etapa dependente de um remoto `origin` configurado e de uma sessao Git sem conflito de ownership.
* **Status**: Implementado.

## [ADR-008] - Ingestao inicial sem validacao de esquema
* **Contexto**: A Fase 2 do backlog separa a simples leitura do `ads_lab.json` da validacao formal do esquema dos pacotes.
* **Decisao**: Implementar a Task 2.1 de forma enxuta, carregando o perfil padrao via `utils/package_loader.py` e conectando esse carregamento ao `main.py`, sem antecipar regras de schema que pertencem a Task 2.2.
* **Status**: Implementado.

## [ADR-009] - Schema minimo para catalogo de pacotes
* **Contexto**: O projeto ainda nao definiu um schema extenso para o `ads_lab.json`, mas ja precisava bloquear erros de digitacao que quebrariam a automacao.
* **Decisao**: Validar apenas o contrato minimo coerente com a memoria atual: raiz com `profile`, `description` e `packages`; itens de pacote com `software`, `install_type` e `winget_id` obrigatorio apenas para `winget` e `winget_pending`.
* **Status**: Implementado.

## [ADR-010] - Execucao respeitando maturidade do catalogo
* **Contexto**: As regras do projeto proÃƒÆ’Ã‚Â­bem automatizar itens ainda marcados como `winget_pending`, e o catalogo tambem pode conter softwares manuais.
* **Decisao**: O loop de execucao trata `winget` como automatizavel com checagem de idempotencia, `winget_pending` como apenas sinalizacao para teste manual e `manual` como registro sem execucao.
* **Status**: Implementado.

## [ADR-011] - Observabilidade minima por entrada de log
* **Contexto**: As regras exigem que os logs persistidos tragam timestamp, maquina, usuario e status do pacote.
* **Decisao**: Evoluir `LabLogger` para gravar `machine`, `user`, `status` e `package` no arquivo de log, mantendo a saida colorida no console.
* **Status**: Implementado.

## [ADR-012] - Relatorio CSV resumido por metricas
* **Contexto**: A Task 3.2 exigia um relatorio final em CSV, mas o projeto ainda nao precisava de granularidade por pacote ou dependencias extras.
* **Decisao**: Gerar um CSV simples em `reports/` com pares `metric,value`, derivado diretamente do resumo da execucao, suficiente para fechar a fase base sem acoplar a exportacao ao WinGet real.
* **Status**: Implementado.

## [ADR-013] - Catalogo executavel so com IDs confirmados
* **Contexto**: A base institucional lista softwares desejados, mas nem todos ja possuem `winget_id` confirmado, como o caso de `Dev C++`.
* **Decisao**: Popular o `ads_lab.json` apenas com itens que ja possuem dados suficientes para o schema e para a execucao controlada, sem inventar IDs pendentes.
* **Status**: Implementado.

## [ADR-014] - Caso real inicial limitado ao nucleo seguro
* **Contexto**: O catalogo ja esta preenchido, mas a maturidade operacional dos itens ainda e heterogenea.
* **Decisao**: Tratar o primeiro ensaio real como um teste controlado do nucleo seguro do perfil: `Visual Studio Code` e `Python 3.12` podem automatizar; `winget_pending` e `manual` apenas sinalizam no fluxo atual.
* **Status**: Implementado.

## [ADR-015] - Runtime padronizado por venv local
* **Contexto**: O uso de `python main.py` variava conforme o Python presente no PATH da maquina e quebrava o carregamento de dependencias como `colorama`.
* **Decisao**: Padronizar a execucao do projeto com `.venv` local e scripts dedicados (`bootstrap.ps1`, `run.ps1`, `bootstrap.bat`, `run.bat`), reduzindo dependencia do ambiente global.
* **Status**: Implementado.

## [ADR-016] - Modo degradado para Windows sem WinGet acessivel
* **Contexto**: Ha maquinas compativeis com o baseline do WinGet, como Windows 10 Enterprise LTSC 2019 versao 1809 build 17763, que mesmo assim podem ficar sem App Installer/WinGet acessivel.
* **Decisao**: Nesses casos, o bootstrap nao deve abortar. O sistema registra o diagnostico do Windows, segue em modo degradado e marca pacotes `winget` como `blocked`, preservando `winget_pending` e `manual` como status nao automatizados.
* **Status**: Implementado.

## [ADR-017] - Fallback direto so para o nucleo seguro do catalogo
* **Contexto**: O primeiro teste real mostrou que o modo degradado estabiliza o fluxo, mas ainda nao instala os dois pacotes principais quando o WinGet nao existe.
* **Decisao**: Implementar fallback por instalador direto oficial apenas para `Visual Studio Code` e `Python 3.12`, mantendo `winget_pending` e `manual` fora da automacao. O fluxo tenta primeiro detectar instalacao existente pelo registro do Windows e so entao baixa/executa o instalador silencioso.
* **Status**: Implementado.

## [ADR-018] - Fallback direto validado em LTSC 1809
* **Contexto**: Foi executado um ensaio real em Windows 10 Enterprise LTSC 2019 versao 1809 build 17763 sem WinGet acessivel.
* **Decisao**: Confirmar o fallback direto como caminho operacional suportado para o nucleo seguro do catalogo nesse tipo de host.
* **Status**: Validado em campo.

## [ADR-019] - Ordem de bootstrap: WinGet antes de Python
* **Contexto**: Em distribuicao real, a maquina pode nao ter Python instalado, o que inviabiliza depender do runtime Python para preparar o proprio ambiente.
* **Decisao**: O `bootstrap.ps1` deve tentar restaurar o WinGet primeiro com `Install-Module Microsoft.WinGet.Client` e `Repair-WinGetPackageManager -AllUsers`; depois resolver/instalar Python 3.12; e so entao criar a `.venv` e instalar dependencias do projeto.
* **Status**: Implementado.

## [ADR-020] - Integracao de QA por GitHub Actions com Gemini
* **Contexto**: O repositorio passa a operar com desenvolvimento em branches dedicadas, PR individual por entrega e revisao automatizada antes do merge.
* **Decisao**: Adotar o workflow `qa-review.yml` no GitHub Actions para disparar revisao automatica do Gemini sempre que um PR for aberto ou atualizado.
* **Decisao**: O Codex deve ler o comentario do Gemini antes de qualquer decisao sobre merge, follow-up tecnico ou resposta no PR.
* **Decisao**: Merge automatico so e permitido quando o Gemini aprovar o PR sem erros criticos; em caso de erro de logica, ausencia de tratamento de erro, risco de falha em producao ou comportamento indefinido em cenarios de excecao, o merge deve ser bloqueado e escalado ao humano.
* **Status**: Aprovado para adocao operacional.

## [ADR-021] - QA com Gemini validado em PR real
* **Contexto**: Depois de registrar a governanca de PR e corrigir problemas de YAML e permissao no `qa-review.yml`, o fluxo precisava ser exercitado de ponta a ponta em um caso real.
* **Decisao**: Considerar o gate de QA com Gemini operacionalmente validado apenas apos um PR real em branch dedicada receber comentario automatizado com sucesso e seguir ate merge.
* **Decisao**: A partir desta validacao, o proximo foco deixa de ser a infraestrutura de PR e volta para melhorias do produto e reducao de ruido operacional no runtime.
* **Status**: Validado em campo.

## [ADR-022] - Versionamento da memoria operacional em `brain/`
* **Contexto**: As iteracoes recentes do produto e do fluxo de PR passaram a depender fortemente das anotacoes em `brain/`, e manter isso apenas local gerava defasagem entre estado real e memoria do projeto.
* **Decisao**: A pasta `brain/` passa a ser versionada no repositorio como memoria operacional oficial, devendo ser atualizada junto com mudancas relevantes de produto, QA e runtime.
* **Decisao**: Apenas artefatos temporarios, logs, relatorios locais e segredos continuam fora do versionamento.
* **Status**: Aprovado para adocao imediata.
## [ADR-023] - Separacao entre recursos do bundle e artefatos do operador
* **Contexto**: O executavel empacotado precisa ler o catalogo e demais recursos do bundle do PyInstaller, mas logs, relatorios e downloads devem ficar em local visivel ao operador ao lado do .exe.
* **Decisao**: Separar `RESOURCE_DIR` e `RUNTIME_DIR` em `config.py`, mantendo `packages/` no bundle e redirecionando `logs/`, `reports/` e `.downloads/` para o diretorio do executavel quando rodar empacotado.
* **Status**: Implementado.

## [ADR-024] - Feedback visual obrigatorio no encerramento do executavel
* **Contexto**: Na validacao real, o `.exe` concluiu a execucao corretamente, mas a ausencia de uma confirmacao visual ao operador dava a impressao de encerramento silencioso.
* **Decisao**: Exibir uma mensagem final com resumo da execucao e caminho do relatorio quando o fluxo rodar como executavel empacotado, e exibir tambem erros criticos de bootstrap/catalogo ao operador.
* **Status**: Implementado e validado em campo.

## [ADR-025] - Otimizacao de PRs para economizar cota do Gemini
* **Contexto**: O uso em conta gratuita do Gemini exige reduzir disparos desnecessarios do workflow de QA em PRs pequenas ou excessivamente iterativas.
* **Decisao**: Consolidar mudancas relacionadas na branch `trabalho/codex`, abrir PR apenas quando o bloco estiver maduro e evitar pushes intermediarios desnecessarios em PR aberta.
* **Status**: Aprovado para adocao imediata.



## [ADR-026] - Downloads oficiais catalogados em vez de busca aberta na web
* **Contexto**: Itens fora do WinGet ainda precisam de tratamento assistido, mas a busca aberta por instaladores na web introduz risco alto de origem incorreta, quebra de URL e variacao nao auditada.
* **Decisao**: O catalogo passa a aceitar `official_download` com URL controlada e nome de arquivo opcional, reutilizando a pasta `.downloads` do produto e registrando o caminho no resultado por pacote.
* **Consequencia**: Itens manuais podem orientar o operador com download oficial assistido sem abrir espaco para scraping generico ou busca aberta fora do catalogo.
* **Status**: Implementado.

## [ADR-027] - Distribuicao publica via GitHub Releases
* **Contexto**: O executavel ja atingiu um nivel de maturidade que permite distribuicao para uso real, mas `dist/` nao deve ser versionado diretamente no repositorio.
* **Decisao**: Publicar o bundle funcional do Windows via GitHub Releases, gerado por workflow dedicado e compactado em `.zip`, mantendo o repositorio limpo e reprodutivel.
* **Consequencia**: O download do instalador passa a acontecer pela aba `Releases`, com README orientando o uso e o workflow cuidando da publicacao.
* **Status**: Implementado.

## [ADR-028] - Comandos do WinGet devem fixar `--source winget` e `--exact`
* **Contexto**: Em validacao real do `InstaladorLabs.exe`, a instalacao de `Visual Studio Code` podia travar por prompt interativo da `msstore`, apesar do fluxo ja enviar os flags de aceite de contratos.
* **Decisao**: Todos os comandos de `list`, `install`, `upgrade` e `uninstall` por `--id` devem fixar `--source winget` e `--exact` para evitar resolucao ambigua de fonte e impedir prompts interativos inesperados da Microsoft Store.
* **Consequencia**: O fluxo automatizado deixa de depender do estado da `msstore` para itens do catalogo que devem sair pelo repositorio principal do WinGet.
* **Status**: Implementado e validado em campo.

## [ADR-029] - Publicacao do bundle deve preservar caminho estavel e orientar o operador em caso de lock
* **Contexto**: O `build_exe.ps1` conseguia gerar o bundle do PyInstaller, mas podia falhar ao publicar o resultado quando o diretorio `dist\InstaladorLabs` estivesse bloqueado por um executavel ainda aberto ou por arquivos em uso.
* **Decisao**: O script de build deve sempre preservar `dist\InstaladorLabs` como caminho final esperado pelo workflow de release, tentar publicacao direta primeiro e cair para sincronizacao robusta no mesmo caminho; se ainda houver falha por lock, deve exibir instrucoes objetivas para o operador fechar o app e repetir o build.
* **Consequencia**: O processo de release continua compativel com o workflow do GitHub e o troubleshooting local fica ensinavel ao usuario sem depender de interpretacao de erro cru do PowerShell.
* **Status**: Implementado e validado operacionalmente.

## [ADR-030] - Reparo automatico de fontes quebradas do WinGet
* **Contexto**: O WinGet pode ter suas fontes de pacotes corrompidas, causando falhas `winget source list` sem contudo significar que o cliente esta completamente quebrado.
* **Decisao**: Antes de marcar um pacote como falha, o instalador deve tentar `winget source repair` para recuperar as fontes padrao e entao re-tentar a operacao.
* **Consequencia**: Falhas transitórias por fonte corrompida sao recuperadas automaticamente sem escalar para fallback direto.
* **Status**: Implementado.

## [ADR-031] - Fallback direto apos falha recuperavel do WinGet
* **Contexto**: Apos tentativa de repair das fontes, se o WinGet ainda falhar por motivo recuperavel (fonte ainda indisponivel), o fluxo deve desviar para o instalador direto oficial sem marcar como falha definitiva.
* **Decisao**: Classificar o erro em recuperavel vs. definitivo; fallbacks devem ser acionados para erros recuperaveis apos exhausted de estrategias nativas.
* **Consequencia**: Maquinas com fontes temporariamente indisponiveis nao bloqueiam a instalacao.
* **Status**: Implementado.

## [ADR-032] - Bypass automatico do WinGet quebrado no Windows 11
* **Contexto**: Em Windows 11, o WinGet pode estar instalado porem com estado irremediavelmente quebrado, onde nem `repair` resolve. Nessas maquinas, insistir no WinGet causara delay desnecessario.
* **Decisao**: Detectar o estado quebrado do WinGet no Win11 via diagnostico de comando e desviar automaticamente para fallback direto, sem tentar repair ou outros comandos nativos.
* **Consequencia**: Maquinas Win11 com WinGet inoperante instalam via caminho direto sem intervencao do operador.
* **Status**: Implementado.

## [ADR-033] - Deteccao e aviso de proxy antes de instalacoes
* **Contexto**: Redes corporativas com proxy podem bloquear instalacoes automatizadas sem feedback claro ao operador.
* **Decisao**: Detectar configuracao de proxy do sistema antes de iniciar instalacoes via WinGet e exibir aviso explicito ao operador.
* **Consequencia**: O operador e alertado sobre possiveis bloqueios de rede antes do inicio do processo, evitando falhas confusas.
* **Status**: Implementado.

## [ADR-034] - Deteccao de pacotes ja instalados antes de tentar instalar
* **Contexto**: Reinstalacoes desnecessarias causam ruido no log, delay e potenciais problemas em ambientes ja configurados.
* **Decisao**: Antes de tentar qualquer instalacao (winget ou fallback), verificar se o pacote ja esta instalado e registrar como `already_installed`, pulando a operacao.
* **Consequencia**: O log reflete o estado real da maquina e o operador ve apenas operacoes realmente necessarias.
* **Status**: Implementado.

## [ADR-035] - Validacao de pre-requisitos por perfil do catalogo
* **Contexto**: Diferentes perfis de laboratorio podem ter pre-requisitos diferentes, e tentar instalar sem satisface-los pode causar falhas em cadeia.
* **Decisao**: O catalogo aceita um bloco `prerequisites` por perfil; o carregador valida antes de executar qualquer plano de instalacao.
* **Consequencia**: Falhas por dependencia faltante sao identificadas cedo, com mensagem clara ao operador.
* **Status**: Implementado.

## [ADR-036] - Retry de downloads via PowerShell em erros SSL/TLS
* **Contexto**: Downloads diretos podem falhar por configuracao SSL restritiva ou certificados invalidos, mesmo com URLsHTTPS validas.
* **Decisao**: Quando o download direto falhar por erro SSL/TLS, tentar novamente via `System.Net.WebClient` do PowerShell com configuracao mais permissiva.
* **Consequencia**: Downloads em ambientes corporativos com SSL restritivo tem taxa de sucesso significativamente maior.
* **Status**: Implementado.

## [ADR-037] - Log confiavel de versoes do Windows e WinGet
* **Contexto**: Diagnosticos remotos dependem de informacao precisa de versao, mas`winget --version` pode falhar ou retornar formato inconfiavel.
* **Decisao**: Registrar versoes via multiplas fontes (registro do Windows, `winget --version`, `sysinfo`) e usar o valor mais confiavel disponivel.
* **Consequencia**: Logs de falha contem informacao de versao confiavel para reproduzir o ambiente.
* **Status**: Implementado.

## [ADR-038] - Menu interativo do .exe consolidando operacao, perfil e pacotes
* **Contexto**: O operador precisa de uma interface clara para escolher o que fazer, contra quem, e em qual escopo.
* **Decisao**: Menu interativo no console do .exe com tres fases: escolha da operacao (instalar/atualizar/desinstalar), escolha do perfil, e escolha dos pacotes.
* **Consequencia**: A experiencia do operador se aproxima de um instalador tradicional com controles faceis de entender.
* **Status**: Implementado na v0.2.0.

## [ADR-039] - Schema do catalogo deve falhar cedo para URLs e artefatos ambiguos
* **Contexto**: O catalogo passou a carregar semantica operacional critica demais para continuar aceitando entradas ambiguas ou inseguras, como URLs sem HTTPS, `file_name` com diretorios ou extensoes incoerentes.
* **Decisao**: Endurecer `utils/package_loader.py` para validar HTTPS com host valido, proibir `file_name` com caminho embutido, restringir extensoes de artefato suportadas e bloquear combinacoes ambiguas como `manual` com `fallback_installer`.
* **Consequencia**: Erros de catalogo passam a ser detectados antes da execucao, reduzindo falhas confusas em maquina real.
* **Status**: Implementado na branch `fix/harden-runtime-and-catalog`.

## [ADR-040] - Fallback direto deve validar artefato baixado alem do magic header
* **Contexto**: Apenas checar `MZ` ou assinatura MSI no cabecalho ainda permite payloads pequenos ou claramente quebrados passarem pela validacao basica.
* **Decisao**: O `DirectInstallerManager` deve validar tambem tamanho minimo do arquivo e produzir diagnostico explicito da causa de invalidacao do artefato.
* **Consequencia**: Downloads corrompidos, truncados ou HTML disfarcado sao rejeitados mais cedo, com mensagem mais acionavel para troubleshooting.
* **Status**: Implementado na branch `fix/harden-runtime-and-catalog`.

## [ADR-041] - Diagnosticos de runtime nao devem morar no main.py
* **Contexto**: `main.py` vinha acumulando diagnosticos de reboot, host, runtime, conectividade e mensagens ao operador, aumentando acoplamento e tornando o fluxo principal mais dificil de manter.
* **Decisao**: Extrair o suporte de runtime e operator messaging para `utils/runtime_support.py`, mantendo `main.py` como orquestrador do fluxo principal.
* **Consequencia**: O codigo fica mais modular, com menor concentracao de responsabilidade em `main.py`, sem trocar o comportamento funcional do produto.
* **Status**: Implementado na branch `fix/harden-runtime-and-catalog`.

## [ADR-042] - Relatorio e resumo de execucao devem viver fora do main.py
* **Contexto**: Depois da extracao do suporte de runtime, `main.py` ainda concentrava classificacao diagnostica, resumo textual ao operador e geracao do CSV final, que formam um bloco coeso e testavel por si so.
* **Decisao**: Extrair esse bloco para `utils/reporting.py`, mantendo wrappers finos em `main.py` para preservar contrato funcional e evitar regressao no restante do fluxo.
* **Consequencia**: O codigo de relatorio fica mais modular e reutilizavel, enquanto `main.py` continua encolhendo sem quebrar a API interna usada pelos testes e pelo runtime.
* **Status**: Implementado na branch `refactor/extract-preflight-and-reporting`.

## [ADR-043] - Bootstrap e carregamento de catalogo devem ser extraidos com injecao de dependencias
* **Contexto**: `main.py` ainda concentrava validacao de ambiente, diagnosticos de bootstrap e carregamento/sondagem do catalogo. Ao extrair esse bloco, os testes existentes dependiam de mocks em `main.py`, o que seria quebrado por imports diretos no modulo novo.
* **Decisao**: Extrair o bloco para `utils/bootstrap_support.py`, mas com injecao explicita das dependencias usadas no carregamento de catalogo e nas validacoes do bootstrap, preservando a mockabilidade e o contrato funcional do wrapper em `main.py`.
* **Consequencia**: O `main.py` encolhe mais um bloco grande sem sacrificar testabilidade; a extracao fica modular e os testes continuam representando o comportamento real esperado pelo projeto.
* **Status**: Implementado na branch `refactor/extract-bootstrap-from-main`.
