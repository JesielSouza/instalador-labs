from utils.package_loader import (
    PackageProfileValidationError,
    PackageSelectionError,
    build_profile_endpoint_diagnostics,
)



def bootstrap_environment(
    logger,
    winget,
    direct_installer,
    is_admin,
    fail_with_operator_message,
    get_pending_reboot_diagnostics,
    get_host_capacity_diagnostics,
    get_runtime_directory_diagnostics,
):
    """Inicializa o sistema e valida requisitos basicos do ambiente."""
    logger.info("Iniciando GSD - Instalador de Laboratorios...", status="bootstrap")

    if not is_admin():
        logger.error(
            "ERRO DE PRIVILEGIO: O script deve ser executado como Administrador.",
            status="bootstrap_error",
        )
        fail_with_operator_message("O instalador deve ser executado como Administrador.")
    logger.info("Privilegios de Administrador confirmados.", status="bootstrap")

    pending_reboot = get_pending_reboot_diagnostics()
    if pending_reboot["active"]:
        logger.warning(
            "Reinicializacao pendente detectada no host. Algumas instalacoes silenciosas podem falhar ou pedir reboot. "
            + pending_reboot["detail"],
            status="bootstrap_reboot_pending",
        )

    host_capacity = get_host_capacity_diagnostics()
    logger.info(host_capacity["detail"], status="bootstrap")
    if host_capacity["issues"]:
        logger.warning(
            "Foram encontrados sinais de capacidade/arquitetura que podem impactar instalacoes automatizadas. "
            + ", ".join(host_capacity["issues"]),
            status="bootstrap_host_capacity_warning",
        )

    runtime_dirs = get_runtime_directory_diagnostics()
    logger.info(runtime_dirs["detail"], status="bootstrap")
    if runtime_dirs["issues"]:
        logger.warning(
            "Foram encontrados problemas de escrita em diretorios usados pelo instalador. "
            + ", ".join(runtime_dirs["issues"]),
            status="bootstrap_runtime_dirs_warning",
        )

    if hasattr(winget, "get_store_stack_diagnostics"):
        store_stack = winget.get_store_stack_diagnostics()
        logger.info(store_stack["detail"], status="bootstrap")
        if store_stack.get("issues"):
            logger.warning(
                "Foram encontrados sinais de indisponibilidade na stack Store/App Installer. "
                + ", ".join(store_stack["issues"]),
                status="bootstrap_store_stack_warning",
            )

    if hasattr(winget, "get_store_policy_diagnostics"):
        policy_diagnostics = winget.get_store_policy_diagnostics()
        logger.info(policy_diagnostics["detail"], status="bootstrap")
        if policy_diagnostics.get("issues"):
            logger.warning(
                "Foram encontradas politicas locais que podem bloquear Store/App Installer. "
                + ", ".join(policy_diagnostics["issues"]),
                status="bootstrap_store_policy_warning",
            )

    if hasattr(winget, "get_execution_alias_diagnostics"):
        alias_diagnostics = winget.get_execution_alias_diagnostics()
        logger.info(alias_diagnostics["detail"], status="bootstrap")
        if alias_diagnostics.get("issues"):
            logger.warning(
                "Foram encontrados sinais de problema no alias/executavel do WinGet. "
                + ", ".join(alias_diagnostics["issues"]),
                status="bootstrap_winget_alias_warning",
            )

    if hasattr(winget, "get_source_catalog_diagnostics"):
        source_diagnostics = winget.get_source_catalog_diagnostics()
        logger.info(source_diagnostics["detail"], status="bootstrap")
        if source_diagnostics.get("issues"):
            logger.warning(
                "Foram encontrados sinais de problema nas sources do WinGet. "
                + ", ".join(source_diagnostics["issues"]),
                status="bootstrap_winget_sources_warning",
            )

    if hasattr(winget, "get_windows_security_diagnostics"):
        security_diagnostics = winget.get_windows_security_diagnostics()
        logger.info(security_diagnostics["detail"], status="bootstrap")
        if security_diagnostics.get("issues"):
            logger.warning(
                "Foram encontrados sinais de politicas/servicos de seguranca que podem alterar o comportamento de binarios baixados. "
                + ", ".join(security_diagnostics["issues"]),
                status="bootstrap_windows_security_warning",
            )

    if hasattr(winget, "get_windows_update_diagnostics"):
        update_diagnostics = winget.get_windows_update_diagnostics()
        logger.info(update_diagnostics["detail"], status="bootstrap")
        if update_diagnostics.get("issues"):
            logger.warning(
                "Foram encontrados sinais de Windows Update/servicos que podem impactar instalacoes silenciosas. "
                + ", ".join(update_diagnostics["issues"]),
                status="bootstrap_windows_update_warning",
            )

    winget_state = winget.classify_winget_state()
    diagnostics = winget_state["diagnostics"]
    raw_product_name = diagnostics.get("raw_product_name", diagnostics["product_name"])
    windows_message = (
        "Windows detectado: "
        f"{diagnostics['product_name']} | versao {diagnostics['display_version']} | build {diagnostics['build']}."
    )
    if raw_product_name != diagnostics["product_name"]:
        windows_message += f" Registro legado reportou: {raw_product_name}."
    logger.info(
        windows_message,
        status="bootstrap",
    )

    if winget_state["state"] == "available":
        logger.info(winget_state["reason"], status="bootstrap")
        logger.info(
            f"Consulta inicial do WinGet concluida. Executavel: {winget.executable} | versao observada: {winget.get_version()}",
            status="bootstrap",
        )
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
            logger.info(
                "Estado final do WinGet apos bootstrap: "
                f"acao={client_health.get('action', 'none')} | "
                f"versao_inicial={client_health.get('initial_version', 'Desconhecida')} | "
                f"versao_final={client_health.get('final_version', 'Desconhecida')}",
                status="bootstrap",
            )
        else:
            logger.warning(
                "WinGet detectado, mas ainda com sinais de instabilidade apos tentativa automatica de recuperacao. "
                + client_health["detail"],
                status="bootstrap_degraded",
            )
            logger.warning(
                "Estado final do WinGet apos bootstrap degradado: "
                f"acao={client_health.get('action', 'unknown')} | "
                f"versao_inicial={client_health.get('initial_version', 'Desconhecida')} | "
                f"versao_final={client_health.get('final_version', 'Desconhecida')}",
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



def load_catalog_profile(
    logger,
    fail_with_operator_message,
    probe_catalog_endpoint_connectivity,
    build_dynamic_package_profile,
    load_profile_by_name,
    load_default_package_profile,
    select_profile_packages,
    profile_name: str | None = None,
    selected_packages: list[str] | None = None,
    custom_packages: list[dict] | None = None,
):
    """Carrega um catalogo JSON e opcionalmente filtra os pacotes selecionados."""
    try:
        if custom_packages is not None:
            profile = build_dynamic_package_profile(custom_packages)
        else:
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
    endpoint_diagnostics = build_profile_endpoint_diagnostics(profile)
    logger.info(endpoint_diagnostics["detail"], status="catalog_loaded")
    if endpoint_diagnostics["issues"]:
        logger.warning(
            "Foram encontrados sinais de risco nos endpoints/arquivos do catalogo selecionado. "
            + " | ".join(endpoint_diagnostics["issues"][:4]),
            status="catalog_endpoint_warning",
        )
    connectivity_diagnostics = probe_catalog_endpoint_connectivity(profile)
    logger.info(connectivity_diagnostics["detail"], status="catalog_loaded")
    if connectivity_diagnostics["issues"]:
        logger.warning(
            "Foram encontrados sinais de bloqueio/rede ao sondar os endpoints oficiais do catalogo. "
            + " | ".join(connectivity_diagnostics["issues"][:4]),
            status="catalog_connectivity_warning",
        )
    return profile
