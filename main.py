import csv
import ctypes
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

from config import DOWNLOADS_DIR, LOGS_DIR, REPORTS_DIR
from utils.fallback_installer import DirectInstallerManager
from utils.logger import LabLogger
from utils.package_loader import (
    PackageProfileValidationError,
    PackageSelectionError,
    build_dynamic_package_profile,
    build_profile_endpoint_diagnostics,
    list_package_profiles,
    load_default_package_profile,
    load_package_profile,
    load_profile_by_name,
    save_package_profile,
    select_profile_packages,
    validate_package_profile,
)
from utils.runtime_support import (
    MB_ICONERROR,
    MB_ICONINFORMATION,
    MB_ICONWARNING,
    OperatorVisibleError,
    fail_with_operator_message as runtime_fail_with_operator_message,
    get_host_capacity_diagnostics,
    get_pending_reboot_diagnostics,
    get_runtime_directory_diagnostics,
    is_admin,
    is_frozen_runtime,
    probe_catalog_endpoint_connectivity,
    show_operator_message,
)
from utils.reporting import (
    OPERATION_TITLES,
    SUMMARY_LAYOUTS,
    build_execution_summary_text as reporting_build_execution_summary_text,
    classify_package_result as reporting_classify_package_result,
    summarize_execution_diagnostics as reporting_summarize_execution_diagnostics,
    write_execution_report as reporting_write_execution_report,
)
from utils.bootstrap_support import (
    bootstrap_environment,
    load_catalog_profile,
)
from utils.winget import WinGetManager

_OPERATOR_WINDOW_ACTIVE = False


def fail_with_operator_message(message: str, exit_code: int = 1, title: str = "Instalador Labs - Erro"):
    return runtime_fail_with_operator_message(
        message,
        operator_window_active=_OPERATOR_WINDOW_ACTIVE,
        exit_code=exit_code,
        title=title,
    )


ALLOWED_OPERATIONS = ("install", "update", "uninstall")
OPERATION_TITLES = {
    "install": "Instalacao",
    "update": "Atualizacao",
    "uninstall": "Desinstalacao",
}
OPERATION_BUTTON_LABELS = {
    "install": "Iniciar instalacao",
    "update": "Iniciar atualizacao",
    "uninstall": "Iniciar desinstalacao",
}
SUMMARY_LAYOUTS = {
    "install": [
        ("installed", "Instalados"),
        ("already_installed", "Ja presentes"),
        ("pending", "Pendentes"),
        ("manual", "Manuais"),
        ("failed", "Falhas"),
        ("blocked", "Bloqueados"),
    ],
    "update": [
        ("updated", "Atualizados"),
        ("not_installed", "Nao instalados"),
        ("pending", "Pendentes"),
        ("manual", "Manuais"),
        ("failed", "Falhas"),
        ("blocked", "Bloqueados"),
    ],
    "uninstall": [
        ("removed", "Removidos"),
        ("not_installed", "Nao instalados"),
        ("pending", "Pendentes"),
        ("manual", "Manuais"),
        ("failed", "Falhas"),
        ("blocked", "Bloqueados"),
    ],
}



def create_logger(logger_observer=None):
    """Cria o logger principal do fluxo."""
    return LabLogger(observer=logger_observer)


def normalize_operation(operation: str | None) -> str:
    """Normaliza e valida o modo de operacao solicitado."""
    candidate = (operation or "install").strip().lower()
    if candidate not in ALLOWED_OPERATIONS:
        raise ValueError(f"Operacao invalida: {operation}")
    return candidate


def build_summary_template(operation: str) -> dict:
    """Cria um resumo vazio compativel com a operacao selecionada."""
    normalized_operation = normalize_operation(operation)
    return {key: 0 for key, _label in SUMMARY_LAYOUTS[normalized_operation]}


def build_execution_summary_text(profile: dict, results: dict, report_path: Path, log_path: Path) -> str:
    """Monta um resumo amigavel para o operador ao final da execucao."""
    return reporting_build_execution_summary_text(
        profile,
        results,
        report_path,
        log_path,
        allowed_operations=ALLOWED_OPERATIONS,
    )


def _open_target_for_operator(target: Path | str):
    """Abre um arquivo, pasta ou URL do instalador para o operador no Windows."""
    os.startfile(str(target))


def _ensure_catalog_prerequisites(package, logger, direct_installer):
    """Valida e tenta instalar pre-requisitos declarados no catalogo antes do pacote principal."""
    prerequisites = package.get("prerequisites", [])
    if not prerequisites:
        return {"ready": True, "detail": ""}

    for prerequisite in prerequisites:
        prerequisite_name = prerequisite.get("software", "Pre-requisito")
        if direct_installer.is_package_present(prerequisite):
            logger.info(
                f"Pre-requisito '{prerequisite_name}' ja presente para '{package['software']}'.",
                status="prerequisite_present",
                package_name=package["software"],
            )
            continue

        if not prerequisite.get("fallback_installer"):
            detail = (
                f"Pre-requisito '{prerequisite_name}' ausente e sem automacao configurada no catalogo."
            )
            logger.error(
                detail,
                status="prerequisite_missing",
                package_name=package["software"],
            )
            return {"ready": False, "detail": detail}

        logger.warning(
            f"Pre-requisito '{prerequisite_name}' ausente para '{package['software']}'. Tentando instalar antes do pacote principal.",
            status="prerequisite_installing",
            package_name=package["software"],
        )
        if direct_installer.install_package(prerequisite, logger):
            logger.info(
                f"Pre-requisito '{prerequisite_name}' instalado para '{package['software']}'.",
                status="prerequisite_installed",
                package_name=package["software"],
            )
            continue

        detail = f"Falha ao instalar o pre-requisito '{prerequisite_name}' antes de '{package['software']}'."
        logger.error(
            detail,
            status="prerequisite_error",
            package_name=package["software"],
        )
        return {"ready": False, "detail": detail}

    return {"ready": True, "detail": ""}


def launch_operator_runtime_window():
    """Abre uma janela unica para acompanhar a execucao do instalador."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    operation_display_map = {
        "Instalar": "install",
        "Atualizar": "update",
        "Desinstalar": "uninstall",
    }
    display_by_operation = {value: key for key, value in operation_display_map.items()}

    global _OPERATOR_WINDOW_ACTIVE
    _OPERATOR_WINDOW_ACTIVE = True

    event_queue = Queue()
    state = {
        "report_path": None,
        "log_path": None,
        "folder_path": None,
        "manual_reference_url": None,
        "running": False,
        "has_completed": False,
        "search_results": [],
        "visible_search_results": [],
        "selected_dynamic_packages": [],
        "selection_label": "Busca dinamica WinGet",
        "prepare_details_visible": False,
    }

    root = tk.Tk()
    root.title("Instalador Labs")
    root.minsize(720, 500)
    root.configure(bg="#eef2f5")

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("App.TFrame", background="#eef2f5")
    style.configure("Card.TFrame", background="#ffffff")
    style.configure("App.TLabel", background="#eef2f5", foreground="#1f2937", font=("Segoe UI", 10))
    style.configure("Muted.TLabel", background="#eef2f5", foreground="#5b6472", font=("Segoe UI", 10))
    style.configure("Section.TLabelframe", background="#eef2f5", borderwidth=0)
    style.configure("Section.TLabelframe.Label", background="#eef2f5", foreground="#16202a", font=("Segoe UI Semibold", 10))
    style.configure("Primary.TButton", font=("Segoe UI Semibold", 10))
    style.configure("TButton", padding=(10, 6))
    style.configure("TCombobox", padding=4)
    style.configure("Wizard.TNotebook", background="#eef2f5", borderwidth=0)
    style.configure("Wizard.TNotebook.Tab", padding=(14, 8), font=("Segoe UI Semibold", 10))
    style.configure("Package.Horizontal.TProgressbar", troughcolor="#dce4ec", background="#175cd3", bordercolor="#dce4ec", lightcolor="#175cd3", darkcolor="#175cd3")
    style.configure("PackageSuccess.Horizontal.TProgressbar", troughcolor="#dcefe1", background="#067647", bordercolor="#dcefe1", lightcolor="#067647", darkcolor="#067647")
    style.configure("PackageWarning.Horizontal.TProgressbar", troughcolor="#f7ead0", background="#b54708", bordercolor="#f7ead0", lightcolor="#b54708", darkcolor="#b54708")
    style.configure("PackageError.Horizontal.TProgressbar", troughcolor="#f4d7d5", background="#b42318", bordercolor="#f4d7d5", lightcolor="#b42318", darkcolor="#b42318")

    viewport = ttk.Frame(root, style="App.TFrame")
    viewport.pack(fill="both", expand=True)

    container_canvas = tk.Canvas(
        viewport,
        bg="#eef2f5",
        highlightthickness=0,
        borderwidth=0,
    )
    container_scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=container_canvas.yview)
    container_canvas.configure(yscrollcommand=container_scrollbar.set)
    container_scrollbar.pack(side="right", fill="y")
    container_canvas.pack(side="left", fill="both", expand=True)

    container = ttk.Frame(container_canvas, padding=16, style="App.TFrame")
    canvas_window = container_canvas.create_window((0, 0), window=container, anchor="nw")

    def _sync_container_width(_event=None):
        container_canvas.itemconfigure(canvas_window, width=container_canvas.winfo_width())

    def _refresh_scroll_region(_event=None):
        container_canvas.configure(scrollregion=container_canvas.bbox("all"))

    def _on_mousewheel(event):
        if event.delta:
            container_canvas.yview_scroll(int(-event.delta / 120), "units")
        elif getattr(event, "num", None) == 4:
            container_canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            container_canvas.yview_scroll(1, "units")

    container.bind("<Configure>", _refresh_scroll_region)
    container_canvas.bind("<Configure>", _sync_container_width)
    root.bind_all("<MouseWheel>", _on_mousewheel)

    status_var = tk.StringVar(value="Pronto para iniciar a instalacao automatizada.")
    hero_frame = tk.Frame(container, bg="#12344a", padx=18, pady=16)
    hero_frame.pack(fill="x")

    tk.Label(
        hero_frame,
        text="Instalador Labs",
        font=("Segoe UI", 19, "bold"),
        fg="#ffffff",
        bg="#12344a",
    ).pack(anchor="w")
    tk.Label(
        hero_frame,
        text="Execucao assistida para laboratorio com foco em diagnostico rapido e operacao em lote.",
        font=("Segoe UI", 10),
        fg="#d6e3ec",
        bg="#12344a",
    ).pack(anchor="w", pady=(4, 10))

    status_banner_var = tk.StringVar(value="Pronto")
    status_banner = tk.Label(
        hero_frame,
        textvariable=status_banner_var,
        font=("Segoe UI Semibold", 10),
        fg="#12344a",
        bg="#d9f2e3",
        padx=10,
        pady=5,
    )
    status_banner.pack(anchor="w")

    ttk.Label(
        container,
        textvariable=status_var,
        style="Muted.TLabel",
    ).pack(anchor="w", pady=(8, 12))

    notebook = ttk.Notebook(container, style="Wizard.TNotebook")
    notebook.pack(fill="both", expand=True)

    prepare_tab = ttk.Frame(notebook, style="App.TFrame", padding=(0, 4, 0, 0))
    selection_tab = ttk.Frame(notebook, style="App.TFrame", padding=(0, 4, 0, 0))
    execution_tab = ttk.Frame(notebook, style="App.TFrame", padding=(0, 4, 0, 0))

    notebook.add(prepare_tab, text="1. Preparar")
    notebook.add(selection_tab, text="2. Selecionar")
    notebook.add(execution_tab, text="3. Executar")

    prepare_intro_frame = tk.Frame(
        prepare_tab,
        bg="#ffffff",
        padx=18,
        pady=18,
        highlightthickness=1,
        highlightbackground="#d8dee6",
    )
    prepare_intro_frame.pack(fill="x", pady=(0, 12))

    prepare_summary_title_var = tk.StringVar(value="Inspecao aguardando")
    prepare_summary_detail_var = tk.StringVar(
        value="Esta aba deve responder se a maquina esta pronta, com atencoes ou bloqueada para a execucao."
    )

    prepare_intro_text = tk.Frame(prepare_intro_frame, bg="#ffffff")
    prepare_intro_text.pack(side="left", fill="x", expand=True)

    tk.Label(
        prepare_intro_text,
        textvariable=prepare_summary_title_var,
        font=("Segoe UI", 16, "bold"),
        fg="#16202a",
        bg="#ffffff",
        anchor="w",
    ).pack(anchor="w")
    tk.Label(
        prepare_intro_text,
        textvariable=prepare_summary_detail_var,
        font=("Segoe UI", 10),
        fg="#4b5563",
        bg="#ffffff",
        justify="left",
        wraplength=620,
        anchor="w",
    ).pack(anchor="w", pady=(6, 0))

    prepare_toggle_button = ttk.Button(prepare_intro_frame, text="Ver diagnostico tecnico")
    prepare_toggle_button.pack(side="right", padx=(16, 0))

    phase_frame = ttk.LabelFrame(prepare_tab, text="Etapas da execucao", style="Section.TLabelframe")
    phase_frame.pack(fill="x", pady=(0, 12))
    ttk.Label(
        phase_frame,
        text="Acompanhe rapidamente em que fase a maquina esta.",
        style="Muted.TLabel",
    ).pack(anchor="w", padx=10, pady=(4, 0))

    phase_row = tk.Frame(phase_frame, bg="#eef2f5")
    phase_row.pack(fill="x", padx=10, pady=(8, 10))
    phase_indicators = {}

    def create_phase_indicator(parent, key, title):
        wrapper = tk.Frame(parent, bg="#eef2f5")
        wrapper.pack(side="left", fill="x", expand=True)
        card = tk.Frame(wrapper, bg="#ffffff", padx=10, pady=10, highlightthickness=1, highlightbackground="#d8dee6")
        card.pack(fill="x")
        title_label = tk.Label(
            card,
            text=title,
            font=("Segoe UI Semibold", 9),
            fg="#16202a",
            bg="#ffffff",
            anchor="w",
        )
        title_label.pack(anchor="w")
        state_label = tk.Label(
            card,
            text="Aguardando",
            font=("Segoe UI Semibold", 10),
            fg="#475467",
            bg="#ffffff",
            anchor="w",
        )
        state_label.pack(anchor="w", pady=(6, 0))
        phase_indicators[key] = {
            "frame": card,
            "title": title_label,
            "state": state_label,
        }

    phase_titles = [
        ("preflight", "1. Preflight"),
        ("catalog", "2. Catalogo"),
        ("execution", "3. Instalacao"),
        ("report", "4. Relatorio"),
    ]
    for index, (phase_key, phase_title) in enumerate(phase_titles):
        create_phase_indicator(phase_row, phase_key, phase_title)
        if index < len(phase_titles) - 1:
            tk.Label(
                phase_row,
                text=">",
                font=("Segoe UI Semibold", 12),
                fg="#98a2b3",
                bg="#eef2f5",
                padx=6,
            ).pack(side="left")

    prepare_details_section = ttk.Frame(prepare_tab, style="App.TFrame")
    prepare_details_section.pack(fill="x", pady=(0, 0))

    overview_row = ttk.Frame(prepare_details_section, style="App.TFrame")
    overview_row.pack(fill="x", pady=(0, 12))

    profile_card_var = tk.StringVar(value="Modo ativo\nBusca dinamica WinGet")
    action_card_var = tk.StringVar(value="Acao\nInstalacao")
    packages_card_var = tk.StringVar(value="Pacotes marcados\n0/0")

    def create_overview_card(parent, variable):
        card = tk.Frame(parent, bg="#ffffff", padx=14, pady=12, highlightthickness=1, highlightbackground="#d8dee6")
        label = tk.Label(
            card,
            textvariable=variable,
            justify="left",
            anchor="w",
            font=("Segoe UI Semibold", 10),
            fg="#16202a",
            bg="#ffffff",
        )
        label.pack(fill="both", expand=True)
        return card

    profile_card = create_overview_card(overview_row, profile_card_var)
    profile_card.pack(side="left", fill="x", expand=True)
    action_card = create_overview_card(overview_row, action_card_var)
    action_card.pack(side="left", fill="x", expand=True, padx=10)
    packages_card = create_overview_card(overview_row, packages_card_var)
    packages_card.pack(side="left", fill="x", expand=True)

    preflight_frame = ttk.LabelFrame(prepare_details_section, text="Preflight da maquina", style="Section.TLabelframe")
    preflight_frame.pack(fill="x", pady=(0, 12))
    ttk.Label(
        preflight_frame,
        text="Leitura rapida dos sinais mais importantes antes e durante a execucao.",
        style="Muted.TLabel",
    ).pack(anchor="w", padx=10, pady=(4, 0))

    preflight_grid = tk.Frame(preflight_frame, bg="#eef2f5")
    preflight_grid.pack(fill="x", padx=10, pady=(8, 10))

    preflight_indicators = {}

    def create_preflight_indicator(parent, row, column, key, title):
        card = tk.Frame(parent, bg="#ffffff", padx=10, pady=10, highlightthickness=1, highlightbackground="#d8dee6")
        card.grid(row=row, column=column, sticky="nsew", padx=4, pady=4)
        title_label = tk.Label(
            card,
            text=title,
            font=("Segoe UI Semibold", 9),
            fg="#16202a",
            bg="#ffffff",
            anchor="w",
        )
        title_label.pack(anchor="w")
        state_label = tk.Label(
            card,
            text="Aguardando",
            font=("Segoe UI Semibold", 10),
            fg="#475467",
            bg="#ffffff",
            anchor="w",
        )
        state_label.pack(anchor="w", pady=(6, 2))
        detail_label = tk.Label(
            card,
            text="Sem leitura ainda",
            font=("Segoe UI", 8),
            fg="#667085",
            bg="#ffffff",
            justify="left",
            wraplength=170,
            anchor="w",
        )
        detail_label.pack(anchor="w", fill="x")
        preflight_indicators[key] = {
            "frame": card,
            "title": title_label,
            "state": state_label,
            "detail": detail_label,
        }

    for column in range(4):
        preflight_grid.columnconfigure(column, weight=1)

    indicator_titles = [
        ("admin", "Administrador"),
        ("winget", "WinGet"),
        ("store", "Store/App Installer"),
        ("network", "Rede"),
        ("capacity", "Espaco/Arquitetura"),
        ("update", "Windows Update"),
        ("security", "Seguranca"),
        ("reboot", "Reinicializacao"),
    ]
    for index, (indicator_key, indicator_title) in enumerate(indicator_titles):
        create_preflight_indicator(preflight_grid, index // 4, index % 4, indicator_key, indicator_title)

    selection_frame = ttk.LabelFrame(selection_tab, text="Selecao", style="Section.TLabelframe")
    selection_frame.pack(fill="x")

    selection_intro = ttk.Label(
        selection_frame,
        text="Pesquise qualquer programa no WinGet, revise os resultados e monte sua fila de execucao.",
        style="Muted.TLabel",
    )
    selection_intro.pack(anchor="w", padx=10, pady=(8, 0))

    search_row = ttk.Frame(selection_frame)
    search_row.pack(fill="x", padx=10, pady=(10, 6))

    ttk.Label(search_row, text="Programa", style="App.TLabel").pack(side="left")
    search_query_var = tk.StringVar(value="")
    search_entry = ttk.Entry(search_row, textvariable=search_query_var, width=36)
    search_entry.pack(side="left", padx=(8, 0))

    ttk.Label(search_row, text="Acao", style="App.TLabel").pack(side="left", padx=(12, 0))
    action_var = tk.StringVar(value=display_by_operation["install"])
    action_combo = ttk.Combobox(
        search_row,
        textvariable=action_var,
        state="readonly",
        values=list(operation_display_map.keys()),
        width=14,
    )
    action_combo.pack(side="left", padx=(8, 0))

    search_button = ttk.Button(search_row, text="Pesquisar")
    search_button.pack(side="left", padx=(8, 0))

    open_profile_button = ttk.Button(search_row, text="Abrir perfil")
    open_profile_button.pack(side="left", padx=(8, 0))

    show_generic_results_var = tk.BooleanVar(value=False)
    show_generic_check = ttk.Checkbutton(search_row, text="Mostrar genericos", variable=show_generic_results_var)
    show_generic_check.pack(side="left", padx=(8, 0))

    search_status_var = tk.StringVar(value="Pesquise qualquer programa disponivel no WinGet.")
    ttk.Label(search_row, textvariable=search_status_var, style="Muted.TLabel").pack(side="left", padx=(12, 0))

    selection_status_var = tk.StringVar(value="")
    selection_status_bar = tk.Frame(selection_frame, bg="#ffffff", padx=12, pady=10, highlightthickness=1, highlightbackground="#d8dee6")
    selection_status_bar.pack(fill="x", padx=10, pady=(4, 10))
    ttk.Label(selection_status_bar, textvariable=selection_status_var, style="App.TLabel").pack(side="left")
    ttk.Label(
        selection_status_bar,
        text="Dica: deixe na fila apenas o que voce realmente quer executar agora.",
        style="Muted.TLabel",
    ).pack(side="right")

    workspace_row = ttk.Frame(selection_frame)
    workspace_row.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    search_results_frame = ttk.LabelFrame(workspace_row, text="Resultados encontrados", style="Section.TLabelframe")
    search_results_frame.pack(side="left", fill="both", expand=True)
    ttk.Label(
        search_results_frame,
        text="Escolha resultados confiaveis e envie para a fila.",
        style="Muted.TLabel",
    ).pack(anchor="w", padx=10, pady=(4, 0))

    search_results_row = ttk.Frame(search_results_frame)
    search_results_row.pack(fill="x", padx=10, pady=(8, 10))

    search_results_listbox = tk.Listbox(
        search_results_row,
        selectmode="extended",
        exportselection=False,
        height=6,
        font=("Segoe UI", 10),
        bg="#ffffff",
        fg="#16202a",
        selectbackground="#1d6fa5",
        selectforeground="#ffffff",
        relief="flat",
        highlightthickness=1,
        highlightbackground="#d8dee6",
        activestyle="none",
    )
    search_results_listbox.pack(side="left", fill="x", expand=True)

    search_results_scrollbar = ttk.Scrollbar(search_results_row, orient="vertical", command=search_results_listbox.yview)
    search_results_scrollbar.pack(side="left", fill="y")
    search_results_listbox.configure(yscrollcommand=search_results_scrollbar.set)

    search_results_actions = ttk.Frame(search_results_row)
    search_results_actions.pack(side="left", padx=(10, 0))

    add_result_button = ttk.Button(search_results_actions, text="Adicionar a fila")
    add_result_button.pack(fill="x")

    result_details_var = tk.StringVar(value="Selecione um resultado para ver detalhes de ID, versao e origem.")
    ttk.Label(search_results_frame, textvariable=result_details_var, style="Muted.TLabel").pack(anchor="w", padx=10, pady=(0, 8))

    package_panel = ttk.LabelFrame(workspace_row, text="Fila de execucao", style="Section.TLabelframe")
    package_panel.pack(side="left", fill="both", expand=True, padx=(12, 0))
    ttk.Label(
        package_panel,
        text="Organize a ordem e deixe selecionado so o que sera executado.",
        style="Muted.TLabel",
    ).pack(anchor="w", padx=10, pady=(4, 0))

    package_row = ttk.Frame(package_panel)
    package_row.pack(fill="x", padx=10, pady=(8, 10))

    package_listbox = tk.Listbox(
        package_row,
        selectmode="extended",
        exportselection=False,
        height=8,
        font=("Segoe UI", 10),
        bg="#ffffff",
        fg="#16202a",
        selectbackground="#1d6fa5",
        selectforeground="#ffffff",
        relief="flat",
        highlightthickness=1,
        highlightbackground="#d8dee6",
        activestyle="none",
    )
    package_listbox.pack(side="left", fill="x", expand=True)

    package_scrollbar = ttk.Scrollbar(package_row, orient="vertical", command=package_listbox.yview)
    package_scrollbar.pack(side="left", fill="y")
    package_listbox.configure(yscrollcommand=package_scrollbar.set)

    package_action_column = ttk.Frame(package_row)
    package_action_column.pack(side="left", padx=(10, 0))

    select_all_button = ttk.Button(package_action_column, text="Selecionar tudo")
    select_all_button.pack(fill="x")

    clear_selection_button = ttk.Button(package_action_column, text="Remover")
    clear_selection_button.pack(fill="x", pady=(8, 0))

    move_up_button = ttk.Button(package_action_column, text="Subir")
    move_up_button.pack(fill="x", pady=(8, 0))

    move_down_button = ttk.Button(package_action_column, text="Descer")
    move_down_button.pack(fill="x", pady=(8, 0))

    save_profile_button = ttk.Button(package_action_column, text="Salvar perfil")
    save_profile_button.pack(fill="x", pady=(8, 0))

    selected_details_var = tk.StringVar(value="Selecione um programa da lista para ver o ID e as notas da selecao.")
    ttk.Label(package_panel, textvariable=selected_details_var, style="Muted.TLabel").pack(anchor="w", padx=10, pady=(0, 8))

    package_status_frame = ttk.LabelFrame(execution_tab, text="Status dos pacotes", style="Section.TLabelframe")
    package_status_frame.pack(fill="x", pady=(0, 12))
    ttk.Label(
        package_status_frame,
        text="Acompanhamento visual por pacote durante a execucao.",
        style="Muted.TLabel",
    ).pack(anchor="w", padx=10, pady=(4, 0))

    package_status_board = tk.Frame(package_status_frame, bg="#eef2f5")
    package_status_board.pack(fill="x", padx=10, pady=(8, 10))
    package_status_widgets = {}

    execution_intro_frame = tk.Frame(
        execution_tab,
        bg="#ffffff",
        padx=18,
        pady=18,
        highlightthickness=1,
        highlightbackground="#d8dee6",
    )
    execution_intro_frame.pack(fill="x", pady=(0, 12))

    execution_intro_title_var = tk.StringVar(value="Pronto para executar")
    execution_intro_detail_var = tk.StringVar(
        value="Monte a fila na aba Selecionar. Quando estiver tudo certo, inicie a operacao aqui."
    )
    execution_intro_meta_var = tk.StringVar(value="Nenhum pacote marcado ainda.")

    execution_intro_text = tk.Frame(execution_intro_frame, bg="#ffffff")
    execution_intro_text.pack(side="left", fill="x", expand=True)

    tk.Label(
        execution_intro_text,
        textvariable=execution_intro_title_var,
        font=("Segoe UI", 16, "bold"),
        fg="#16202a",
        bg="#ffffff",
        anchor="w",
    ).pack(anchor="w")
    tk.Label(
        execution_intro_text,
        textvariable=execution_intro_detail_var,
        font=("Segoe UI", 10),
        fg="#4b5563",
        bg="#ffffff",
        justify="left",
        wraplength=620,
        anchor="w",
    ).pack(anchor="w", pady=(6, 4))
    tk.Label(
        execution_intro_text,
        textvariable=execution_intro_meta_var,
        font=("Segoe UI Semibold", 10),
        fg="#1849a9",
        bg="#ffffff",
        anchor="w",
    ).pack(anchor="w")

    execution_action_column = tk.Frame(execution_intro_frame, bg="#ffffff")
    execution_action_column.pack(side="right", padx=(16, 0))

    start_button = ttk.Button(execution_action_column, text=OPERATION_BUTTON_LABELS["install"], style="Primary.TButton")
    start_button.pack(fill="x")

    summary_frame = ttk.LabelFrame(execution_tab, text="Resumo", style="Section.TLabelframe")
    summary_frame.pack(fill="x", pady=(0, 0))

    summary_hint_var = tk.StringVar(value="Leitura amigavel para o operador")
    ttk.Label(summary_frame, textvariable=summary_hint_var, style="Muted.TLabel").pack(anchor="w", padx=10, pady=(4, 0))

    summary_box = tk.Text(
        summary_frame,
        wrap="word",
        height=7,
        width=100,
        font=("Consolas", 10),
        padx=10,
        pady=10,
        bg="#fbfcfd",
        fg="#16202a",
        relief="flat",
        highlightthickness=1,
        highlightbackground="#d8dee6",
    )
    summary_box.pack(fill="x", expand=False, padx=10, pady=(6, 10))
    summary_box.configure(state="disabled")

    log_frame = ttk.LabelFrame(execution_tab, text="Log ao vivo", style="Section.TLabelframe")
    log_frame.pack(fill="both", expand=True, pady=(12, 0))

    log_hint_var = tk.StringVar(value="INFO, WARN, ERROR e OK destacados por cor")
    ttk.Label(log_frame, textvariable=log_hint_var, style="Muted.TLabel").pack(anchor="w", padx=10, pady=(4, 0))

    log_box = scrolledtext.ScrolledText(
        log_frame,
        wrap="word",
        height=9,
        width=100,
        font=("Consolas", 10),
        padx=10,
        pady=10,
        bg="#f8fafc",
        fg="#16202a",
        relief="flat",
        highlightthickness=1,
        highlightbackground="#d8dee6",
        state="disabled",
    )
    log_box.pack(fill="both", expand=True, padx=10, pady=(6, 10))
    log_box.tag_configure("info", foreground="#1f2937")
    log_box.tag_configure("warn", foreground="#9a6700")
    log_box.tag_configure("error", foreground="#b42318")
    log_box.tag_configure("ok", foreground="#067647")
    log_box.tag_configure("boot", foreground="#175cd3")

    button_row = ttk.Frame(execution_tab, style="App.TFrame")
    button_row.pack(fill="x", pady=(12, 0))

    report_button = ttk.Button(button_row, text="Abrir relatorio", state="disabled")
    report_button.pack(side="left")

    log_button = ttk.Button(button_row, text="Abrir log", state="disabled")
    log_button.pack(side="left", padx=(8, 0))

    folder_button = ttk.Button(button_row, text="Abrir pasta", state="disabled")
    folder_button.pack(side="left", padx=(8, 0))

    reference_button = ttk.Button(button_row, text="Abrir referencia", state="disabled")
    reference_button.pack(side="left", padx=(8, 0))

    close_button = ttk.Button(button_row, text="Fechar", command=root.destroy)
    close_button.pack(side="right")

    tab_by_key = {
        "prepare": prepare_tab,
        "selection": selection_tab,
        "execution": execution_tab,
    }

    def focus_tab(key: str):
        tab = tab_by_key.get(key)
        if tab is not None:
            notebook.select(tab)

    def get_selected_operation() -> str:
        return operation_display_map[action_var.get()]

    def set_window_geometry(width: int | float, height: int | float):
        root.update_idletasks()

        class _Rect(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        work_area = _Rect()
        if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area), 0):
            available_width = max(work_area.right - work_area.left, 640)
            available_height = max(work_area.bottom - work_area.top, 480)
            target_width = int(available_width * width) if isinstance(width, float) else width
            target_height = int(available_height * height) if isinstance(height, float) else height
            required_width = max(target_width, min(root.winfo_reqwidth(), available_width - 24))
            required_height = max(target_height, min(root.winfo_reqheight(), available_height - 24))
            clamped_width = min(required_width, available_width - 12)
            clamped_height = min(required_height, available_height - 12)
            x = work_area.left + max((available_width - clamped_width) // 2, 0)
            y = work_area.top + max((available_height - clamped_height) // 5, 0)
            root.maxsize(available_width, available_height)
        else:
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()
            target_width = int(screen_width * width) if isinstance(width, float) else width
            target_height = int(screen_height * height) if isinstance(height, float) else height
            required_width = max(target_width, root.winfo_reqwidth())
            required_height = max(target_height, root.winfo_reqheight())
            clamped_width = min(required_width, screen_width - 12)
            clamped_height = min(required_height, screen_height - 12)
            x = max((screen_width - clamped_width) // 2, 0)
            y = max((screen_height - clamped_height) // 5, 0)
            root.maxsize(screen_width, screen_height)

        root.geometry(f"{clamped_width}x{clamped_height}+{x}+{y}")

    def set_summary(text: str):
        summary_box.configure(state="normal")
        summary_box.delete("1.0", "end")
        summary_box.insert("1.0", text)
        summary_box.configure(state="disabled")

    def set_status_banner(text: str, tone: str = "idle"):
        palette = {
            "idle": {"bg": "#d9f2e3", "fg": "#12344a"},
            "running": {"bg": "#dbeafe", "fg": "#12344a"},
            "success": {"bg": "#d9f2e3", "fg": "#0f5132"},
            "warning": {"bg": "#fff3cd", "fg": "#7a4f01"},
            "error": {"bg": "#fee4e2", "fg": "#912018"},
        }
        colors = palette.get(tone, palette["idle"])
        status_banner_var.set(text)
        status_banner.configure(bg=colors["bg"], fg=colors["fg"])

    def set_prepare_details_visible(visible: bool):
        state["prepare_details_visible"] = visible
        if visible:
            if not prepare_details_section.winfo_manager():
                prepare_details_section.pack(fill="x", pady=(0, 0))
            prepare_toggle_button.configure(text="Ocultar diagnostico tecnico")
        else:
            if prepare_details_section.winfo_manager():
                prepare_details_section.pack_forget()
            prepare_toggle_button.configure(text="Ver diagnostico tecnico")

    def toggle_prepare_details():
        set_prepare_details_visible(not state.get("prepare_details_visible", False))

    def refresh_prepare_summary():
        states = [indicator["state"].cget("text") for indicator in preflight_indicators.values()]
        errors = sum(1 for item in states if item in {"Erro", "Bloqueio", "Indisponivel"})
        warnings = sum(1 for item in states if item in {"Atencao", "Proxy", "Observacao", "Degradado"})
        successes = sum(1 for item in states if item in {"OK", "Saudavel"})

        if errors:
            prepare_summary_title_var.set("Bloqueios encontrados")
            prepare_summary_detail_var.set(
                f"{errors} sinal(is) critico(s) foram encontrados. Revise o diagnostico tecnico antes de continuar."
            )
        elif warnings:
            prepare_summary_title_var.set("Execucao com atencoes")
            prepare_summary_detail_var.set(
                f"{warnings} atencao(oes) foram encontradas. A maquina pode seguir, mas vale revisar os pontos destacados."
            )
        elif successes:
            prepare_summary_title_var.set("Maquina pronta para executar")
            prepare_summary_detail_var.set(
                "Nenhum bloqueio critico apareceu no preflight. Se quiser, siga para a selecao e execute a fila."
            )
        else:
            prepare_summary_title_var.set("Inspecao aguardando")
            prepare_summary_detail_var.set(
                "Quando a execucao comecar, esta aba vai resumir se a maquina esta pronta, com atencoes ou bloqueada."
            )

    def set_execution_intro(title: str, detail: str, meta: str):
        execution_intro_title_var.set(title)
        execution_intro_detail_var.set(detail)
        execution_intro_meta_var.set(meta)

    def set_execution_panels_visibility(show_summary: bool, show_log: bool):
        if show_summary:
            if not summary_frame.winfo_manager():
                summary_frame.pack(fill="x", pady=(0, 0), before=log_frame)
        else:
            if summary_frame.winfo_manager():
                summary_frame.pack_forget()

        if show_log:
            if not log_frame.winfo_manager():
                log_frame.pack(fill="both", expand=True, pady=(12, 0), before=button_row)
        else:
            if log_frame.winfo_manager():
                log_frame.pack_forget()

    def set_preflight_indicator(key: str, state_text: str, tone: str, detail_text: str):
        palette = {
            "idle": {"card": "#ffffff", "border": "#d8dee6", "state": "#475467", "detail": "#667085"},
            "running": {"card": "#eff8ff", "border": "#b2ddff", "state": "#175cd3", "detail": "#1849a9"},
            "success": {"card": "#ecfdf3", "border": "#abefc6", "state": "#067647", "detail": "#085d3a"},
            "warning": {"card": "#fffaeb", "border": "#fedf89", "state": "#b54708", "detail": "#93370d"},
            "error": {"card": "#fef3f2", "border": "#fecdca", "state": "#b42318", "detail": "#912018"},
        }
        colors = palette.get(tone, palette["idle"])
        indicator = preflight_indicators[key]
        indicator["frame"].configure(bg=colors["card"], highlightbackground=colors["border"])
        indicator["title"].configure(bg=colors["card"])
        indicator["state"].configure(text=state_text, bg=colors["card"], fg=colors["state"])
        indicator["detail"].configure(text=detail_text, bg=colors["card"], fg=colors["detail"])
        refresh_prepare_summary()

    def set_phase_indicator(key: str, state_text: str, tone: str):
        palette = {
            "idle": {"card": "#ffffff", "border": "#d8dee6", "state": "#475467"},
            "running": {"card": "#eff8ff", "border": "#b2ddff", "state": "#175cd3"},
            "success": {"card": "#ecfdf3", "border": "#abefc6", "state": "#067647"},
            "warning": {"card": "#fffaeb", "border": "#fedf89", "state": "#b54708"},
            "error": {"card": "#fef3f2", "border": "#fecdca", "state": "#b42318"},
        }
        colors = palette.get(tone, palette["idle"])
        indicator = phase_indicators[key]
        indicator["frame"].configure(bg=colors["card"], highlightbackground=colors["border"])
        indicator["title"].configure(bg=colors["card"])
        indicator["state"].configure(text=state_text, bg=colors["card"], fg=colors["state"])

    def create_package_status_row(parent, package_name: str):
        row = tk.Frame(parent, bg="#ffffff", padx=10, pady=8, highlightthickness=1, highlightbackground="#d8dee6")
        row.pack(fill="x", pady=3)
        top_row = tk.Frame(row, bg="#ffffff")
        top_row.pack(fill="x")
        name_label = tk.Label(
            top_row,
            text=package_name,
            font=("Segoe UI Semibold", 9),
            fg="#16202a",
            bg="#ffffff",
            anchor="w",
        )
        name_label.pack(side="left", fill="x", expand=True)
        state_label = tk.Label(
            top_row,
            text="Aguardando",
            font=("Segoe UI Semibold", 9),
            fg="#475467",
            bg="#ffffff",
            anchor="e",
        )
        state_label.pack(side="right")
        progress_var = tk.DoubleVar(value=0)
        progress_bar = ttk.Progressbar(
            row,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            variable=progress_var,
            style="Package.Horizontal.TProgressbar",
        )
        progress_bar.pack(fill="x", pady=(6, 0))
        package_status_widgets[package_name] = {
            "frame": row,
            "top_row": top_row,
            "name": name_label,
            "state": state_label,
            "progress": progress_bar,
            "progress_var": progress_var,
            "progress_mode": "determinate",
        }

    def set_package_status(
        package_name: str,
        state_text: str,
        tone: str = "idle",
        progress_value: float | None = None,
        animate: bool | None = None,
    ):
        if package_name not in package_status_widgets:
            return
        palette = {
            "idle": {"card": "#ffffff", "border": "#d8dee6", "name": "#16202a", "state": "#475467"},
            "running": {"card": "#eff8ff", "border": "#b2ddff", "name": "#1849a9", "state": "#175cd3"},
            "success": {"card": "#ecfdf3", "border": "#abefc6", "name": "#085d3a", "state": "#067647"},
            "warning": {"card": "#fffaeb", "border": "#fedf89", "name": "#93370d", "state": "#b54708"},
            "error": {"card": "#fef3f2", "border": "#fecdca", "name": "#912018", "state": "#b42318"},
        }
        colors = palette.get(tone, palette["idle"])
        row = package_status_widgets[package_name]
        row["frame"].configure(bg=colors["card"], highlightbackground=colors["border"])
        row["top_row"].configure(bg=colors["card"])
        row["name"].configure(bg=colors["card"], fg=colors["name"])
        row["state"].configure(text=state_text, bg=colors["card"], fg=colors["state"])
        progress_style = {
            "idle": "Package.Horizontal.TProgressbar",
            "running": "Package.Horizontal.TProgressbar",
            "success": "PackageSuccess.Horizontal.TProgressbar",
            "warning": "PackageWarning.Horizontal.TProgressbar",
            "error": "PackageError.Horizontal.TProgressbar",
        }.get(tone, "Package.Horizontal.TProgressbar")
        row["progress"].configure(style=progress_style)

        should_animate = bool(animate)
        if should_animate:
            if row["progress_mode"] != "indeterminate":
                row["progress"].stop()
                row["progress"].configure(mode="indeterminate")
                row["progress_mode"] = "indeterminate"
            row["progress"].start(12)
        else:
            if row["progress_mode"] != "determinate":
                row["progress"].stop()
                row["progress"].configure(mode="determinate")
                row["progress_mode"] = "determinate"
            if progress_value is not None:
                row["progress_var"].set(max(0, min(progress_value, 100)))

    def rebuild_package_status_board(package_names: list[str]):
        for child in package_status_board.winfo_children():
            child.destroy()
        package_status_widgets.clear()
        for package_name in package_names:
            create_package_status_row(package_status_board, package_name)

    def refresh_package_status_selection():
        selected = set(get_selected_package_names())
        for package_name in package_status_widgets:
            if state["running"]:
                continue
            if package_name in selected:
                set_package_status(package_name, "Selecionado", "running", progress_value=8)
            else:
                set_package_status(package_name, "Nao marcado", "idle", progress_value=0)

    def mark_selected_packages_queued():
        selected = set(get_selected_package_names())
        for package_name in package_status_widgets:
            if package_name in selected:
                set_package_status(package_name, "Na fila", "running", progress_value=15)
            else:
                set_package_status(package_name, "Nao marcado", "idle", progress_value=0)

    def infer_progress_from_log_line(raw_line: str) -> float | None:
        percent_match = re.search(r"(?<!\d)(100|[1-9]?\d)%", raw_line)
        if percent_match:
            return float(percent_match.group(1))

        fraction_match = re.search(
            r"(\d+(?:\.\d+)?)\s*(KB|MB|GB)\s*/\s*(\d+(?:\.\d+)?)\s*(KB|MB|GB)",
            raw_line,
            flags=re.IGNORECASE,
        )
        if not fraction_match:
            return None

        unit_scale = {"kb": 1, "mb": 1024, "gb": 1024 * 1024}
        current_value = float(fraction_match.group(1)) * unit_scale[fraction_match.group(2).lower()]
        total_value = float(fraction_match.group(3)) * unit_scale[fraction_match.group(4).lower()]
        if total_value <= 0:
            return None
        return round((current_value / total_value) * 100, 1)

    def reset_preflight_indicators():
        defaults = {
            "admin": "Privilegios ainda nao validados",
            "winget": "Cliente ainda nao inspecionado",
            "store": "Stack Store/App Installer ainda nao verificada",
            "network": "Sem leitura de rede/proxy",
            "capacity": "Sem leitura de espaco/arquitetura",
            "update": "Sem leitura de Windows Update",
            "security": "Sem leitura de seguranca do host",
            "reboot": "Sem leitura de reinicializacao pendente",
        }
        for key, detail in defaults.items():
            set_preflight_indicator(key, "Aguardando", "idle", detail)

    def reset_phase_indicators():
        for key in phase_indicators:
            set_phase_indicator(key, "Aguardando", "idle")

    def set_active_phase(active_key: str):
        ordered = ["preflight", "catalog", "execution", "report"]
        for key in ordered:
            if key == active_key:
                set_phase_indicator(key, "Em andamento", "running")
            elif ordered.index(key) < ordered.index(active_key):
                if phase_indicators[key]["state"].cget("text") == "Erro":
                    continue
                set_phase_indicator(key, "Concluida", "success")
            else:
                set_phase_indicator(key, "Aguardando", "idle")
        if active_key == "preflight":
            focus_tab("prepare")
        elif active_key == "catalog":
            focus_tab("selection")
        else:
            focus_tab("execution")

    def update_preflight_from_log(line: str):
        normalized = line.lower()

        if "iniciando gsd - instalador de laboratorios" in normalized:
            set_active_phase("preflight")
        elif "catalogo carregado:" in normalized:
            set_active_phase("catalog")
        elif "iniciando instalacao automatizada" in normalized or "iniciando atualizacao automatizada" in normalized or "iniciando desinstalacao automatizada" in normalized:
            set_active_phase("execution")
        elif "relatorio csv gerado" in normalized:
            set_active_phase("report")
            set_phase_indicator("report", "Concluida", "success")

        if "privilegios de administrador confirmados" in normalized:
            set_preflight_indicator("admin", "OK", "success", "Execucao elevada confirmada.")
        elif "erro de privilegio" in normalized or "deve ser executado como administrador" in normalized:
            set_preflight_indicator("admin", "Erro", "error", "Sem privilegios de administrador.")

        if "reinicializacao pendente detectada" in normalized:
            set_preflight_indicator("reboot", "Atencao", "warning", "Host com sinais de reboot pendente.")
        elif "ambiente validado com sucesso" in normalized and preflight_indicators["reboot"]["state"].cget("text") == "Aguardando":
            set_preflight_indicator("reboot", "OK", "success", "Sem sinal critico de reboot no bootstrap.")

        if "diagnostico de host:" in normalized:
            set_preflight_indicator("capacity", "OK", "success", "Arquitetura e espaco avaliados.")
        elif "capacidade/arquitetura" in normalized:
            set_preflight_indicator("capacity", "Atencao", "warning", "Host com sinal de espaco ou arquitetura critica.")

        if "stack store/app installer" in normalized and "indisponibilidade" not in normalized:
            set_preflight_indicator("store", "OK", "success", "Stack Store/App Installer encontrada.")
        elif "indisponibilidade na stack store/app installer" in normalized:
            set_preflight_indicator("store", "Atencao", "warning", "Stack Store/App Installer com sinais de indisponibilidade.")
        elif "politicas locais que podem bloquear store/app installer" in normalized:
            set_preflight_indicator("store", "Bloqueio", "error", "Politica local pode bloquear Store/App Installer.")

        if "diagnostico de alias/executavel do winget" in normalized or "winget detectado:" in normalized or "winget disponivel:" in normalized:
            set_preflight_indicator("winget", "OK", "success", "Cliente/alias do WinGet identificado.")
        elif "cliente do winget respondeu normalmente" in normalized:
            set_preflight_indicator("winget", "Saudavel", "success", "Sources consultadas com sucesso.")
        elif "problema no alias/executavel do winget" in normalized or "problema nas sources do winget" in normalized:
            set_preflight_indicator("winget", "Atencao", "warning", "Cliente do WinGet com sinais de instabilidade.")
        elif "modo degradado sem winget" in normalized or "sem winget acessivel" in normalized:
            set_preflight_indicator("winget", "Indisponivel", "error", "Fluxo sem WinGet funcional.")
        elif "falha sistemica anterior do winget" in normalized or "sessao marcada como fallback-first" in normalized:
            set_preflight_indicator("winget", "Degradado", "warning", "Sessao desviada para fallback-first.")

        if "diagnostico windows update" in normalized:
            set_preflight_indicator("update", "OK", "success", "Windows Update e servicos inspecionados.")
        elif "sinais de windows update pendente" in normalized:
            set_preflight_indicator("update", "Atencao", "warning", "Atualizacao pendente ou servico critico indisponivel.")

        if "diagnostico de seguranca do windows" in normalized:
            set_preflight_indicator("security", "OK", "success", "SmartScreen/Defender inspecionados.")
        elif "politicas/servicos de seguranca" in normalized:
            set_preflight_indicator("security", "Atencao", "warning", "Politicas de seguranca podem alterar downloads/binarios.")

        if "proxy detectado" in normalized:
            set_preflight_indicator("network", "Proxy", "warning", "Host com proxy ativo.")
        elif "diagnostico de conectividade dos endpoints" in normalized and "falhas=0" in normalized:
            set_preflight_indicator("network", "OK", "success", "Endpoints oficiais responderam ao teste.")
        elif "bloqueio/rede ao sondar os endpoints" in normalized or "falha no teste head" in normalized:
            set_preflight_indicator("network", "Falha", "error", "Sinais de bloqueio ou indisponibilidade de rede.")
        elif ("firewall" in normalized or "sem indicio local de proxy" in normalized) and preflight_indicators["network"]["state"].cget("text") == "Aguardando":
            set_preflight_indicator("network", "Observacao", "running", "Sem proxy local; validar firewall/politica externa se falhar.")

        for package_name in package_status_widgets:
            package_lower = package_name.lower()
            if package_lower not in normalized:
                continue
            progress_hint = infer_progress_from_log_line(line)
            if "validando pacote" in normalized:
                set_package_status(package_name, "Validando", "running", progress_value=30)
            elif "iniciando instalacao automatizada" in normalized:
                set_package_status(package_name, "Instalando", "running", progress_value=45, animate=progress_hint is None)
            elif "iniciando atualizacao automatizada" in normalized:
                set_package_status(package_name, "Atualizando", "running", progress_value=45, animate=progress_hint is None)
            elif "iniciando desinstalacao automatizada" in normalized:
                set_package_status(package_name, "Removendo", "running", progress_value=45, animate=progress_hint is None)
            elif "requer instalacao manual" in normalized or "requer atualizacao manual" in normalized or "requer desinstalacao manual" in normalized:
                set_package_status(package_name, "Manual", "warning", progress_value=100)
            elif "nao esta presente para" in normalized:
                set_package_status(package_name, "Nao presente", "idle", progress_value=0)
            elif "nao pode ser automatizado" in normalized:
                set_package_status(package_name, "Bloqueado", "error", progress_value=100)
            elif "falha " in normalized:
                set_package_status(package_name, "Falhou", "error", progress_value=100)
            elif "sucesso:" in normalized:
                if "desinstal" in normalized:
                    set_package_status(package_name, "Concluido", "success", progress_value=100)
                else:
                    set_package_status(package_name, "Concluido", "success", progress_value=100)
            elif progress_hint is not None:
                set_package_status(package_name, f"Em andamento ({int(progress_hint)}%)", "running", progress_value=progress_hint)

    def refresh_overview_cards():
        selected_operation = get_selected_operation()
        selected_count = len(get_selected_package_names())
        total_packages = package_listbox.size()
        profile_card_var.set(f"Modo ativo\n{state['selection_label']}")
        action_card_var.set(f"Acao\n{OPERATION_TITLES[selected_operation]}")
        packages_card_var.set(f"Pacotes marcados\n{selected_count}/{total_packages}")

    def set_selection_controls_enabled(enabled: bool):
        combo_state = "readonly" if enabled else "disabled"
        action_state = "normal" if enabled else "disabled"
        action_combo.configure(state=combo_state)
        search_entry.configure(state="normal" if enabled else "disabled")
        search_button.configure(state=action_state)
        show_generic_check.configure(state=action_state)
        search_results_listbox.configure(state=action_state)
        add_result_button.configure(state=action_state)
        package_listbox.configure(state=action_state)
        select_all_button.configure(state=action_state)
        clear_selection_button.configure(state=action_state)
        move_up_button.configure(state=action_state)
        move_down_button.configure(state=action_state)
        open_profile_button.configure(state=action_state)
        save_profile_button.configure(state=action_state)

    def get_selected_package_names() -> list[str]:
        return [package_listbox.get(index) for index in package_listbox.curselection()]

    def get_selected_search_results() -> list[dict]:
        return [state["visible_search_results"][index] for index in search_results_listbox.curselection()]

    def get_selected_dynamic_package_details() -> dict | None:
        selected_names = get_selected_package_names()
        if not selected_names:
            return None
        package_name = selected_names[0]
        for package in state["selected_dynamic_packages"]:
            if package["software"] == package_name:
                return package
        return None

    def format_search_result(item: dict) -> str:
        version = item.get("version") or "?"
        confidence = item.get("confidence", "baixa").upper()
        automation_label = item.get("automation_label", "Resultado generico")
        return f"{item.get('name', 'Sem nome')} [{item.get('id', 'sem.id')}] - {version} | {confidence} | {automation_label}"

    def get_filtered_search_results() -> list[dict]:
        if show_generic_results_var.get():
            return list(state["search_results"])
        return [
            item for item in state["search_results"]
            if item.get("automation_hint") in {"trusted", "likely_official"}
        ]

    def render_search_results():
        state["visible_search_results"] = get_filtered_search_results()
        search_results_listbox.delete(0, "end")
        for item in state["visible_search_results"]:
            search_results_listbox.insert("end", format_search_result(item))
        result_details_var.set("Selecione um resultado para ver detalhes de ID, versao e origem.")

    def update_selected_package_details():
        package = get_selected_dynamic_package_details()
        if not package:
            selected_details_var.set("Selecione um programa da lista para ver o ID e as notas da selecao.")
            return
        selected_details_var.set(
            f"Selecionado: {package['software']} | ID: {package['winget_id']} | "
            f"Notas: {package.get('notes', 'Sem notas adicionais.')}"
        )

    def update_search_result_details():
        selected_indices = search_results_listbox.curselection()
        if not selected_indices:
            result_details_var.set("Selecione um resultado para ver detalhes de ID, versao e origem.")
            return
        item = state["visible_search_results"][selected_indices[0]]
        result_details_var.set(
            f"Nome: {item.get('name', 'Sem nome')} | "
            f"ID: {item.get('id', 'sem.id')} | "
            f"Versao: {item.get('version') or 'desconhecida'} | "
            f"Origem: {item.get('source') or 'winget'} | "
            f"Confianca: {item.get('confidence', 'baixa')} | "
            f"Score: {item.get('score', 0)} | "
            f"Heuristica: {item.get('automation_label', 'Resultado generico')}"
        )

    def run_winget_search():
        if state["running"]:
            return

        query = search_query_var.get().strip()
        if not query:
            messagebox.showwarning(
                "Instalador Labs",
                "Digite o nome de um programa para pesquisar no WinGet.",
            )
            search_status_var.set("Informe um termo para pesquisar.")
            return

        search_status_var.set("Pesquisando no WinGet...")
        focus_tab("selection")
        search_manager = WinGetManager()
        result = search_manager.search_packages(query)
        state["search_results"] = result.get("results", [])
        render_search_results()
        visible_results = state["visible_search_results"]
        if visible_results:
            search_results_listbox.selection_set(0, "end")
            update_search_result_details()
            hidden_count = max(len(result.get("results", [])) - len(visible_results), 0)
            if hidden_count:
                search_status_var.set(
                    f"{len(visible_results)} resultado(s) exibido(s); {hidden_count} generico(s) ocultado(s)."
                )
            else:
                search_status_var.set(f"{len(visible_results)} resultado(s) encontrado(s).")
        else:
            if result.get("results"):
                search_status_var.set("So foram encontrados resultados genericos. Marque 'Mostrar genericos' para exibir.")
            else:
                search_status_var.set("Nenhum resultado encontrado ou WinGet indisponivel para pesquisa.")

    def add_selected_search_results():
        selected_results = get_selected_search_results()
        if not selected_results:
            return

        existing_ids = {item["winget_id"].lower() for item in state["selected_dynamic_packages"]}
        existing_names = {item["software"].lower() for item in state["selected_dynamic_packages"]}
        for item in selected_results:
            if item["id"].lower() in existing_ids:
                continue
            software_name = item["name"]
            if software_name.lower() in existing_names:
                software_name = f"{item['name']} ({item['id']})"
            state["selected_dynamic_packages"].append(
                {
                    "software": software_name,
                    "winget_id": item["id"],
                    "notes": (
                        f"Adicionado dinamicamente pela busca: {item['name']}. "
                        f"Heuristica: {item.get('automation_label', 'Resultado generico')}."
                    ),
                }
            )
            existing_ids.add(item["id"].lower())
            existing_names.add(software_name.lower())

        state["selection_label"] = "Busca dinamica WinGet"
        rebuild_selected_packages_listbox()
        search_status_var.set(f"{len(selected_results)} item(ns) enviado(s) para a selecao.")

    def save_current_selection_profile():
        if not state["selected_dynamic_packages"]:
            messagebox.showwarning(
                "Instalador Labs",
                "Adicione ao menos um programa antes de salvar um perfil.",
            )
            return

        profile = build_dynamic_package_profile(state["selected_dynamic_packages"])
        suggested_name = f"{profile['profile']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        target_path = filedialog.asksaveasfilename(
            title="Salvar perfil dinamico",
            defaultextension=".json",
            initialfile=suggested_name,
            filetypes=[("JSON", "*.json")],
        )
        if not target_path:
            return

        saved_path = save_package_profile(profile, target_path)
        search_status_var.set(f"Perfil salvo em {saved_path}.")

    def move_selected_package(direction: int):
        selected_indices = list(package_listbox.curselection())
        if not selected_indices:
            return

        if direction < 0:
            for index in selected_indices:
                if index == 0:
                    continue
                state["selected_dynamic_packages"][index - 1], state["selected_dynamic_packages"][index] = (
                    state["selected_dynamic_packages"][index],
                    state["selected_dynamic_packages"][index - 1],
                )
        else:
            for index in reversed(selected_indices):
                if index >= len(state["selected_dynamic_packages"]) - 1:
                    continue
                state["selected_dynamic_packages"][index + 1], state["selected_dynamic_packages"][index] = (
                    state["selected_dynamic_packages"][index],
                    state["selected_dynamic_packages"][index + 1],
                )

        rebuild_selected_packages_listbox()
        updated_indices = [max(0, min(index + direction, package_listbox.size() - 1)) for index in selected_indices]
        package_listbox.selection_clear(0, "end")
        for index in updated_indices:
            package_listbox.selection_set(index)
        update_selection_status()
        update_selected_package_details()

    def open_saved_profile():
        if state["running"]:
            return

        target_path = filedialog.askopenfilename(
            title="Abrir perfil salvo",
            filetypes=[("JSON", "*.json")],
        )
        if not target_path:
            return

        profile = validate_package_profile(load_package_profile(target_path))
        state["selected_dynamic_packages"] = [
            {
                "software": package["software"],
                "winget_id": package["winget_id"],
                "notes": package.get("notes", "Carregado de perfil salvo."),
            }
            for package in profile.get("packages", [])
            if package.get("install_type") == "winget" and package.get("winget_id")
        ]
        state["selection_label"] = f"Perfil salvo: {Path(target_path).stem}"
        rebuild_selected_packages_listbox()
        search_status_var.set(f"Perfil carregado com {len(state['selected_dynamic_packages'])} programa(s).")
        focus_tab("selection")

    def update_selection_status():
        total_packages = package_listbox.size()
        selected_count = len(get_selected_package_names())
        selection_status_var.set(f"Pacotes marcados: {selected_count}/{total_packages}")
        refresh_overview_cards()
        refresh_package_status_selection()

    def update_idle_summary():
        if state["running"] or state["has_completed"]:
            return

        selected_packages = get_selected_package_names()
        package_total = package_listbox.size()
        selected_operation = get_selected_operation()
        operation_title = OPERATION_TITLES[selected_operation].lower()
        start_label = OPERATION_BUTTON_LABELS[selected_operation]
        set_summary(
            "Modo: Busca dinamica WinGet\n"
            f"Operacao: {OPERATION_TITLES[selected_operation]}\n"
            f"Pacotes marcados: {len(selected_packages)} de {package_total}.\n\n"
            f"Clique em '{start_label}' para executar a {operation_title.lower()} apenas nos softwares marcados.\n"
            "Pesquise programas, adicione a selecao e acompanhe o status por pacote durante a execucao."
        )
        if selected_packages:
            package_preview = ", ".join(selected_packages[:3])
            if len(selected_packages) > 3:
                package_preview += ", ..."
            set_execution_intro(
                f"Pronto para {operation_title}",
                "Revise a fila e inicie quando quiser. O acompanhamento detalhado aparece aqui durante a execucao.",
                f"{len(selected_packages)} pacote(s) marcado(s): {package_preview}",
            )
        else:
            set_execution_intro(
                "Nada para executar ainda",
                "Monte sua fila na aba Selecionar. Esta aba so ganha detalhes tecnicos quando houver uma execucao em andamento.",
                "Nenhum pacote marcado ainda.",
            )
        summary_hint_var.set("Leitura amigavel para o operador")

    def update_idle_presentation():
        if state["running"] or state["has_completed"]:
            return

        selected_operation = get_selected_operation()
        start_button.configure(text=OPERATION_BUTTON_LABELS[selected_operation])
        status_var.set(f"Pronto para iniciar a {OPERATION_TITLES[selected_operation].lower()} automatizada.")
        set_status_banner("Ambiente pronto para iniciar", tone="idle")
        state["manual_reference_url"] = None
        update_reference_button()
        update_idle_summary()
        focus_tab("selection")

    def rebuild_selected_packages_listbox():
        package_listbox.delete(0, "end")
        package_names = [package["software"] for package in state["selected_dynamic_packages"]]
        for package_name in package_names:
            package_listbox.insert("end", package_name)
        rebuild_package_status_board(package_names)
        if package_names:
            package_listbox.selection_set(0, "end")
        update_selection_status()
        update_idle_presentation()

    def select_all_packages():
        if package_listbox.size():
            package_listbox.selection_set(0, "end")
        update_selection_status()
        update_idle_presentation()

    def clear_selected_packages():
        selected_names = set(get_selected_package_names())
        if not selected_names:
            return
        state["selected_dynamic_packages"] = [
            package for package in state["selected_dynamic_packages"] if package["software"] not in selected_names
        ]
        rebuild_selected_packages_listbox()

    def apply_window_mode(mode: str):
        if mode == "idle":
            set_window_geometry(0.94, 0.86)
            summary_box.configure(height=5)
            log_box.configure(height=5)
            package_listbox.configure(height=4)
            search_results_listbox.configure(height=5)
            log_hint_var.set("INFO, WARN, ERROR e OK destacados por cor")
            set_execution_panels_visibility(False, False)
        elif mode == "running":
            set_window_geometry(0.96, 0.9)
            summary_box.configure(height=7)
            log_box.configure(height=10)
            package_listbox.configure(height=4)
            search_results_listbox.configure(height=5)
            summary_hint_var.set("Resumo operacional em construcao")
            log_hint_var.set("Diagnostico tecnico em tempo real")
            set_execution_panels_visibility(True, True)
        elif mode == "completed":
            set_window_geometry(0.96, 0.9)
            summary_box.configure(height=7)
            log_box.configure(height=8)
            package_listbox.configure(height=4)
            search_results_listbox.configure(height=5)
            summary_hint_var.set("Resumo final pronto para revisao")
            log_hint_var.set("Use o log para comparar comportamento entre maquinas")
            set_execution_panels_visibility(True, True)

    def clear_log():
        log_box.configure(state="normal")
        log_box.delete("1.0", "end")
        log_box.configure(state="disabled")

    def append_log_line(line: str):
        log_box.configure(state="normal")
        upper_line = line.upper()
        tag = "info"
        if "[ERROR]" in upper_line:
            tag = "error"
        elif "[WARN]" in upper_line:
            tag = "warn"
        elif "[OK]" in upper_line or "[SUCCESS]" in upper_line:
            tag = "ok"
        elif "[INFO]" in upper_line and "BOOTSTRAP" in upper_line:
            tag = "boot"
        elif "[INFO]" in upper_line:
            tag = "info"
        log_box.insert("end", f"{line}\n", tag)
        log_box.see("end")
        log_box.configure(state="disabled")
        update_preflight_from_log(line)

    def resolve_manual_reference_url(_selected_package_names: list[str]) -> str | None:
        return None

    def disable_artifact_buttons():
        report_button.configure(state="disabled")
        log_button.configure(state="disabled")
        folder_button.configure(state="disabled")
        reference_button.configure(state="disabled")

    def update_reference_button():
        if state["manual_reference_url"]:
            reference_button.configure(state="normal")
        else:
            reference_button.configure(state="disabled")

    def enable_artifact_buttons():
        if state["report_path"]:
            report_button.configure(state="normal")
        if state["log_path"]:
            log_button.configure(state="normal")
        if state["folder_path"]:
            folder_button.configure(state="normal")
        update_reference_button()

    def reset_execution_state():
        state["report_path"] = None
        state["log_path"] = None
        state["folder_path"] = None
        state["manual_reference_url"] = None
        disable_artifact_buttons()
        clear_log()
        reset_preflight_indicators()
        reset_phase_indicators()

    def worker(selected_dynamic_packages: list[dict], selected_operation: str):
        try:
            package_profile, execution_results, report_path, log_path = run_application(
                logger_observer=lambda line: event_queue.put(("log", line)),
                custom_packages=selected_dynamic_packages,
                operation=selected_operation,
            )
            event_queue.put(("completed", (package_profile, execution_results, report_path, log_path)))
        except OperatorVisibleError as error:
            event_queue.put(("operator_error", (str(error), None)))
        except SystemExit:
            event_queue.put(("operator_error", ("Execucao encerrada prematuramente.", None)))
        except Exception as error:
            event_queue.put(("unexpected_error", (str(error), None)))

    def start_execution():
        if state["running"]:
            return

        selected_package_names = get_selected_package_names()
        selected_operation = get_selected_operation()
        if not selected_package_names:
            messagebox.showwarning(
                "Instalador Labs",
                "Selecione ao menos um pacote antes de iniciar a execucao.",
            )
            status_var.set("Selecione ao menos um pacote para continuar.")
            update_idle_presentation()
            return

        state["running"] = True
        state["has_completed"] = False
        reset_execution_state()
        start_button.configure(state="disabled")
        set_selection_controls_enabled(False)
        apply_window_mode("running")
        status_var.set(f"Executando {OPERATION_TITLES[selected_operation].lower()} automatizada...")
        set_status_banner("Execucao em andamento", tone="running")
        set_execution_intro(
            f"{OPERATION_TITLES[selected_operation]} em andamento",
            "Acompanhe abaixo o progresso por pacote. O log so aparece porque agora ele faz parte da execucao.",
            f"{len(selected_package_names)} pacote(s) na fila desta execucao.",
        )
        set_active_phase("preflight")
        focus_tab("execution")
        mark_selected_packages_queued()
        set_summary(
            f"Preparando a {OPERATION_TITLES[selected_operation].lower()} de {len(selected_package_names)} programa(s) selecionado(s).\n"
            "O resumo final sera exibido aqui ao termino."
        )
        selected_dynamic_packages = [
            package for package in state["selected_dynamic_packages"] if package["software"] in selected_package_names
        ]
        Thread(target=worker, args=(selected_dynamic_packages, selected_operation), daemon=True).start()

    def mark_execution_finished():
        state["running"] = False
        state["has_completed"] = True
        start_button.configure(state="normal", text="Executar novamente")
        set_selection_controls_enabled(True)

    def poll_events():
        try:
            while True:
                event_type, payload = event_queue.get_nowait()
                if event_type == "log":
                    append_log_line(payload)
                    continue

                mark_execution_finished()

                if event_type == "completed":
                    package_profile, execution_results, report_path, log_path = payload
                    operation = normalize_operation(execution_results.get("operation", "install"))
                    state["report_path"] = report_path
                    state["log_path"] = log_path
                    state["folder_path"] = report_path.parent
                    manual_urls = []
                    for package_result in execution_results.get("packages", []):
                        reference_url = package_result.get("manual_reference_url")
                        if reference_url and reference_url not in manual_urls:
                            manual_urls.append(reference_url)
                    state["manual_reference_url"] = manual_urls[0] if len(manual_urls) == 1 else None
                    set_summary(build_execution_summary_text(package_profile, execution_results, report_path, log_path))
                    status_var.set(f"{OPERATION_TITLES[operation]} concluida. Revise o resumo e abra os artefatos se necessario.")
                    if execution_results.get("summary", {}).get("failed") or execution_results.get("summary", {}).get("blocked"):
                        set_status_banner("Execucao concluida com atencoes", tone="warning")
                        set_execution_intro(
                            "Execucao concluida com atencoes",
                            "Revise os pacotes com falha ou bloqueio e use os artefatos abaixo para investigar se precisar.",
                            "Consulte o resumo final e, se necessario, abra o log ou o relatorio.",
                        )
                    else:
                        set_status_banner("Execucao concluida com sucesso", tone="success")
                        set_execution_intro(
                            "Execucao concluida com sucesso",
                            "Tudo o que estava marcado foi resolvido sem falhas. Os artefatos ficam disponiveis abaixo para conferencia.",
                            "Use 'Executar novamente' se quiser processar outra fila.",
                        )
                    set_phase_indicator("report", "Concluida", "success")
                    for package_result in execution_results.get("packages", []):
                        package_name = package_result.get("package")
                        if package_result.get("status") in ("installed", "updated", "removed", "already_installed", "not_installed"):
                            set_package_status(package_name, "Concluido", "success", progress_value=100)
                        elif package_result.get("status") == "manual":
                            set_package_status(package_name, "Manual", "warning", progress_value=100)
                        elif package_result.get("status") in ("failed", "blocked"):
                            set_package_status(package_name, "Falhou", "error", progress_value=100)
                    apply_window_mode("completed")
                    focus_tab("execution")
                    enable_artifact_buttons()
                elif event_type == "operator_error":
                    message, log_path = payload
                    state["log_path"] = log_path
                    state["folder_path"] = log_path.parent if log_path else None
                    set_summary(f"A execucao foi interrompida.\n\n{message}" + (f"\n\nLog: {log_path}" if log_path else ""))
                    status_var.set("Execucao interrompida. Consulte o log para detalhes.")
                    set_status_banner("Execucao interrompida", tone="error")
                    set_execution_intro(
                        "Execucao interrompida",
                        "O fluxo nao chegou ao fim. O resumo e o log abaixo mostram o ponto da interrupcao.",
                        "Revise o motivo antes de tentar novamente.",
                    )
                    for phase_key in phase_indicators:
                        if phase_indicators[phase_key]["state"].cget("text") == "Em andamento":
                            set_phase_indicator(phase_key, "Erro", "error")
                            break
                    apply_window_mode("completed")
                    focus_tab("execution")
                    enable_artifact_buttons()
                elif event_type == "unexpected_error":
                    message, log_path = payload
                    state["log_path"] = log_path
                    state["folder_path"] = log_path.parent if log_path else None
                    set_summary(f"O instalador encontrou um erro inesperado.\n\n{message}" + (f"\n\nLog: {log_path}" if log_path else ""))
                    status_var.set("Erro inesperado durante a execucao. Consulte o log.")
                    set_status_banner("Erro inesperado", tone="error")
                    set_execution_intro(
                        "Erro inesperado",
                        "A execucao encontrou uma condicao nao prevista. O log abaixo agora e a principal fonte para diagnostico.",
                        "Revise o erro e tente novamente depois do ajuste.",
                    )
                    for phase_key in phase_indicators:
                        if phase_indicators[phase_key]["state"].cget("text") == "Em andamento":
                            set_phase_indicator(phase_key, "Erro", "error")
                            break
                    apply_window_mode("completed")
                    focus_tab("execution")
                    enable_artifact_buttons()
        except Empty:
            pass

        root.after(120, poll_events)

    action_combo.bind("<<ComboboxSelected>>", lambda _event: update_idle_presentation())
    package_listbox.bind("<<ListboxSelect>>", lambda _event: (update_selection_status(), update_idle_presentation()))
    package_listbox.bind("<<ListboxSelect>>", lambda _event: update_selected_package_details(), add="+")
    search_results_listbox.bind("<<ListboxSelect>>", lambda _event: update_search_result_details())
    search_button.configure(command=run_winget_search)
    open_profile_button.configure(command=open_saved_profile)
    prepare_toggle_button.configure(command=toggle_prepare_details)
    add_result_button.configure(command=add_selected_search_results)
    move_up_button.configure(command=lambda: move_selected_package(-1))
    move_down_button.configure(command=lambda: move_selected_package(1))
    save_profile_button.configure(command=save_current_selection_profile)
    search_entry.bind("<Return>", lambda _event: run_winget_search())
    show_generic_results_var.trace_add("write", lambda *_args: (render_search_results(), update_search_result_details()))

    select_all_button.configure(command=select_all_packages)
    clear_selection_button.configure(command=clear_selected_packages)
    report_button.configure(command=lambda: _open_target_for_operator(state["report_path"]))
    log_button.configure(command=lambda: _open_target_for_operator(state["log_path"]))
    folder_button.configure(command=lambda: _open_target_for_operator(state["folder_path"]))
    reference_button.configure(command=lambda: _open_target_for_operator(state["manual_reference_url"]))
    start_button.configure(command=start_execution)

    rebuild_selected_packages_listbox()
    render_search_results()
    reset_preflight_indicators()
    reset_phase_indicators()
    set_prepare_details_visible(False)
    apply_window_mode("idle")
    focus_tab("selection")

    root.after(120, poll_events)
    root.mainloop()
    _OPERATOR_WINDOW_ACTIVE = False

def bootstrap(logger):
    """Inicializa o sistema e valida requisitos basicos do ambiente."""
    winget = WinGetManager()
    direct_installer = DirectInstallerManager()
    return bootstrap_environment(
        logger,
        winget,
        direct_installer,
        is_admin=is_admin,
        fail_with_operator_message=fail_with_operator_message,
        get_pending_reboot_diagnostics=get_pending_reboot_diagnostics,
        get_host_capacity_diagnostics=get_host_capacity_diagnostics,
        get_runtime_directory_diagnostics=get_runtime_directory_diagnostics,
    )


def load_package_catalog(
    logger,
    profile_name: str | None = None,
    selected_packages: list[str] | None = None,
    custom_packages: list[dict] | None = None,
):
    """Carrega um catalogo JSON e opcionalmente filtra os pacotes selecionados."""
    return load_catalog_profile(
        logger,
        fail_with_operator_message=fail_with_operator_message,
        probe_catalog_endpoint_connectivity=probe_catalog_endpoint_connectivity,
        build_dynamic_package_profile=build_dynamic_package_profile,
        load_profile_by_name=load_profile_by_name,
        load_default_package_profile=load_default_package_profile,
        select_profile_packages=select_profile_packages,
        profile_name=profile_name,
        selected_packages=selected_packages,
        custom_packages=custom_packages,
    )

def _check_winget_package_status(winget, package_id: str) -> dict:
    """Consulta o status de um pacote via WinGet com diagnostico detalhado quando disponivel."""
    if hasattr(winget, "check_package_status_details"):
        return winget.check_package_status_details(package_id)

    found = winget.check_package_status(package_id)
    return {
        "found": found,
        "detail": "Pacote localizado pelo WinGet antes da operacao." if found else "Pacote nao localizado pelo WinGet antes da operacao.",
    }


def _install_winget_package(winget, package_id: str) -> dict:
    """Executa a instalacao via WinGet com diagnostico detalhado quando disponivel."""
    if hasattr(winget, "install_package_details"):
        return winget.install_package_details(package_id)

    success = winget.install_package(package_id)
    return {
        "success": success,
        "detail": "Instalado com sucesso pelo WinGet." if success else "Falha na instalacao automatizada pelo WinGet.",
    }


def _is_retryable_winget_install_failure(install_result: dict) -> bool:
    """Indica se a falha do WinGet sugere tentar um fallback direto oficial."""
    detail = (install_result.get("detail") or "").lower()
    return any(
        marker in detail
        for marker in (
            "failed when opening source",
            "source reset",
            "fontes do winget",
            "2316632079",
            "0x8a15000f",
        )
    )


def _build_winget_failure_diagnostics(install_result: dict) -> str:
    """Extrai uma trilha diagnostica objetiva do WinGet para comparar hosts."""
    diagnostics = (install_result.get("diagnostics") or "").strip()
    if diagnostics:
        return diagnostics
    return install_result.get("detail", "Sem diagnostico adicional do WinGet.")


def _can_bypass_winget_install(winget) -> bool:
    return hasattr(winget, "has_systemic_install_failure") and winget.has_systemic_install_failure()


def _get_systemic_winget_failure_diagnostics(winget) -> str:
    if hasattr(winget, "get_systemic_install_failure_diagnostics"):
        return winget.get_systemic_install_failure_diagnostics() or "Sem diagnostico adicional do WinGet."
    return "Sem diagnostico adicional do WinGet."


def classify_package_result(package_result: dict) -> str:
    """Classifica a causa/rota principal de cada pacote para facilitar analise em campo."""
    return reporting_classify_package_result(package_result)


def summarize_execution_diagnostics(results: dict) -> dict:
    """Resume os sinais dominantes da execucao para exibicao ao operador."""
    return reporting_summarize_execution_diagnostics(results)


def _upgrade_winget_package(winget, package_id: str) -> dict:
    """Executa a atualizacao via WinGet com diagnostico detalhado quando disponivel."""
    if hasattr(winget, "upgrade_package_details"):
        return winget.upgrade_package_details(package_id)

    success = winget.upgrade_package(package_id)
    return {
        "success": success,
        "detail": "Atualizado com sucesso pelo WinGet." if success else "Falha na atualizacao automatizada pelo WinGet.",
    }


def _uninstall_winget_package(winget, package_id: str) -> dict:
    """Executa a desinstalacao via WinGet com diagnostico detalhado quando disponivel."""
    if hasattr(winget, "uninstall_package_details"):
        return winget.uninstall_package_details(package_id)

    success = winget.uninstall_package(package_id)
    return {
        "success": success,
        "detail": "Desinstalado com sucesso pelo WinGet." if success else "Falha na desinstalacao automatizada pelo WinGet.",
    }


def process_package(package, logger, winget, direct_installer, operation: str = "install"):
    """Processa um pacote do catalogo de acordo com seu tipo de instalacao e operacao."""
    operation = normalize_operation(operation)
    package_name = package["software"]
    install_type = package["install_type"]
    winget_id = package.get("winget_id", "")
    result = {
        "package": package_name,
        "operation": operation,
        "install_type": install_type,
        "winget_id": winget_id,
        "catalog_notes": package.get("notes", ""),
        "manual_reference_url": package.get("manual_reference_url", ""),
        "status": "",
        "install_method": "",
        "detail": "",
    }

    if install_type == "manual":
        manual_action = {
            "install": "instalacao manual",
            "update": "atualizacao manual",
            "uninstall": "desinstalacao manual",
        }[operation]

        if operation == "install" and package.get("official_download"):
            try:
                installer_path = direct_installer.download_manual_installer(package, logger)
                logger.warning(
                    f"Pacote '{package_name}' requer instalacao manual. Instalador oficial baixado em '{installer_path}'.",
                    status="manual_downloaded",
                    package_name=package_name,
                )
                result["status"] = "manual"
                result["install_method"] = "manual_download"
                result["detail"] = f"Instalador oficial baixado em '{installer_path}' para execucao manual."
                return result
            except Exception as error:
                logger.error(
                    f"Falha ao baixar instalador oficial de '{package_name}': {error}",
                    status="manual_download_error",
                    package_name=package_name,
                )
                result["status"] = "failed"
                result["install_method"] = "manual_download"
                result["detail"] = f"Falha ao baixar instalador oficial para execucao manual: {error}"
                return result

        logger.warning(
            f"Pacote '{package_name}' requer {manual_action}. Nenhuma acao automatica executada.",
            status="manual",
            package_name=package_name,
        )
        result["status"] = "manual"
        result["install_method"] = "manual"
        if result["manual_reference_url"]:
            result["detail"] = (
                f"Requer {manual_action}. Consulte a referencia oficial em {result['manual_reference_url']}."
            )
        else:
            result["detail"] = f"Requer {manual_action}."
        return result

    if install_type == "winget_pending":
        logger.warning(
            f"Pacote '{package_name}' esta marcado como winget_pending e sera apenas sinalizado para teste manual.",
            status="winget_pending",
            package_name=package_name,
        )
        result["status"] = "pending"
        result["install_method"] = "winget_pending"
        result["detail"] = f"Aguardando validacao manual do fluxo WinGet para {operation}."
        return result

    if operation == "install":
        if direct_installer.is_package_present(package):
            logger.success(package_name, status="already_installed")
            result["status"] = "already_installed"
            result["install_method"] = "registry_detect"
            result["detail"] = "Pacote detectado no host sem necessidade de instalacao."
            return result

        if not winget.is_installed():
            if package.get("fallback_installer"):
                if direct_installer.install_package(package, logger):
                    logger.success(package_name, status="installed")
                    result["status"] = "installed"
                    result["install_method"] = "fallback_direct"
                    result["detail"] = "Instalado via instalador direto oficial."
                    return result

                logger.error(
                    f"Falha no fallback de instalacao de '{package_name}'.",
                    status="fallback_failed",
                    package_name=package_name,
                )
                result["status"] = "failed"
                result["install_method"] = "fallback_direct"
                result["detail"] = "Falha na execucao do instalador direto oficial."
                return result

            logger.warning(
                f"Pacote '{package_name}' nao pode ser automatizado nesta maquina porque o WinGet nao esta disponivel.",
                status="winget_unavailable",
                package_name=package_name,
            )
            result["status"] = "blocked"
            result["install_method"] = "blocked_no_winget"
            result["detail"] = "Sem WinGet acessivel e sem fallback direto configurado."
            return result

        if package.get("fallback_installer") and _can_bypass_winget_install(winget):
            winget_failure_diagnostics = _get_systemic_winget_failure_diagnostics(winget)
            logger.warning(
                f"Falha sistemica anterior do WinGet detectada nesta execucao. Pulando WinGet para '{package_name}'. "
                f"Diagnostico: {winget_failure_diagnostics}",
                status="winget_bypassed",
                package_name=package_name,
            )
            if direct_installer.is_package_present(package):
                logger.success(package_name, status="already_installed")
                result["status"] = "already_installed"
                result["install_method"] = "registry_detect"
                result["detail"] = (
                    "Pacote detectado no host apos falha sistemica anterior do WinGet. "
                    f"Diagnostico do WinGet: {winget_failure_diagnostics}"
                )
                return result

            if direct_installer.install_package(package, logger):
                logger.success(package_name, status="installed")
                result["status"] = "installed"
                result["install_method"] = "fallback_direct_after_systemic_winget_failure"
                result["detail"] = (
                    "Instalado via fallback direto oficial apos falha sistemica anterior do WinGet nesta maquina. "
                    f"Diagnostico do WinGet: {winget_failure_diagnostics}"
                )
                return result

            logger.error(
                f"Falha no fallback de instalacao de '{package_name}' apos bypass do WinGet.",
                status="fallback_failed",
                package_name=package_name,
            )
            result["status"] = "failed"
            result["install_method"] = "fallback_direct_after_systemic_winget_failure"
            result["detail"] = (
                "O WinGet foi pulado por falha sistemica anterior e o fallback direto oficial nao concluiu a instalacao. "
                f"Diagnostico do WinGet: {winget_failure_diagnostics}"
            )
            return result

        logger.info(
            f"Validando pacote '{package_name}' ({winget_id})...",
            status="checking",
            package_name=package_name,
        )

        package_status = _check_winget_package_status(winget, winget_id)
        if package_status["found"]:
            logger.success(package_name, status="already_installed")
            result["status"] = "already_installed"
            result["install_method"] = "winget_detect"
            result["detail"] = "Pacote localizado pelo WinGet antes da instalacao."
            return result

        prerequisite_check = _ensure_catalog_prerequisites(package, logger, direct_installer)
        if not prerequisite_check["ready"]:
            result["status"] = "failed"
            result["install_method"] = "prerequisite_check"
            result["detail"] = prerequisite_check["detail"]
            return result

        logger.info(
            f"Iniciando instalacao automatizada de '{package_name}' ({winget_id}).",
            status="installing",
            package_name=package_name,
        )
        install_result = _install_winget_package(winget, winget_id)
        if install_result["success"]:
            logger.success(package_name, status="installed")
            result["status"] = "installed"
            result["install_method"] = "winget"
            result["detail"] = "Instalado com sucesso pelo WinGet."
            return result

        if install_result.get("timed_out"):
            logger.warning(
                f"A instalacao de '{package_name}' excedeu o tempo limite previsto no WinGet. Verificando se o pacote foi instalado mesmo assim.",
                status="install_timeout",
                package_name=package_name,
            )
            package_status_after_timeout = _check_winget_package_status(winget, winget_id)
            if package_status_after_timeout["found"] or direct_installer.is_package_present(package):
                logger.success(package_name, status="installed")
                result["status"] = "installed"
                result["install_method"] = "winget_timeout_but_present"
                result["detail"] = (
                    "O comando do WinGet excedeu o tempo limite, mas o pacote foi detectado no host apos a espera."
                )
                return result

        if package.get("fallback_installer") and _is_retryable_winget_install_failure(install_result):
            winget_failure_diagnostics = _build_winget_failure_diagnostics(install_result)
            network_guidance = winget.build_network_guidance() if hasattr(winget, "build_network_guidance") else ""
            logger.warning(
                f"Falha no WinGet para '{package_name}'. Diagnostico: {winget_failure_diagnostics}"
                + (f" | {network_guidance}" if network_guidance else ""),
                status="winget_failure_diagnostics",
                package_name=package_name,
            )
            logger.warning(
                f"Falha no WinGet para '{package_name}'. Tentando fallback direto oficial.",
                status="fallback_retry",
                package_name=package_name,
            )
            if direct_installer.is_package_present(package):
                logger.success(package_name, status="already_installed")
                result["status"] = "already_installed"
                result["install_method"] = "registry_detect"
                result["detail"] = (
                    "Pacote detectado no host apos falha do WinGet, sem necessidade de fallback. "
                    f"Diagnostico do WinGet: {winget_failure_diagnostics}"
                )
                return result

            if direct_installer.install_package(package, logger):
                logger.success(package_name, status="installed")
                result["status"] = "installed"
                result["install_method"] = "fallback_direct_after_winget"
                result["detail"] = (
                    "Instalado via fallback direto oficial apos falha recuperavel do WinGet. "
                    f"Diagnostico do WinGet: {winget_failure_diagnostics}"
                )
                return result

            logger.error(
                f"Falha no fallback de instalacao de '{package_name}' apos erro do WinGet.",
                status="fallback_failed",
                package_name=package_name,
            )
            result["status"] = "failed"
            result["install_method"] = "fallback_direct_after_winget"
            result["detail"] = (
                "O WinGet falhou e o fallback direto oficial tambem nao concluiu a instalacao. "
                f"Diagnostico do WinGet: {winget_failure_diagnostics}"
            )
            return result

        logger.error(
            f"Falha na instalacao automatizada de '{package_name}' ({winget_id}): {install_result['detail']}",
            status="install_error",
            package_name=package_name,
        )
        result["status"] = "failed"
        result["install_method"] = "winget"
        result["detail"] = install_result["detail"]
        return result

    package_present = False
    if winget.is_installed():
        logger.info(
            f"Validando pacote '{package_name}' ({winget_id}) para {operation}...",
            status="checking",
            package_name=package_name,
        )
        package_status = _check_winget_package_status(winget, winget_id)
        package_present = package_status["found"]
        if not package_present:
            logger.info(
                f"Pacote '{package_name}' nao esta presente para {operation}.",
                status="not_installed",
                package_name=package_name,
            )
            result["status"] = "not_installed"
            result["install_method"] = "winget_not_found"
            result["detail"] = f"Pacote nao localizado pelo WinGet para {operation}."
            return result
    else:
        package_present = direct_installer.is_package_present(package)
        if not package_present:
            logger.info(
                f"Pacote '{package_name}' nao esta presente para {operation}.",
                status="not_installed",
                package_name=package_name,
            )
            result["status"] = "not_installed"
            result["install_method"] = "registry_not_found"
            result["detail"] = f"Pacote nao localizado para {operation}."
            return result

        logger.warning(
            f"Pacote '{package_name}' foi detectado, mas a operacao '{operation}' exige WinGet acessivel neste fluxo.",
            status="winget_unavailable",
            package_name=package_name,
        )
        result["status"] = "blocked"
        result["install_method"] = "blocked_no_winget"
        result["detail"] = f"Pacote detectado, mas a operacao '{operation}' exige WinGet acessivel neste fluxo."
        return result

    if operation == "update":
        logger.info(
            f"Iniciando atualizacao automatizada de '{package_name}' ({winget_id}).",
            status="updating",
            package_name=package_name,
        )
        update_result = _upgrade_winget_package(winget, winget_id)
        if update_result["success"]:
            logger.success(package_name, status="updated")
            result["status"] = "updated"
            result["install_method"] = "winget_upgrade"
            result["detail"] = "Atualizado com sucesso pelo WinGet."
            return result

        logger.error(
            f"Falha na atualizacao automatizada de '{package_name}' ({winget_id}): {update_result['detail']}",
            status="update_error",
            package_name=package_name,
        )
        result["status"] = "failed"
        result["install_method"] = "winget_upgrade"
        result["detail"] = update_result["detail"]
        return result

    logger.info(
        f"Iniciando desinstalacao automatizada de '{package_name}' ({winget_id}).",
        status="uninstalling",
        package_name=package_name,
    )
    uninstall_result = _uninstall_winget_package(winget, winget_id)
    if uninstall_result["success"]:
        logger.success(package_name, status="removed")
        result["status"] = "removed"
        result["install_method"] = "winget_uninstall"
        result["detail"] = "Desinstalado com sucesso pelo WinGet."
        return result

    logger.error(
        f"Falha na desinstalacao automatizada de '{package_name}' ({winget_id}): {uninstall_result['detail']}",
        status="uninstall_error",
        package_name=package_name,
    )
    result["status"] = "failed"
    result["install_method"] = "winget_uninstall"
    result["detail"] = uninstall_result["detail"]
    return result


def execute_package_plan(profile, logger, winget, direct_installer, operation: str = "install"):
    """Executa o plano de processamento dos pacotes do perfil."""
    operation = normalize_operation(operation)
    packages = profile.get("packages", [])
    if not packages:
        logger.warning(
            "O catalogo nao possui pacotes cadastrados. Nenhuma acao sera executada.",
            status="empty_catalog",
        )
        return {
            "operation": operation,
            "summary": build_summary_template(operation),
            "packages": [],
        }

    summary = build_summary_template(operation)
    package_results = []
    logged_systemic_bypass = False

    for package in packages:
        if operation == "install" and _can_bypass_winget_install(winget) and not logged_systemic_bypass:
            logger.warning(
                "Sessao marcada como fallback-first para os proximos pacotes com instalador direto, "
                "porque o WinGet ja falhou de forma sistemica nesta execucao. "
                f"Diagnostico: {_get_systemic_winget_failure_diagnostics(winget)}",
                status="winget_session_degraded",
            )
            logged_systemic_bypass = True
        package_result = process_package(package, logger, winget, direct_installer, operation=operation)
        package_results.append(package_result)
        status = package_result["status"]
        if status in summary:
            summary[status] += 1

    summary_parts = [f"{summary[key]} {label.lower()}" for key, label in SUMMARY_LAYOUTS[operation]]
    logger.info(
        "Execucao concluida: " + ", ".join(summary_parts) + ".",
        status="execution_summary",
    )
    return {"operation": operation, "summary": summary, "packages": package_results}


def write_execution_report(profile, results, logger):
    """Gera um relatorio CSV com resumo e rastreabilidade por pacote."""
    return reporting_write_execution_report(
        profile,
        results,
        logger,
        reports_dir=REPORTS_DIR,
        allowed_operations=ALLOWED_OPERATIONS,
    )


def run_application(
    logger_observer=None,
    profile_name: str | None = None,
    selected_packages: list[str] | None = None,
    custom_packages: list[dict] | None = None,
    operation: str = "install",
):
    """Executa o fluxo principal do instalador e retorna os artefatos principais."""
    operation = normalize_operation(operation)
    logger = create_logger(logger_observer=logger_observer)
    winget, direct_installer = bootstrap(logger)
    package_profile = load_package_catalog(
        logger,
        profile_name=profile_name,
        selected_packages=selected_packages,
        custom_packages=custom_packages,
    )
    execution_results = execute_package_plan(package_profile, logger, winget, direct_installer, operation=operation)
    report_path = write_execution_report(package_profile, execution_results, logger)
    return package_profile, execution_results, report_path, Path(logger.log_file)


if __name__ == "__main__":
    if is_frozen_runtime():
        try:
            launch_operator_runtime_window()
        except Exception as error:
            show_operator_message(
                "Instalador Labs - Erro",
                f"A interface do instalador encontrou um erro.\n\n{error}",
                icon=MB_ICONERROR,
            )
            raise
    else:
        try:
            package_profile, execution_results, report_path, log_path = run_application()
        except SystemExit:
            raise
        except Exception as error:
            show_operator_message(
                "Instalador Labs - Erro",
                f"O instalador encontrou um erro inesperado.\n\n{error}",
                icon=MB_ICONERROR,
            )
            raise
        else:
            show_operator_message(
                "Instalador Labs - Execucao concluida",
                build_execution_summary_text(package_profile, execution_results, report_path, log_path),
                icon=MB_ICONINFORMATION,
            )



