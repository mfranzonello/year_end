from math import e
import streamlit as st

from pages.general import set_sidebar, pages, allow_page, get_link

set_sidebar()

st.title(f'Family Fun Times')
st.write(f'Choose your adventure!')

for grouping in pages:
    with st.container(horizontal_alignment='center'):
        allowable_pages = [page for page in pages[grouping] if allow_page(page)]
        cols = st.columns(len(allowable_pages))
        for p, page in enumerate(allowable_pages):
            with cols[p]:
                if st.button(page['label']):
                    st.switch_page(get_link(page))