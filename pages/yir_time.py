from uuid import UUID
from datetime import date, timedelta

import streamlit as st

from database.db import get_engine
from database.db_display import fetch_member_information, fetch_relationships_summary
from database.db_adobe import fetch_timeline_years, fetch_actor_spans, fetch_markers
from database.db_family import fetch_founder
from charting.charts import timeline_chart
from charting.general import set_sidebar, plot_altair_chart
from family_tree.ancestry import build_tree_dashboard

PGHOST = st.secrets['postgresql']['host']
PGPORT = st.secrets['postgresql'].get('port', '5432')
PGDBNAME = st.secrets['postgresql']['database']
PGUSER = st.secrets['postgresql']['user']
PGPASSWORD = st.secrets['postgresql']['password']

CLOUDINARY_CLOUD = st.secrets['cloudinary']['cloud_name']

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

DASHBOARD_SCHEMA = 'dashboard' # demo if not logged in

# set up page
set_sidebar()
st.set_page_config(page_title='Franzonello Family YIR Appearances',
                   layout='wide')
years = fetch_timeline_years(engine)
year:int = st.selectbox('Year to Review', years, len(years) - 1, width=100)
st.title(f'Franzonello YIR {year}')

cut_date = date(year + 1, 1, 1) - timedelta(days=1)


members_df = fetch_member_information(engine, schema_name=DASHBOARD_SCHEMA, cut_date=cut_date)
relationships_df = fetch_relationships_summary(engine, schema_name=DASHBOARD_SCHEMA)
founder_id = fetch_founder(engine, schema_name=DASHBOARD_SCHEMA)


## pull in member and relationship info and send to build tree
relatives = build_tree_dashboard(members_df, relationships_df, founder_id,
                                 include_animals=True, cut_date=cut_date, include_deceased=False)
relative_ids = relatives['member_id'].tolist()

##member_info = fetch_member_information(engine, cut_date=cut_date)
actor_spans = fetch_actor_spans(engine, year)
actor_spans = (actor_spans
               .merge(relatives[['member_id', 'generation', 'in-law']], how='outer', on='member_id')
               .merge(members_df, on='member_id') ##member_info
               )

actor_spans.loc[~actor_spans['member_id'].isin(relative_ids), 'clan_id'] = UUID(int=0) # can use ['generation'].isna() too
actor_spans['in-law'] = actor_spans['in-law'].fillna(False)

markers = fetch_markers(engine, year)

# gantt chart of appearances
chart = timeline_chart(actor_spans, markers, cloud_name=CLOUDINARY_CLOUD)
plot_altair_chart(chart)