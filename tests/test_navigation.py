from streamlit.testing.v1 import AppTest


def _selector_app() -> None:
    import streamlit as st

    from app.navigation import volet_selector

    chosen = volet_selector({"classement": "Classement", "chance": "Chance", "forme": "Forme"})
    st.write(f"volet={chosen}")


def _single_app() -> None:
    import streamlit as st

    from app.navigation import volet_selector

    chosen = volet_selector({"film": "Le film"})
    st.write(f"volet={chosen}")


def _two_pages_app() -> None:
    import streamlit as st

    from app.navigation import volet_selector

    pages = {
        "a": {"classement": "Classement", "chance": "Chance", "forme": "Forme"},
        "b": {"resume": "Résumé", "forme": "Forme"},
    }
    chosen = volet_selector(pages[st.query_params.get("page", "a")])
    st.write(f"volet={chosen}")


def _page_link_app() -> None:
    import streamlit as st

    from app.navigation import page_link

    page_link("inconnue", "Aller ailleurs", icon="➡️")
    st.write("fin")


def _run(app, query: str | None = None, session: dict | None = None) -> AppTest:
    at = AppTest.from_function(app)
    for name, value in (session or {}).items():
        at.session_state[name] = value
    if query is not None:
        at.query_params["volet"] = query
    return at.run()


def _shown(at: AppTest) -> str:
    return next(m.value for m in at.markdown if m.value.startswith("volet="))


def test_premier_volet_par_defaut():
    at = _run(_selector_app)
    assert not at.exception
    assert _shown(at) == "volet=classement"
    assert not at.warning
    assert "volet" not in at.query_params


def test_volet_valide_de_l_adresse_respecte():
    at = _run(_selector_app, query="chance")
    assert not at.exception
    assert _shown(at) == "volet=chance"
    assert at.query_params["volet"] == "chance"


def test_volet_invalide_retombe_sur_le_premier():
    at = _run(_selector_app, query="nimporte")
    assert not at.exception
    assert not at.warning
    assert _shown(at) == "volet=classement"
    assert "volet" not in at.query_params


def test_valeur_restee_en_session_d_une_autre_page():
    at = _run(_selector_app, session={"volet": "resume", "_volet_signature": ("", ("resume", "chance"))})
    assert not at.exception
    assert not at.warning
    assert _shown(at) == "volet=classement"


def test_changement_de_page_ignore_la_valeur_de_la_page_precedente():
    at = AppTest.from_function(_two_pages_app)
    at.query_params["volet"] = "chance"
    at.run()
    assert _shown(at) == "volet=chance"
    at.query_params["page"] = "b"
    at.run()
    assert not at.exception
    assert not at.warning
    assert _shown(at) == "volet=resume"
    at.query_params["volet"] = "forme"
    at.query_params["page"] = "a"
    at.run()
    assert _shown(at) == "volet=forme"


def test_choix_utilisateur_conserve_et_ecrit_dans_l_adresse():
    at = _run(_selector_app)
    at.get("button_group")[0].set_value("forme").run()
    assert not at.exception
    assert _shown(at) == "volet=forme"
    assert at.query_params["volet"] == "forme"
    at.get("button_group")[0].set_value("classement").run()
    assert _shown(at) == "volet=classement"
    assert "volet" not in at.query_params


def test_un_seul_volet_n_affiche_pas_de_selecteur():
    at = _run(_single_app)
    assert not at.exception
    assert _shown(at) == "volet=film"
    assert not at.get("button_group")
    assert "volet" not in at.query_params


def test_un_seul_volet_nettoie_l_adresse():
    at = _run(_single_app, query="fiabilite", session={"volet": "fiabilite"})
    assert not at.exception
    assert _shown(at) == "volet=film"
    assert "volet" not in at.query_params


def test_retour_a_plusieurs_volets_apres_un_seul():
    def app() -> None:
        import streamlit as st

        from app.navigation import volet_selector

        pages = {"seul": {"film": "Le film"}, "multi": {"a": "A", "b": "B"}}
        st.write(f"volet={volet_selector(pages[st.query_params.get('page', 'seul')])}")

    at = AppTest.from_function(app).run()
    assert _shown(at) == "volet=film"
    at.query_params["page"] = "multi"
    at.run()
    assert not at.exception
    assert _shown(at) == "volet=a"
    assert at.get("button_group")[0].value == "a"


def test_options_vides_refusees():
    def app() -> None:
        from app.navigation import volet_selector

        volet_selector({})

    at = AppTest.from_function(app).run()
    assert at.exception
    assert "au moins un volet" in at.exception[0].value


def test_page_link_sans_registre_ne_fait_rien():
    at = _run(_page_link_app)
    assert not at.exception
    assert [m.value for m in at.markdown] == ["fin"]


def test_page_link_cle_inconnue_avec_registre():
    def app() -> None:
        import streamlit as st

        from app.navigation import page_link, register

        register({})
        page_link("x", "Lien", volet="chance")
        st.write("fin")

    at = AppTest.from_function(app).run()
    assert not at.exception


def test_volet_title_echappe_le_titre_et_garde_le_sous_titre_html(monkeypatch):
    from app import components

    rendus: list[str] = []
    monkeypatch.setattr(components.st, "html", rendus.append)
    components.volet_title("A <b>&</b> B", "Texte <em>mis en avant</em>")
    components.volet_title("Seul")
    assert 'class="title">A &lt;b&gt;&amp;&lt;/b&gt; B</div>' in rendus[0]
    assert '<div class="subtitle">Texte <em>mis en avant</em></div>' in rendus[0]
    assert "subtitle" not in rendus[1]
