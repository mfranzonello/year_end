from uuid import UUID
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

import streamlit as st

from database.db import get_engine
from database.db_family import fetch_person_information, fetch_animal_information
from database.db_display import fetch_member_summary
from family_tree.cloudy import get_image_url, upload_image, configure_cloud
from pages.general import set_sidebar
from charting.stats_member import fill_in_bio

PGHOST = st.secrets['postgresql']['host']
PGPORT = st.secrets['postgresql'].get('port', '5432')
PGDBNAME = st.secrets['postgresql']['database']
PGUSER = st.secrets['postgresql']['user']
PGPASSWORD = st.secrets['postgresql']['password']

CLOUDINARY_CLOUD = st.secrets['cloudinary']['cloud_name']
CLOUDINARY_KEY = st.secrets['cloudinary']['api_key']
CLOUDINARY_SECRET = st.secrets['cloudinary']['api_secret']
configure_cloud(CLOUDINARY_CLOUD, CLOUDINARY_KEY, CLOUDINARY_SECRET)

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

SCHEMA_NAME = 'dashboard'  # demo if not logged in

# set up page
set_sidebar()
st.set_page_config(page_title='Franzonello Family YIR Appearances',
                   layout='wide')

members = fetch_member_summary(engine, schema_name=SCHEMA_NAME).sort_values('sort_order')
known_index = members.index[members['member_id'] == st.session_state.get('member_id')]
index = int(known_index[0]) if len(known_index) else None
member_id = st.selectbox('Select Family Member', members['member_id'],
                         format_func=lambda x: members[members['member_id'] == x]['full_name'].iloc[0],
                         width=400,
                         index=None)

if member_id is not None:
    st.session_state['member_id'] = member_id
    fill_in_bio(engine, member_id, members, CLOUDINARY_CLOUD)