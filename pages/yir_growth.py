import streamlit as st

from database.db import get_engine
from database.db_project import fetch_years_summary
from family_tree.charts import growth_charts
from display import set_sidebar

PGHOST = st.secrets['postgresql']['host']
PGPORT = st.secrets['postgresql'].get('port', '5432')
PGDBNAME = st.secrets['postgresql']['database']
PGUSER = st.secrets['postgresql']['user']
PGPASSWORD = st.secrets['postgresql']['password']

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

# set up page
set_sidebar()
st.set_page_config(page_title='Franzonello Family YIR Growth',
                   layout='wide')
st.title(f'Franzonello YIR Growth')

year_values = fetch_years_summary(engine)

charts = growth_charts(year_values)

for chart in charts:
    st.altair_chart(chart, use_container_width=True)