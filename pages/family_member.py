from uuid import UUID
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

import streamlit as st

from database.db import get_engine
from database.db_family import fetch_person_information, fetch_animal_information
from database.db_display import fetch_member_summary
from family_tree.cloudy import configure_cloud
from pages.general import set_sidebar, get_hash_funcs
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

# set up page
set_sidebar()
st.set_page_config(page_title='Family Members',
                   layout='wide')

@st.cache_data(hash_funcs=get_hash_funcs())
def get_member_data(engine):
    members = fetch_member_summary(engine).sort_values('sort_order')
    person_information = fetch_person_information(engine)

    animal_information = fetch_animal_information(engine)
    member_informations = {'person': person_information,
                           'animal': animal_information}
    return members, member_informations

members, member_informations = get_member_data(engine)
known_index = members.index[members['member_id'] == st.session_state.get('member_id')]

index = int(known_index[0]) if len(known_index) else None
member_id = st.selectbox('Select Member', members['member_id'],
                         placeholder='Choose a family member to view',
                         format_func=lambda x: members[members['member_id'] == x]['full_name'].iloc[0],
                         width=350,
                         index=index)

st.session_state['member_id'] = member_id
if member_id is not None:
    member_type = members[members['member_id'] == member_id]['member_type'].iloc[0]
    information = member_informations[member_type][member_informations[member_type]['member_id'] == member_id]
    list_id = fill_in_bio(engine, CLOUDINARY_CLOUD, members, information, member_type, member_id)