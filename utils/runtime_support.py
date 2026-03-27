import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import winreg
from pathlib import Path

from config import DOWNLOADS_DIR, LOGS_DIR, REPORTS_DIR
from utils.package_loader import build_profile_endpoint_diagnostics

MB_ICONINFORMATION = 0x40
MB_ICONWARNING = 0x30
MB_ICONERROR = 0x10
MB_OK = 0x0


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



def get_pending_reboot_diagnostics() -> dict:
    """Coleta sinais comuns de reinicializacao pendente no Windows."""
    signals = []
    checks = [
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
            None,
            "CBS/RebootPending",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
            None,
            "WindowsUpdate/RebootRequired",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager",
            "PendingFileRenameOperations",
            "SessionManager/PendingFileRenameOperations",
        ),
    ]

    for root, path, value_name, label in checks:
        try:
            with winreg.OpenKey(root, path) as registry_key:
                if value_name is None:
                    signals.append(label)
                    continue

                value, _ = winreg.QueryValueEx(registry_key, value_name)
                if value:
                    signals.append(label)
        except OSError:
            continue

    detail = ", ".join(signals) if signals else "Nenhum indicio de reinicializacao pendente."
    return {"active": bool(signals), "signals": signals, "detail": detail}



def get_host_capacity_diagnostics() -> dict:
    """Coleta arquitetura do host e espaco livre do disco do sistema."""
    system_drive = os.environ.get("SystemDrive", "C:")
    root_path = f"{system_drive}\\"

    try:
        disk_usage = shutil.disk_usage(root_path)
        free_gb = round(disk_usage.free / (1024 ** 3), 2)
    except OSError:
        free_gb = None

    architecture = (
        os.environ.get("PROCESSOR_ARCHITEW6432")
        or os.environ.get("PROCESSOR_ARCHITECTURE")
        or "desconhecida"
    )
    normalized_architecture = architecture.lower()

    issues = []
    if "64" not in normalized_architecture:
        issues.append(f"Arquitetura nao x64 detectada: {architecture}")
    if free_gb is not None and free_gb < 5:
        issues.append(f"Pouco espaco livre em {root_path}: {free_gb} GB")

    detail = (
        f"Diagnostico de host: arquitetura={architecture} | "
        + (
            f"espaco_livre_{root_path}={free_gb} GB"
            if free_gb is not None
            else f"espaco_livre_{root_path}=indisponivel"
        )
    )
    return {
        "architecture": architecture,
        "free_gb": free_gb,
        "system_drive": root_path,
        "issues": issues,
        "detail": detail,
    }



def get_runtime_directory_diagnostics() -> dict:
    """Valida se diretorios de trabalho e temporarios estao gravaveis."""
    targets = {
        "logs": LOGS_DIR,
        "reports": REPORTS_DIR,
        "downloads": DOWNLOADS_DIR,
        "temp": Path(tempfile.gettempdir()),
    }
    issues = []
    details = []

    for label, path in targets.items():
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".instalador_labs_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            details.append(f"{label}={path} (gravavel)")
        except OSError as error:
            issues.append(f"{label} sem escrita: {path}")
            details.append(f"{label}={path} (erro: {error})")

    return {
        "issues": issues,
        "detail": "Diagnostico de diretorios: " + " | ".join(details),
    }



def _probe_url_head(url: str, host: str) -> dict:
    """Tenta validar rapidamente a conectividade com um endpoint oficial."""
    safe_url = url.replace("'", "''")
    command = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        (
            f"try {{ $response = Invoke-WebRequest -UseBasicParsing -Uri '{safe_url}' -Method Head -TimeoutSec 12 -ErrorAction Stop; "
            "Write-Output $response.StatusCode; exit 0 } "
            "catch { Write-Output $_.Exception.Message; exit 1 }"
        ),
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {
            "host": host,
            "url": url,
            "ok": False,
            "detail": f"{host}: falha ao executar teste HEAD ({error})",
        }

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if completed.returncode == 0:
        status_text = stdout or "sem status"
        return {
            "host": host,
            "url": url,
            "ok": True,
            "detail": f"{host}: HEAD respondeu {status_text}",
        }

    reason = stdout or stderr or f"codigo {completed.returncode}"
    return {
        "host": host,
        "url": url,
        "ok": False,
        "detail": f"{host}: falha no teste HEAD ({reason})",
    }



def probe_catalog_endpoint_connectivity(profile: dict) -> dict:
    """Sonda rapidamente os hosts do catalogo para antecipar bloqueios de rede."""
    endpoint_diagnostics = build_profile_endpoint_diagnostics(profile)
    downloads = endpoint_diagnostics.get("downloads", [])
    unique_downloads = []
    seen_hosts = set()
    for item in downloads:
        host = item.get("host")
        url = item.get("download_url")
        if not host or not url or host in seen_hosts:
            continue
        seen_hosts.add(host)
        unique_downloads.append({"host": host, "url": url})

    probes = [_probe_url_head(item["url"], item["host"]) for item in unique_downloads]
    issues = [probe["detail"] for probe in probes if not probe["ok"]]
    ok_count = sum(1 for probe in probes if probe["ok"])
    detail = (
        f"Diagnostico de conectividade dos endpoints: hosts_testados={len(probes)} | "
        f"hosts_ok={ok_count} | falhas={len(issues)}"
    )
    return {
        "issues": issues,
        "detail": detail,
        "probes": probes,
    }



def show_operator_message(title: str, message: str, icon: int = MB_ICONINFORMATION) -> None:
    """Exibe um resumo visivel ao operador quando o fluxo roda como executavel."""
    if not is_frozen_runtime():
        return

    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, MB_OK | icon)
    except Exception:
        print(f"{title}\n{message}")



def fail_with_operator_message(message: str, operator_window_active: bool = False, exit_code: int = 1, title: str = "Instalador Labs - Erro"):
    """Encerra a execucao exibindo o motivo ao operador."""
    if operator_window_active:
        raise OperatorVisibleError(message)

    show_operator_message(title, message, icon=MB_ICONERROR)
    raise SystemExit(exit_code)
