import streamlit as st
#import altair

from family_tree.statistics import get_engine, fetch_folders

PGHOST = st.secrets['PGHOST']
PGPORT = st.secrets.get('PGPORT', '5432')
PGDBNAME = st.secrets['PGDATABASE']
PGUSER = st.secrets['PGUSER']
PGPASSWORD = st.secrets['PGPASSWORD']

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

st.title('Franzonello Family 2025 YIR WIP')

folder_values = fetch_folders(engine, 2025)
diplay_values = folder_values[['full_name', 'video_count']].set_index('full_name')
st.bar_chart(diplay_values)