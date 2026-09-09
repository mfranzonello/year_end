import streamlit as st

from pages.general import set_sidebar, existing_pages, allow_page

set_sidebar()

st.title(f'Family Fun Times')
st.write(f'Choose your adventure!')

viewable_ages = [p for p in existing_pages if allow_page(p[-1])]
cols = st.columns(len(viewable_ages))
for col, (page_py, page_name, page_gate) in zip(cols, viewable_ages):
    with col:
        if st.button(page_name):
            st.switch_page(page_py)