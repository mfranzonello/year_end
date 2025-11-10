import streamlit as st
import os
for key, value in st.secrets.items():
    if isinstance(value, dict):
        # flatten nested secrets (like st.secrets["neon"]["user"])
        for subkey, subval in value.items():
            env_key = f'{key.upper()}_{subkey.upper()}'
            os.environ[env_key] = str(subval)
    else:
        os.environ[key.upper()] = str(value)

#import altair

from family_tree.statistics import get_engine, fetch_folders

st.secrets

engine = get_engine()

st.title('Franzonello Family 2025 YIR WIP')

folder_values = fetch_folders(engine, 2025)
diplay_values = folder_values[['full_name', 'video_count']].set_index('full_name')
st.bar_chart(diplay_values)