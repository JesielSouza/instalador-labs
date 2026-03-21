# Catalogo de Softwares (Base Institucional)

| Software | ID WinGet | Tipo de Instalacao | Notas Tecnicas |
| :--- | :--- | :--- | :--- |
| **Visual Studio Code** | `Microsoft.VisualStudioCode` | `winget` | Instalacao padrao. |
| **Python 3.12** | `Python.Python.3.12` | `winget` | Requer extensao no VS Code. |
| **Figma** | `Figma.Figma` | `winget_pending` | Validar comportamento do instalador. |
| **Dev C++** | *A validar* | `winget_pending` | Verificar repositorio oficial. |
| **MySQL Workbench** | `Oracle.MySQL.Workbench` | `winget_pending` | Requer validacao de dependencias. |
| **XAMPP** | `ApacheFriends.Xampp.8.2` | `winget_pending` | Validar path de instalacao. |
| **Astah Community** | - | `manual` | Licenca estudantil; requer intervencao. |

## Legenda de Status
* **winget**: Totalmente automatizado via script.
* **winget_pending**: Em fase de teste de automacao.
* **manual**: Requer instalacao humana direta.

## Itens Bloqueados para o Perfil Executavel
* **Dev C++**: Fora do `packages/ads_lab.json` ate confirmacao de `winget_id`.

## Caso Real Seguro Atual
* O perfil `ads_lab` atual permite um ensaio controlado em maquina real.
* Itens que podem automatizar agora: `Visual Studio Code` e `Python 3.12`.
* Itens que nao serao instalados automaticamente: `Figma`, `MySQL Workbench` e `XAMPP` permanecem como `winget_pending`; `Astah Community` permanece `manual`.
