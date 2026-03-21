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
* **Contexto**: As regras do projeto proíbem automatizar itens ainda marcados como `winget_pending`, e o catalogo tambem pode conter softwares manuais.
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
