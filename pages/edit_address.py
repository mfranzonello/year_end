from uuid import UUID
from datetime import date

import streamlit as st

from database.db import get_engine
from database.db_display import fetch_member_summary
from database.db_messaging import (
    fetch_addresses, fetch_address_moves, fetch_homeless,
    insert_address, insert_address_move,
    update_address, update_address_move,
    remove_address, remove_address_move
    )
from pages.streamlit_auth import get_database_credentials, get_cloud_credentials
from pages.general import set_sidebar, get_hash_funcs, get_member_name_display, get_value
from charting.stats_member import plot_map

engine = get_engine(*get_database_credentials())

# set up page
set_sidebar()
st.set_page_config(page_title='Add and Edit Family Members',
                   layout='wide')

members = fetch_member_summary(engine)
persons = members[members['member_type'] == 'person']
homeless = fetch_homeless(engine)

def list_homeless():
    with st.expander('Show Homeless', type='compact', width=300):
        for _, (person_id, ) in homeless[['person_id']].iterrows():
            st.write(f':gray-background[{get_member_name_display(members, person_id)}]')

@st.dialog('Add Address')
def add_address():
    with st.container():
        cols = st.columns(2)
        with cols[0]:
            st.text_input('Address Name', key=f'address_name_new')
        with cols[1]:
            st.number_input('Zip Code', min_value=0, max_value=99999, key=f'zip_code_new')
    st.divider()
    with st.container(horizontal_alignment='right'):
        if st.button('Add Address'):
            keys = ['address_name', 'zip_code']
            information = {k: get_value(st.session_state[f'{k}_new']) for k in keys}
            insert_address(engine, information)
            st.rerun()

@st.dialog('Edit Address')
def edit_address(address_id, address_name, zip_code, i):
    with st.container():
        cols = st.columns([2, 1])
        with cols[0]:
            st.text_input('Address Name', value=address_name, key=f'address_name_{i}')
        with cols[1]:
            st.number_input('Zip Code', min_value=0, max_value=99999, value=int(zip_code), key=f'zip_code_{i}')
    st.divider()
    with st.container(horizontal_alignment='right'):
        if st.button('Update Address'):
            keys = ['address_name', 'zip_code']
            information = {'address_id': address_id}
            information.update({k: get_value(st.session_state[f'{k}_{i}']) for k in keys})
            update_address(engine, information)
            st.rerun()
        if st.button('Delete Address'):
            remove_address(engine, address_id=address_id)
            st.rerun()

@st.dialog('Add Move')
def add_address_move(address_id, exclude_ids):
    with st.container():
        cols = st.columns([2, 1])
        with cols[0]:
            possibles = persons[~persons['member_id'].isin(exclude_ids)]
            st.selectbox('Person', options=possibles['member_id'].to_list(), 
                         format_func=lambda x: get_member_name_display(members, x),
                         index=None,
                         key='person_id_new')
        with cols[1]:
            st.date_input('Start date', min_value=date.min, max_value=date.max, value=None,
                          key='start_date_new')
    st.divider()
    with st.container(horizontal_alignment='right'):
        if st.button('Add Move'):
            keys = ['person_id', 'start_date']
            information = {'address_id': address_id}
            information.update({k: get_value(st.session_state[f'{k}_new']) for k in keys})
            insert_address_move(engine, information)
            st.rerun()

@st.dialog('Edit Move')
def edit_address_move(move_id, person_id, start_date, i, j):
    with st.container():
        cols = st.columns([2, 1])
        with cols[0]:
            st.write(get_member_name_display(members, person_id))
        with cols[1]:
            st.date_input('start date', value=start_date, min_value=date.min, max_value=date.max,
                            key=f'start_date_{i}_{j}')
    st.divider()
    with st.container(horizontal_alignment='right'):
        if st.button('Update Move'):
            keys = ['start_date']
            information = {'move_id': move_id}
            information.update({k: get_value(st.session_state[f'{k}_{i}_{j}']) for k in keys})
            insert_address_move(engine, information)
            st.rerun()
        if st.button('Delete Move'):
            remove_address_move(engine, move_id=move_id)
            st.rerun()

addresses = fetch_addresses(engine).sort_values(by='address_name')
address_moves = fetch_address_moves(engine).sort_values(by=['address_name', 'start_date'])


list_homeless()

if st.button('Add Address', type='primary', key='add_address'):
    add_address()

for i, (address_id, address_name, zip_code) in addresses.iterrows():
    address_moves_i = address_moves[address_moves['address_id'] == address_id].reset_index(drop=True)
    with st.container(border=True):
        cols = st.columns(2)
        with cols[0]:
            with st.container():
                s_cols = st.columns([1, 3])
                with s_cols[0]:
                    if st.button('Edit Address', type='primary', key=f'edit_address_{i}'):
                        edit_address(address_id, address_name, zip_code, i)
                with s_cols[1]:
                    st.markdown(f'Address name: **{address_name}**')

            with st.expander('Location details'):
                st.markdown(f'Zip code: **{zip_code}**')
                plot_map(zip_code, width=500)

        with cols[1]:
            if st.button('Add Move', type='primary', key=f'add_move_{i}'):
                excluded_ids = address_moves_i['person_id'].to_list()
                add_address_move(address_id, excluded_ids)
            with st.expander('Residents'):
                for j, (address_id, address_name, zip_code, move_id, person_id, start_date) in address_moves_i.iterrows():
                    with st.container(border=True):
                        s_cols = st.columns([2, 1, 1])
                        with s_cols[0]:
                            st.write('Addressee:')
                            st.markdown(f'**{get_member_name_display(members, person_id)}**')
                        with s_cols[1]:
                            st.write('Start date:')
                            st.markdown(f'**{start_date}**')
                        with s_cols[2]:
                            if st.button('Edit Move', type='primary', key=f'edit_move_{i}_{j}'):
                                edit_address_move(move_id, person_id, start_date, i, j)
