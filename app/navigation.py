import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

VOLET_KEY = "volet"
_SIGNATURE_KEY = "_volet_signature"
_PAGES_KEY = "_pages_registry"


def _page_signature(options: dict[str, str]) -> tuple[str, tuple[str, ...]]:
    ctx = get_script_run_ctx()
    return (ctx.page_script_hash if ctx is not None else "", tuple(options))


def _sync_url(chosen: str, first: str) -> None:
    if chosen == first:
        if VOLET_KEY in st.query_params:
            del st.query_params[VOLET_KEY]
    elif st.query_params.get(VOLET_KEY) != chosen:
        st.query_params[VOLET_KEY] = chosen


def volet_selector(options: dict[str, str]) -> str:
    """Affiche le choix du volet et renvoie sa clé.

    Le widget n'est pas lié à l'adresse (`bind="query-params"`) : Streamlit y écrirait le libellé affiché
    et non la clé. L'adresse est donc lue au premier affichage de chaque page, puis réécrite à chaque choix.
    """
    if not options:
        raise ValueError("volet_selector exige au moins un volet.")
    first = next(iter(options))
    signature = _page_signature(options)
    if st.session_state.get(_SIGNATURE_KEY) != signature:
        st.session_state[_SIGNATURE_KEY] = signature
        requested = st.query_params.get(VOLET_KEY)
        st.session_state[VOLET_KEY] = requested if requested in options else first
    elif st.session_state.get(VOLET_KEY) not in options:
        st.session_state[VOLET_KEY] = first
    chosen = st.segmented_control(
        "Volet",
        list(options),
        format_func=options.__getitem__,
        key=VOLET_KEY,
        required=True,
        label_visibility="collapsed",
    )
    _sync_url(chosen, first)
    return chosen


def register(pages: dict[str, st.Page]) -> None:
    st.session_state[_PAGES_KEY] = dict(pages)


def page_link(key: str, label: str, icon: str | None = None, volet: str | None = None) -> None:
    page = st.session_state.get(_PAGES_KEY, {}).get(key)
    if page is None:
        return
    query_params = {VOLET_KEY: volet} if volet else None
    st.page_link(page, label=label, icon=icon, query_params=query_params)
