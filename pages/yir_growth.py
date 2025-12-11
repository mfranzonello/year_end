import streamlit as st

from database.db import get_engine
from database.db_display import fetch_resolution_order
from database.db_project import fetch_years_summary
from charting.charts import growth_charts
from charting.general import set_sidebar, plot_altair_chart

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

resolution_order = fetch_resolution_order(engine)
charts = growth_charts(year_values, resolution_order)

for chart in charts:
    plot_altair_chart(chart)