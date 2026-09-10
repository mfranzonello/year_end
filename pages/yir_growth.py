import streamlit as st

from database.db import get_engine
from database.db_display import fetch_resolution_order
from database.db_project import fetch_years_summary
from pages.streamlit_auth import get_database_credentials
from pages.general import set_sidebar, get_hash_funcs, plot_altair_chart
from charting.charts_yir import growth_charts

engine = get_engine(*get_database_credentials())

# set up page
set_sidebar()
st.set_page_config(page_title='Family YIR Growth',
                   layout='wide')
st.title(f'Year In Review Growth')

@st.cache_data(ttl='15m', hash_funcs=get_hash_funcs())
def get_years_summary(engine):
    return fetch_years_summary(engine)

year_values = get_years_summary(engine)

resolution_order = fetch_resolution_order(engine)
charts = growth_charts(year_values, resolution_order)

for chart in charts:
    plot_altair_chart(chart)