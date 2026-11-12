"""Coach privé, à lancer en local uniquement : `uv run streamlit run coach_app.py`."""

import streamlit as st

st.set_page_config(
    page_title="Coach · Napoly Game",
    page_icon=":material/sports:",
    layout="wide",
    initial_sidebar_state="expanded",
)

from app import theme  # noqa: E402
from app.state import get_analysis  # noqa: E402
from app.views import coach  # noqa: E402
from mpg.loader import DataSchemaError  # noqa: E402

theme.inject_css()
st.logo("assets/logo.svg", size="large", icon_image="assets/icon.svg")

try:
    analysis = get_analysis()
except DataSchemaError as exc:
    st.error(f"Les fichiers de `data/` ne sont pas au format attendu : {exc}")
    st.stop()

coach.render(analysis)
