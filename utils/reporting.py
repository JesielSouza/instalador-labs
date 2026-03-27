import csv
from datetime import datetime
from pathlib import Path


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


OPERATION_TITLES = {
    "install": "Instalacao",
    "update": "Atualizacao",
    "uninstall": "Desinstalacao",
}


class ReportingError(ValueError):
    """Erro de configuracao/uso do modulo de relatorios."""



def normalize_operation(operation: str | None, allowed_operations: tuple[str, ...]) -> str:
    candidate = (operation or "install").strip().lower()
    if candidate not in allowed_operations:
        raise ReportingError(f"Operacao invalida: {operation}")
    return candidate



def classify_package_result(package_result: dict) -> str:
    """Classifica a causa/rota principal de cada pacote para facilitar analise em campo."""
    status = package_result.get("status", "")
    method = package_result.get("install_method", "")
    detail = (package_result.get("detail") or "").lower()

    if status in ("installed", "updated", "removed"):
        if "reiniz" in detail or "reinicializ" in detail:
            return "success_reboot_required"
        if "fallback" in method:
            return "success_fallback_direct"
        if "winget" in method:
            return "success_winget"
        return "success_other"

    if status in ("already_installed", "not_installed"):
        return "already_present"

    if status == "manual":
        return "manual_action_required"

    if status == "pending":
        return "pending_validation"

    if status == "blocked":
        if "blocked_no_winget" in method:
            return "blocked_winget_unavailable"
        return "blocked_other"

    if status != "failed":
        return "unknown"

    if "prerequisite" in method or "pre-requisito" in detail:
        return "failed_prerequisite"
    if "certificate_verify_failed" in detail or "local issuer certificate" in detail or "ssl" in detail:
        return "failed_ssl_tls"
    if "2316632079" in detail or "failed when opening source" in detail or "fontes do winget" in detail:
        return "failed_winget_source"
    if "1603" in detail:
        return "failed_msi_1603"
    if "reiniz" in detail or "reinicializ" in detail or "3010" in detail or "1641" in detail:
        return "failed_reboot_required"
    if "timeout" in detail or "proxy" in detail or "firewall" in detail or "bits" in detail:
        return "failed_network_or_policy"
    if "fallback" in method:
        return "failed_fallback_direct"
    if "winget" in method:
        return "failed_winget_generic"
    return "failed_other"



def summarize_execution_diagnostics(results: dict) -> dict:
    """Resume os sinais dominantes da execucao para exibicao ao operador."""
    category_groups = {
        "winget": {
            "failed_winget_source",
            "failed_winget_generic",
            "blocked_winget_unavailable",
        },
        "network_or_policy": {
            "failed_ssl_tls",
            "failed_network_or_policy",
        },
        "msi_or_prerequisite": {
            "failed_msi_1603",
            "failed_prerequisite",
            "failed_reboot_required",
        },
        "fallback": {
            "failed_fallback_direct",
            "success_fallback_direct",
        },
        "manual": {
            "manual_action_required",
            "pending_validation",
        },
    }

    counts = {group: 0 for group in category_groups}
    details = []
    for package_result in results.get("packages", []):
        category = classify_package_result(package_result)
        for group, mapped_categories in category_groups.items():
            if category in mapped_categories:
                counts[group] += 1
                break
        if category.startswith("failed_"):
            details.append((package_result.get("package", "?"), category))

    dominant_groups = [group for group, count in counts.items() if count > 0]
    detail = (
        "Diagnostico dominante da execucao: "
        + ", ".join(f"{group}={counts[group]}" for group in dominant_groups)
        if dominant_groups
        else "Diagnostico dominante da execucao: sem sinais relevantes agregados."
    )
    return {
        "counts": counts,
        "dominant_groups": dominant_groups,
        "detail": detail,
        "failed_details": details,
    }



def build_execution_summary_text(
    profile: dict,
    results: dict,
    report_path: Path,
    log_path: Path,
    allowed_operations: tuple[str, ...],
) -> str:
    """Monta um resumo amigavel para o operador ao final da execucao."""
    operation = normalize_operation(results.get("operation", "install"), allowed_operations)
    summary = results["summary"]
    package_results = results.get("packages", [])
    manual_packages = [item["package"] for item in package_results if item.get("status") == "manual"]
    execution_diagnostics = summarize_execution_diagnostics(results)

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

    if execution_diagnostics["dominant_groups"]:
        message_lines.extend(
            [
                "",
                execution_diagnostics["detail"],
            ]
        )
        if execution_diagnostics["failed_details"]:
            top_failures = ", ".join(
                f"{package} ({category})"
                for package, category in execution_diagnostics["failed_details"][:3]
            )
            message_lines.append(f"Principais sinais de falha: {top_failures}")

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



def write_execution_report(
    profile: dict,
    results: dict,
    logger,
    reports_dir: Path,
    allowed_operations: tuple[str, ...],
):
    """Gera um relatorio CSV com resumo e rastreabilidade por pacote."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"execution_report_{timestamp}.csv"
    operation = normalize_operation(results.get("operation", "install"), allowed_operations)
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
                "diagnostic_category",
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
                    classify_package_result(package_result),
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
