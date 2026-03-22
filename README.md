# Instalador Labs

Ferramenta Windows para instalar, atualizar e desinstalar softwares de laboratorio com interface grafica, relatorio CSV e log operacional.

## O que ja esta funcional
- Selecionar perfil e escolher pacotes
- Executar `Instalar`, `Atualizar` e `Desinstalar`
- Gerar relatorio CSV por pacote
- Gerar log detalhado da execucao
- Orientar itens manuais com referencia oficial quando aplicavel

## Como usar o executavel
1. Baixe o arquivo `.zip` mais recente na aba `Releases` do repositorio.
2. Extraia o conteudo para uma pasta local.
3. Execute `InstaladorLabs.exe` como Administrador.
4. Escolha a acao, os pacotes e acompanhe a execucao pela interface.

## Onde encontrar os artefatos da execucao
Depois de rodar o instalador, a propria pasta do executavel passara a conter:
- `logs/`
- `reports/`
- `.downloads/` quando houver apoio por instalador oficial catalogado

## Desenvolvimento local
### Verificacao rapida
```powershell
./verify.ps1
```

### Gerar executavel
```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

O bundle gerado fica em `dist/InstaladorLabs/`.

## Publicacao
O repositorio possui workflow de release para gerar e publicar o pacote distribuivel do Windows em `Releases`.
