import ctypes
import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

from config import REPORTS_DIR
from utils.fallback_installer import DirectInstallerManager
from utils.logger import LabLogger
from utils.package_loader import (
    PackageProfileValidationError,
    PackageSelectionError,
    list_package_profiles,
    load_default_package_profile,
    load_profile_by_name,
    select_profile_packages,
)
from utils.winget import WinGetManager

MB_ICONINFORMATION = 0x40
MB_ICONWARNING = 0x30
MB_ICONERROR = 0x10
MB_OK = 0x0
_OPERATOR_WINDOW_ACTIVE = False
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


class OperatorVisibleError(RuntimeError):
    """Erro apresentavel ao operador em interfaces empacotadas."""


def is_admin():
    """Verifica se o script esta rodando com privilegios de Administrador."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def is_frozen_runtime() -> bool:
    """Indica se o fluxo esta rodando a partir do executavel empacotado."""
    return bool(getattr(sys, "frozen", False))


def show_operator_message(title: str, message: str, icon: int = MB_ICONINFORMATION) -> None:
    """Exibe um resumo visivel ao operador quando o fluxo roda como executavel."""
    if not is_frozen_runtime():
        return

    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, MB_OK | icon)
    except Exception:
        print(f"{title}\n{message}")


def fail_with_operator_message(message: str, exit_code: int = 1, title: str = "Instalador Labs - Erro"):
    """Encerra a execucao exibindo o motivo ao operador."""
    if _OPERATOR_WINDOW_ACTIVE:
        raise OperatorVisibleError(message)

    show_operator_message(title, message, icon=MB_ICONERROR)
    raise SystemExit(exit_code)


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
    operation = normalize_operation(results.get("operation", "install"))
    summary = results["summary"]
    package_results = results.get("packages", [])
    manual_packages = [item["package"] for item in package_results if item.get("status") == "manual"]

    message_lines = [
        f"Perfil: {profile.get('profile', 'desconhecido')}",
        f"Operacao: {OPERATION_TITLES[operation]}",
        "",
    ]

    for key, label in SUMMARY_LAYOUTS[operation]:
        message_lines.append(f"{label}: {summary.get(key, 0)}")

    if manual_packages:
        message_lines.extend(
            [
                "",
                "Atencao: existe item que requer acao manual.",
                f"Itens manuais: {', '.join(manual_packages)}",
            ]
        )

    if summary.get("failed") or summary.get("blocked"):
        message_lines.extend(
            [
                "",
                "Consulte o log para detalhes tecnicos antes de encerrar o atendimento.",
            ]
        )

    message_lines.extend(
        [
            "",
            f"Relatorio: {report_path}",
            f"Log: {log_path}",
        ]
    )

    return "\n".join(message_lines)


def _open_target_for_operator(target: Path | str):
    """Abre um arquivo, pasta ou URL do instalador para o operador no Windows."""
    os.startfile(str(target))


def launch_operator_runtime_window():
    """Abre uma janela unica para acompanhar a execucao do instalador."""
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk

    available_profiles = list_package_profiles()
    if not available_profiles:
        raise RuntimeError("Nenhum perfil de pacotes foi encontrado na pasta de catalogos.")

    default_profile_name = load_default_package_profile().get("profile")
    available_profile_names = [item["profile"] for item in available_profiles]
    if default_profile_name not in available_profile_names:
        default_profile_name = available_profile_names[0]

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
    }

    root = tk.Tk()
    root.title("Instalador Labs")
    root.minsize(720, 500)

    container = ttk.Frame(root, padding=16)
    container.pack(fill="both", expand=True)

    ttk.Label(
        container,
        text="Instalador Labs",
        font=("Segoe UI", 18, "bold"),
    ).pack(anchor="w")

    status_var = tk.StringVar(value="Pronto para iniciar a instalacao automatizada.")
    ttk.Label(
        container,
        textvariable=status_var,
        font=("Segoe UI", 10),
    ).pack(anchor="w", pady=(6, 12))

    selection_frame = ttk.LabelFrame(container, text="Selecao")
    selection_frame.pack(fill="x")

    profile_row = ttk.Frame(selection_frame)
    profile_row.pack(fill="x", padx=10, pady=(10, 6))

    ttk.Label(profile_row, text="Perfil:").pack(side="left")
    profile_var = tk.StringVar(value=default_profile_name)
    profile_combo = ttk.Combobox(
        profile_row,
        textvariable=profile_var,
        state="readonly",
        values=available_profile_names,
        width=20,
    )
    profile_combo.pack(side="left", padx=(8, 0))

    ttk.Label(profile_row, text="Acao:").pack(side="left", padx=(12, 0))
    action_var = tk.StringVar(value=display_by_operation["install"])
    action_combo = ttk.Combobox(
        profile_row,
        textvariable=action_var,
        state="readonly",
        values=list(operation_display_map.keys()),
        width=16,
    )
    action_combo.pack(side="left", padx=(8, 0))

    selection_status_var = tk.StringVar(value="")
    ttk.Label(profile_row, textvariable=selection_status_var).pack(side="left", padx=(12, 0))

    package_row = ttk.Frame(selection_frame)
    package_row.pack(fill="x", padx=10, pady=(0, 10))

    package_listbox = tk.Listbox(
        package_row,
        selectmode="extended",
        exportselection=False,
        height=5,
        font=("Segoe UI", 10),
    )
    package_listbox.pack(side="left", fill="x", expand=True)

    package_scrollbar = ttk.Scrollbar(package_row, orient="vertical", command=package_listbox.yview)
    package_scrollbar.pack(side="left", fill="y")
    package_listbox.configure(yscrollcommand=package_scrollbar.set)

    package_action_column = ttk.Frame(package_row)
    package_action_column.pack(side="left", padx=(10, 0))

    select_all_button = ttk.Button(package_action_column, text="Marcar todos")
    select_all_button.pack(fill="x")

    clear_selection_button = ttk.Button(package_action_column, text="Limpar")
    clear_selection_button.pack(fill="x", pady=(8, 0))

    summary_frame = ttk.LabelFrame(container, text="Resumo")
    summary_frame.pack(fill="x", pady=(12, 0))

    summary_box = tk.Text(
        summary_frame,
        wrap="word",
        height=7,
        width=100,
        font=("Consolas", 10),
        padx=10,
        pady=10,
    )
    summary_box.pack(fill="x", expand=False)
    summary_box.configure(state="disabled")

    log_frame = ttk.LabelFrame(container, text="Log ao vivo")
    log_frame.pack(fill="both", expand=True, pady=(12, 0))

    log_box = scrolledtext.ScrolledText(
        log_frame,
        wrap="word",
        height=9,
        width=100,
        font=("Consolas", 10),
        padx=10,
        pady=10,
        state="disabled",
    )
    log_box.pack(fill="both", expand=True)

    button_row = ttk.Frame(container)
    button_row.pack(fill="x", pady=(12, 0))

    start_button = ttk.Button(button_row, text=OPERATION_BUTTON_LABELS["install"])
    start_button.pack(side="left")

    report_button = ttk.Button(button_row, text="Abrir relatorio", state="disabled")
    report_button.pack(side="left", padx=(8, 0))

    log_button = ttk.Button(button_row, text="Abrir log", state="disabled")
    log_button.pack(side="left", padx=(8, 0))

    folder_button = ttk.Button(button_row, text="Abrir pasta", state="disabled")
    folder_button.pack(side="left", padx=(8, 0))

    reference_button = ttk.Button(button_row, text="Abrir referencia", state="disabled")
    reference_button.pack(side="left", padx=(8, 0))

    close_button = ttk.Button(button_row, text="Fechar", command=root.destroy)
    close_button.pack(side="right")

    def get_selected_operation() -> str:
        return operation_display_map[action_var.get()]

    def set_window_geometry(width: int, height: int):
        root.update_idletasks()
        required_width = max(width, root.winfo_reqwidth())
        required_height = max(height, root.winfo_reqheight())

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
            clamped_width = min(required_width, available_width - 32)
            clamped_height = min(required_height, available_height - 48)
            x = work_area.left + max((available_width - clamped_width) // 2, 0)
            y = work_area.top + max((available_height - clamped_height) // 5, 0)
        else:
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()
            clamped_width = required_width
            clamped_height = required_height
            x = max((screen_width - clamped_width) // 2, 0)
            y = max((screen_height - clamped_height) // 5, 0)

        root.geometry(f"{clamped_width}x{clamped_height}+{x}+{y}")

    def set_summary(text: str):
        summary_box.configure(state="normal")
        summary_box.delete("1.0", "end")
        summary_box.insert("1.0", text)
        summary_box.configure(state="disabled")

    def set_selection_controls_enabled(enabled: bool):
        combo_state = "readonly" if enabled else "disabled"
        action_state = "normal" if enabled else "disabled"
        profile_combo.configure(state=combo_state)
        action_combo.configure(state=combo_state)
        package_listbox.configure(state=action_state)
        select_all_button.configure(state=action_state)
        clear_selection_button.configure(state=action_state)

    def get_selected_package_names() -> list[str]:
        return [package_listbox.get(index) for index in package_listbox.curselection()]

    def update_selection_status():
        total_packages = package_listbox.size()
        selected_count = len(get_selected_package_names())
        selection_status_var.set(f"Pacotes marcados: {selected_count}/{total_packages}")

    def update_idle_summary():
        if state["running"] or state["has_completed"]:
            return

        selected_packages = get_selected_package_names()
        package_total = package_listbox.size()
        selected_operation = get_selected_operation()
        operation_title = OPERATION_TITLES[selected_operation].lower()
        start_label = OPERATION_BUTTON_LABELS[selected_operation]
        set_summary(
            f"Perfil selecionado: {profile_var.get()}\n"
            f"Operacao: {OPERATION_TITLES[selected_operation]}\n"
            f"Pacotes marcados: {len(selected_packages)} de {package_total}.\n\n"
            f"Clique em '{start_label}' para executar a {operation_title.lower()} apenas nos softwares marcados.\n"
            "O log ao vivo aparecera abaixo e, ao final, os botoes para abrir relatorio e log serao habilitados."
        )

    def update_idle_presentation():
        if state["running"] or state["has_completed"]:
            return

        selected_operation = get_selected_operation()
        start_button.configure(text=OPERATION_BUTTON_LABELS[selected_operation])
        status_var.set(f"Pronto para iniciar a {OPERATION_TITLES[selected_operation].lower()} automatizada.")
        state["manual_reference_url"] = resolve_manual_reference_url(profile_var.get(), get_selected_package_names())
        update_reference_button()
        update_idle_summary()

    def load_profile_packages_into_list(profile_name: str):
        profile = load_profile_by_name(profile_name)
        package_names = [package["software"] for package in profile.get("packages", [])]
        package_listbox.delete(0, "end")
        for package_name in package_names:
            package_listbox.insert("end", package_name)
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
        package_listbox.selection_clear(0, "end")
        update_selection_status()
        update_idle_presentation()

    def apply_window_mode(mode: str):
        if mode == "idle":
            set_window_geometry(820, 620)
            summary_box.configure(height=6)
            log_box.configure(height=6)
            package_listbox.configure(height=5)
        elif mode == "running":
            set_window_geometry(980, 720)
            summary_box.configure(height=8)
            log_box.configure(height=16)
            package_listbox.configure(height=5)
        elif mode == "completed":
            set_window_geometry(940, 620)
            summary_box.configure(height=7)
            log_box.configure(height=11)
            package_listbox.configure(height=5)

    def clear_log():
        log_box.configure(state="normal")
        log_box.delete("1.0", "end")
        log_box.configure(state="disabled")

    def append_log_line(line: str):
        log_box.configure(state="normal")
        log_box.insert("end", f"{line}\n")
        log_box.see("end")
        log_box.configure(state="disabled")

    def resolve_manual_reference_url(profile_name: str, selected_package_names: list[str]) -> str | None:
        profile = load_profile_by_name(profile_name)
        package_map = {package["software"]: package for package in profile.get("packages", [])}
        urls = []
        for package_name in selected_package_names:
            package = package_map.get(package_name)
            if not package:
                continue
            reference_url = package.get("manual_reference_url")
            if reference_url and reference_url not in urls:
                urls.append(reference_url)

        if len(urls) == 1:
            return urls[0]
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

    def worker(selected_profile_name: str, selected_package_names: list[str], selected_operation: str):
        try:
            package_profile, execution_results, report_path, log_path = run_application(
                logger_observer=lambda line: event_queue.put(("log", line)),
                profile_name=selected_profile_name,
                selected_packages=selected_package_names,
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

        selected_profile_name = profile_var.get()
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
        set_summary(
            f"Preparando a {OPERATION_TITLES[selected_operation].lower()} do perfil '{selected_profile_name}' com {len(selected_package_names)} pacote(s) marcado(s).\n"
            "O resumo final sera exibido aqui ao termino."
        )
        Thread(target=worker, args=(selected_profile_name, selected_package_names, selected_operation), daemon=True).start()

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
                    apply_window_mode("completed")
                    enable_artifact_buttons()
                elif event_type == "operator_error":
                    message, log_path = payload
                    state["log_path"] = log_path
                    state["folder_path"] = log_path.parent if log_path else None
                    set_summary(f"A execucao foi interrompida.\n\n{message}" + (f"\n\nLog: {log_path}" if log_path else ""))
                    status_var.set("Execucao interrompida. Consulte o log para detalhes.")
                    apply_window_mode("completed")
                    enable_artifact_buttons()
                elif event_type == "unexpected_error":
                    message, log_path = payload
                    state["log_path"] = log_path
                    state["folder_path"] = log_path.parent if log_path else None
                    set_summary(f"O instalador encontrou um erro inesperado.\n\n{message}" + (f"\n\nLog: {log_path}" if log_path else ""))
                    status_var.set("Erro inesperado durante a execucao. Consulte o log.")
                    apply_window_mode("completed")
                    enable_artifact_buttons()
        except Empty:
            pass

        root.after(120, poll_events)

    profile_combo.bind("<<ComboboxSelected>>", lambda _event: load_profile_packages_into_list(profile_var.get()))
    action_combo.bind("<<ComboboxSelected>>", lambda _event: update_idle_presentation())
    package_listbox.bind("<<ListboxSelect>>", lambda _event: (update_selection_status(), update_idle_presentation()))

    select_all_button.configure(command=select_all_packages)
    clear_selection_button.configure(command=clear_selected_packages)
    report_button.configure(command=lambda: _open_target_for_operator(state["report_path"]))
    log_button.configure(command=lambda: _open_target_for_operator(state["log_path"]))
    folder_button.configure(command=lambda: _open_target_for_operator(state["folder_path"]))
    reference_button.configure(command=lambda: _open_target_for_operator(state["manual_reference_url"]))
    start_button.configure(command=start_execution)

    load_profile_packages_into_list(default_profile_name)
    apply_window_mode("idle")

    root.after(120, poll_events)
    root.mainloop()
    _OPERATOR_WINDOW_ACTIVE = False

def bootstrap(logger):
    """Inicializa o sistema e valida requisitos basicos do ambiente."""
    winget = WinGetManager()
    direct_installer = DirectInstallerManager()

    logger.info("Iniciando GSD - Instalador de Laboratorios...", status="bootstrap")

    if not is_admin():
        logger.error(
            "ERRO DE PRIVILEGIO: O script deve ser executado como Administrador.",
            status="bootstrap_error",
        )
        fail_with_operator_message("O instalador deve ser executado como Administrador.")
    logger.info("Privilegios de Administrador confirmados.", status="bootstrap")

    winget_state = winget.classify_winget_state()
    diagnostics = winget_state["diagnostics"]
    logger.info(
        "Windows detectado: "
        f"{diagnostics['product_name']} | versao {diagnostics['display_version']} | build {diagnostics['build']}.",
        status="bootstrap",
    )

    if winget_state["state"] == "available":
        logger.info(winget_state["reason"], status="bootstrap")
        proxy_diagnostics = winget.get_proxy_diagnostics()
        if proxy_diagnostics["active"]:
            logger.warning(
                "Proxy detectado no host. O WinGet pode falhar em redes com firewall/proxy corporativo. "
                + proxy_diagnostics["detail"],
                status="bootstrap_proxy_detected",
            )
        client_health = winget.ensure_client_ready()
        if client_health["healthy"]:
            logger.info(client_health["detail"], status="bootstrap")
        else:
            logger.warning(
                "WinGet detectado, mas ainda com sinais de instabilidade apos tentativa automatica de recuperacao. "
                + client_health["detail"],
                status="bootstrap_degraded",
            )
    else:
        logger.warning(
            f"Modo degradado sem WinGet: {winget_state['reason']}",
            status="bootstrap_degraded",
        )

    logger.info(
        "Ambiente validado com sucesso. Pronto para carregar pacotes.",
        status="bootstrap",
    )
    return winget, direct_installer


def load_package_catalog(logger, profile_name: str | None = None, selected_packages: list[str] | None = None):
    """Carrega um catalogo JSON e opcionalmente filtra os pacotes selecionados."""
    try:
        profile = load_profile_by_name(profile_name) if profile_name else load_default_package_profile()
        profile = select_profile_packages(profile, selected_packages)
    except (FileNotFoundError, PackageProfileValidationError, PackageSelectionError) as error:
        logger.error(
            f"Falha ao carregar catalogo de pacotes: {error}",
            status="catalog_error",
        )
        fail_with_operator_message(f"Falha ao carregar o catalogo de pacotes.\n\n{error}")

    package_count = len(profile.get("packages", []))
    logger.info(
        f"Catalogo carregado: perfil '{profile.get('profile', 'desconhecido')}' com {package_count} pacote(s).",
        status="catalog_loaded",
    )
    return profile

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
        if not winget.is_installed():
            if direct_installer.is_package_present(package):
                logger.success(package_name, status="already_installed")
                result["status"] = "already_installed"
                result["install_method"] = "registry_detect"
                result["detail"] = "Pacote detectado no host sem necessidade de instalacao."
                return result

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

    for package in packages:
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
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"execution_report_{timestamp}.csv"
    operation = normalize_operation(results.get("operation", "install"))
    summary = results["summary"]
    package_results = results["packages"]

    summary_rows = [
        ("profile", profile.get("profile", "desconhecido")),
        ("description", profile.get("description", "")),
        ("operation", operation),
        ("total_packages", len(profile.get("packages", []))),
    ]
    summary_rows.extend((key, summary.get(key, 0)) for key, _label in SUMMARY_LAYOUTS[operation])

    with report_path.open("w", encoding="utf-8", newline="") as report_file:
        writer = csv.writer(report_file)
        writer.writerow(["section", "key", "value"])
        for key, value in summary_rows:
            writer.writerow(["summary", key, value])

        writer.writerow([])
        writer.writerow(
            [
                "packages",
                "software",
                "operation",
                "status",
                "install_method",
                "install_type",
                "winget_id",
                "catalog_notes",
                "manual_reference_url",
                "detail",
            ]
        )
        for package_result in package_results:
            writer.writerow(
                [
                    "package",
                    package_result["package"],
                    package_result.get("operation", operation),
                    package_result["status"],
                    package_result["install_method"],
                    package_result["install_type"],
                    package_result["winget_id"],
                    package_result["catalog_notes"],
                    package_result.get("manual_reference_url", ""),
                    package_result["detail"],
                ]
            )

    logger.info(
        f"Relatorio CSV gerado em '{report_path}'.",
        status="report_generated",
    )
    return report_path


def run_application(
    logger_observer=None,
    profile_name: str | None = None,
    selected_packages: list[str] | None = None,
    operation: str = "install",
):
    """Executa o fluxo principal do instalador e retorna os artefatos principais."""
    operation = normalize_operation(operation)
    logger = create_logger(logger_observer=logger_observer)
    winget, direct_installer = bootstrap(logger)
    package_profile = load_package_catalog(logger, profile_name=profile_name, selected_packages=selected_packages)
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



