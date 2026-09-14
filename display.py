from math import e
import streamlit as st

from pages.general import set_sidebar, pages, allow_page, get_link

set_sidebar()

st.title(f'Family Fun Times')
st.write(f'Choose your adventure!')

for grouping in pages:
    allowable_pages = [page for page in pages[grouping] if allow_page(page)]
    if len(allowable_pages):
        with st.container(border=True):
            cols = st.columns(len(allowable_pages))
            for p, page in enumerate(allowable_pages):
                with cols[p]:
                    with st.container(horizontal_alignment='center'):
                        if st.button(page['label'], type='primary', width="stretch"):
                            st.switch_page(get_link(page))