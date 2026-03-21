# 🏛️ Arquitetura do Sistema - Instalador de Labs

## 🧩 Camadas do Projeto
1. [cite_start]**Motor (WinGet)**: Interface direta com o Windows Package Manager[cite: 5].
2. [cite_start]**Orquestrador (Python)**: Lógica de decisão, leitura de catálogo e geração de relatórios[cite: 5].
3. [cite_start]**Memória (Obsidian)**: Fonte da verdade e registro de evolução[cite: 5, 22].

## 📂 Estrutura de Diretórios (Target)
[cite_start]O Codex deve garantir a existência desta estrutura[cite: 29]:

```text
instalador_labs/
├── main.py              # Ponto de entrada e validação de Admin [cite: 29]
├── config.py            # Configurações globais e paths [cite: 29]
├── requirements.txt     # Dependências (ex: colorama, pandas) [cite: 29]
├── brain/               # Documentação viva (Obsidian) [cite: 38]
├── packages/            # JSONs com perfis de softwares [cite: 29]
│   └── ads_lab.json     # Catálogo específico do campus [cite: 29]
├── logs/                # Histórico detalhado de execuções [cite: 29]
├── reports/             # Resumos CSV/JSON para a TI [cite: 29]
└── utils/               # Módulos de suporte [cite: 29]
    ├── __init__.py
    ├── logger.py        # Gestão de logs [cite: 29, 32]
    ├── winget.py        # Wrapper de comandos WinGet [cite: 29]
    └── package_loader.py # Leitor de perfis JSON [cite: 29]