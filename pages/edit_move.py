from uuid import UUID
from datetime import date

import streamlit as st

from database.db import get_engine
from database.db_display import fetch_member_summary
from database.db_messaging import (
    fetch_member_moves, fetch_homeless, fetch_addresses,
    insert_address_move, update_address_move, remove_address_move
    )
from pages.streamlit_auth import get_database_credentials
from pages.general import set_sidebar, get_hash_funcs, get_member_name_display, get_value, get_index
##from charting.stats_member import plot_map

engine = get_engine(*get_database_credentials())

# set up page
set_sidebar()
st.set_page_config(page_title='Add and Edit Family Members',
                   layout='wide')

members = fetch_member_summary(engine)
persons = members[members['member_type'] == 'person']
homeless = fetch_homeless(engine)
addresses = fetch_addresses(engine)
member_moves = fetch_member_moves(engine) ##.sort_values(by=['address_name', 'move_date'])


def get_address_name_display(address_id: int, include_zip: bool = False):
    address_name, zip_code = addresses[addresses['address_id'] == address_id][['address_name',
                                                                               'zip_code']].iloc[0]
    if include_zip:
        address_name += f' ({zip_code})'
    return address_name

def list_homeless():
    with st.expander('Show Homeless', type='compact', width=300):
        for _, (person_id, ) in homeless[['person_id']].iterrows():
            st.write(f':gray-background[{get_member_name_display(members, person_id)}]')

def get_member_color(member_type):
    match member_type:
        case 'person':
            return 'blue'
        case 'animal':
            return 'red'

@st.dialog('Add Move')
def add_move(person_id):
    st.write(f'Add new address move for :blue-background[{get_member_name_display(members, person_id)}]')
    with st.container():
        cols = st.columns([2, 1])
        with cols[0]:
            st.selectbox('Address Name', options=addresses['address_id'].to_list(), 
                         format_func=lambda x: get_address_name_display(x),
                         index=None,
                         key='address_id_new')
        with cols[1]:
            st.date_input('Move date', min_value=date.min, max_value=date.max, value=None,
                          key='move_date_new')
    st.divider()
    with st.container(horizontal_alignment='right'):
        if st.button('Add Move'):
            keys = ['address_id', 'move_date']
            information = {'person_id': person_id}
            information.update({k: get_value(st.session_state[f'{k}_new']) for k in keys})
            insert_address_move(engine, information)
            st.rerun()

list_homeless()

@st.dialog('Edit Move')
def edit_move(move_id, address_id, person_id, move_date, i, j):
    st.write(f'Edit address move for :blue-background[{get_member_name_display(members, person_id)}]')
    with st.container():
        cols = st.columns([2, 1])
        with cols[0]:
            st.selectbox('Address name', options=addresses['address_id'].to_list(), 
                         format_func=lambda x: get_address_name_display(x, include_zip=True),
                         index=get_index(addresses['address_id'].to_list(), address_id),
                         key='address_id_new')
        with cols[1]:
            st.date_input('Move date', value=move_date, min_value=date.min, max_value=date.max,
                            key=f'move_date_{i}_{j}')
    st.divider()
    with st.container(horizontal_alignment='right'):
        if st.button('Update Move'):
            keys = ['move_date', 'address_id']
            information = {'move_id': move_id}
            information.update({k: get_value(st.session_state[f'{k}_{i}_{j}']) for k in keys})
            insert_address_move(engine, information)
            st.rerun()
        if st.button('Delete Move'):
            remove_address_move(engine, move_id=move_id)
            st.rerun()

for i, (member_id, member_type, moves) in member_moves.iterrows():
    with st.container(border=True):
        cols = st.columns([4, 2, 15])
        with cols[0]:
            st.write(f':{get_member_color(member_type)}-background[{get_member_name_display(members, member_id)}]')
        with cols[1]:
            if member_type == 'person':
                if st.button('Add Move', type='primary', key=f'add_move_{i}'):
                    add_move(member_id)
        with cols[2]:
            if moves:
                with st.expander('Residences'):
                    for j, move in enumerate(moves):
                        s_cols = st.columns([6, 3, 4, 2])
                        with s_cols[0]:
                            st.markdown(f'**Address**: {move["address_name"]}')
                        with s_cols[1]:
                            st.markdown(f'**Zip code**: {move["zip_code"]}')
                        with s_cols[2]:
                            st.markdown(f'**Move date**: {move["move_date"]}')
                        with s_cols[3]:
                            if member_type == 'person':
                                if st.button('Edit Move', key=f'edit_move_{i}_{j}'):
                                    edit_move(move['move_id'], move['address_id'], member_id, move['move_date'], i, j)