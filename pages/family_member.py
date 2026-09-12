from datetime import date

import streamlit as st

from database.db import get_engine
from database.db_family import fetch_person_information, fetch_animal_information
from database.db_display import fetch_member_summary
from pages.streamlit_auth import get_database_credentials, get_cloud_credentials
from pages.general import set_sidebar, get_hash_funcs, get_member_name_display
from charting.cloudy import configure_cloud
from charting.stats_member import fill_image, fill_personal, fill_lineage

engine = get_engine(*get_database_credentials())
cloud = configure_cloud(*get_cloud_credentials())

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

# initialize / validate the selection
if 'member_id' not in st.session_state:
    st.session_state['member_id'] = None

if 'member_select' not in st.session_state:
    st.session_state['member_select'] = st.session_state['member_id']

def select_member():
    st.session_state['member_id'] = st.session_state.get('member_select')

st.selectbox(
    'Select Member',
    members['member_id'], placeholder='Choose a family member to view',
    format_func=lambda x: get_member_name_display(members, x), index=None,
    width=350,
    key='member_select', on_change=select_member,
    )

member_id = st.session_state.member_id

def get_basics(members, member_id):
    sex = information['sex'].iloc[0]

    birth_date = information['birth_date'].iloc[0]
    birth_date_precision = information['birth_date_precision'].iloc[0]
    is_future = (birth_date is not None and birth_date > date.today()) or (birth_date_precision == 'future')

    death_date = information['death_date'].iloc[0]
    death_date_precision = information['death_date_precision'].iloc[0]
    is_deceased = (death_date is not None and death_date <= date.today()) or (death_date_precision == 'past')

    return sex, is_future, is_deceased

if member_id is not None:
    member_type = members[members['member_id'] == member_id]['member_type'].iloc[0]
    information = member_informations[member_type][member_informations[member_type]['member_id'] == member_id]

    sex, is_future, is_deceased = get_basics(members, member_id)

    cols = st.columns(3)
    with cols[0]:
        fill_image(engine, cloud, members, member_type, member_id)

    with cols[1]:
        fill_personal(information, member_type, sex, is_future, is_deceased)

    with cols[2]:
        fill_lineage(information, members, member_type, sex, is_future)