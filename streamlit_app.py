if src == "Dossier local (data_*)":
        # 1) Liste tous les dossiers data_* + "data" s'il existe
        data_dirs = find_data_dirs(APP_DIR)  # [Path(.../data), Path(.../data_noob), Path(.../data_xxx), ...]
        labels = [d.name for d in data_dirs]

        # 2) Gestion du défaut (dernier choix ou DEFAULT_YAML_DIR)
        prev_dir = st.session_state.get("data_dir")
        default_label = None
        if prev_dir:
            prev_name = Path(prev_dir).name
            if prev_name in labels:
                default_label = prev_name
        if default_label is None and DEFAULT_YAML_DIR.exists():
            default_label = DEFAULT_YAML_DIR.name

        # 3) Radios : un bouton par dossier + option "Autre"
        options = labels + ["⟶ Autre (saisir chemin)"]
        try:
            default_index = options.index(default_label) if default_label else 0
        except ValueError:
            default_index = 0

        choice = st.radio(
            "Choisis le dossier de données YAML",
            options=options,
            index=min(default_index, len(options) - 1),
        )

        # 4) Résolution du dossier choisi
        if choice == "⟶ Autre (saisir chemin)":
            custom = st.text_input(
                "Chemin absolu/relatif du dossier YAML",
                value=prev_dir or str(DEFAULT_YAML_DIR),
            )
            chosen_dir = Path(custom).expanduser()
        else:
            chosen_dir = data_dirs[labels.index(choice)]

        # 5) Mémorise et charge le corpus
        st.session_state["data_dir"] = str(chosen_dir)

        if chosen_dir.exists() and chosen_dir.is_dir():
            corpus = load_yaml_dir(chosen_dir)
            st.session_state["corpus"] = corpus  # dispo pour l’onglet Aperçu
            st.success(
                f"{len(corpus['units'])} unités et {len(corpus['stratagems'])} stratagèmes chargés depuis `{chosen_dir.name}/`."
            )
        else:
            st.warning(
                "Dossier introuvable. Corrige le chemin ou choisis un dossier existant."
            )