from uuid import UUID
from datetime import date
import streamlit as st

from database.db import get_engine
from database.db_family import (
    fetch_persons, fetch_animals, fetch_parents, fetch_pets, fetch_partners,
    update_person, update_animal, update_parents, update_pets, update_partners,
    insert_person, insert_animal, insert_parents, insert_pets, insert_partners,
    remove_person, remove_animal, remove_parents, remove_pets, remove_partners)
from database.db_display import fetch_member_summary
from pages.streamlit_auth import get_database_credentials, get_cloud_credentials
from pages.general import set_sidebar, get_hash_funcs, get_member_name_display, get_value
from charting.cloudy import configure_cloud, get_image_url, upload_image, get_version

engine = get_engine(*get_database_credentials())
cloud = configure_cloud(*get_cloud_credentials())

# set up page
set_sidebar()
st.set_page_config(page_title='Add and Edit Family Members',
                   layout='wide')

new_uuid = f'{"X"*8}-{"X"*4}-{"X"*4}-{"X"*8}-{"X"*12}'
prefixes = ['Dr', 'Fr']
sexes = {'m': 'male', 'f': 'female'}
precisions = ['day', 'month', 'year', 'past', 'future']
specieses = ['cat', 'dog', 'bird', 'rabbit']
relation_types = {'person': ['biological', 'adoptive', 'step'],
                  'animal': ['adoptive', 'shared']}
partner_types = ['marriage', 'civil']
connect_types = ['friends']
union_types = partner_types + connect_types

def get_index(values, value):
    if value in values:
        return values.index(value)

@st.cache_data(hash_funcs=get_hash_funcs())
def get_member_data(engine):
    members = fetch_member_summary(engine).sort_values('sort_order')
    return members

def get_member_type(members, member_id):
    return members[members['member_id'] == member_id]['member_type'].iloc[0]

def get_last_name_display(x):
    match x:
        case True:
            return 'this'
        case False:
            return 'theirs'
        case _:
            return 'neither'

def check_date_precisions(date_value, date_precision):
    return ((date_value is None and date_precision in ['past', 'future']) or
            (date_value is not None and date_precision in ['day', 'month', 'year']))

# initialize / validate the selection
if 'member_id' not in st.session_state:
    st.session_state['member_id'] = None

if 'member_select' not in st.session_state:
    st.session_state['member_select'] = st.session_state.member_id

def select_member():
    st.session_state.member_id = st.session_state.member_select

@st.dialog('Add New Person', width='medium')
def add_new_person():
    with st.form('add_new_person'):
        st.markdown(f'person_id: :orange-badge[{new_uuid}]')
        cols = st.columns(2)
        with cols[0]:
            st.selectbox('Prefix', options=['Dr', 'Fr'], index=None, width=100, key='prefix_new')
            st.text_input('First Name', width=300, key='first_name_new')
            st.text_input('Nickname', width=300, key='nick_name_new') 
            st.text_input('Middle Names', width=300, key='middle_names_new')
            st.checkbox('Uses Middle', key='uses_middle_new')
            st.text_input('Last Name', width=300, key='last_name_new')
            st.number_input('Suffix', value=None, min_value=1, max_value=None, width=100,
                                     key='suffix_new')

        with cols[1]:
            st.selectbox('Sex', options=sexes.keys(), width=100,
                         format_func=lambda x: sexes.get(x, 'Unknown'),
                         index=None,
                         key='sex_new')
                    
            s_cols = st.columns([2, 1])
            with s_cols[0]:
                st.date_input('Birth Date', value=None, min_value=date.min, max_value=date.max,
                              width=200, key='birth_date_new')
            with s_cols[1]:
                st.selectbox('Precision', options=precisions, index=None,
                             key='birth_date_precision_new')

            s_cols = st.columns([2, 1])
            with s_cols[0]:
                st.date_input('Death Date', value=None, min_value=date.min, max_value=date.max,
                             width=200, key='death_date_new')
            with s_cols[1]:
                st.selectbox('Precision', options=precisions, index=None,
                             key='death_date_precision_new')

            st.divider()
            st.text_area('Notes', key='notes_new')


        st.divider()
        with st.container(horizontal_alignment='right'):
            if st.form_submit_button('Add New Person', type='primary', key='add_new_person'):
                keys = ['first_name', 'middle_names', 'last_name', 'nick_name', 'uses_middle',
                        'prefix', 'suffix', 'sex',
                        'birth_date', 'birth_date_precision', 'death_date', 'death_date_precision',
                        'notes']
                information = {k: get_value(st.session_state[f'{k}_new']) for k in keys}
                st.session_state['member_id'] = insert_person(engine, information)
                get_member_data.clear()
                st.rerun()

@st.dialog('Add New Animal', width='medium')
def add_new_animal():
    with st.form('add_new_animal'):
        st.markdown(f'animal_id: :orange-badge[{new_uuid}]')
        cols = st.columns(2)
        with cols[0]:
            st.text_input('First Name', width=300, key='first_name_new')
            st.text_input('Nickname', width=300, key='nick_name_new')
            st.text_input('Middle Names', width=300, key='middle_names_new')
                    
        with cols[1]:
            st.selectbox('Sex', options=sexes.keys(), width=100,
                         format_func=lambda x: sexes.get(x, 'Unknown'),
                         index=None,
                         key='sex_new')
            st.selectbox('Species', options=specieses, width=200,
                         index=None,
                         key='species_new')

            s_cols = st.columns([2, 1])
            with s_cols[0]:
                st.date_input('Birth Date', value=None, min_value=date.min, max_value=date.max,
                             width=200, key='birth_date_new')
            with s_cols[1]:
                st.selectbox('Precision', options=precisions, index=None,
                             key='birth_date_precision_new')

            s_cols = st.columns([2, 1])
            with s_cols[0]:
                st.date_input('Death Date', value=None, min_value=date.min, max_value=date.max,
                             width=200, key='death_date_new')
            with s_cols[1]:
                st.selectbox('Precision', options=precisions,index=None,
                             key='death_date_precision_new')

            st.divider()
            st.text_area('Notes', key='notes_new')

        st.divider()
        with st.container(horizontal_alignment='right'):
            if st.form_submit_button('Add New Animal', type='primary', key='add_new_animal'):
                keys = ['first_name', 'middle_names', 'nick_name',
                        'species', 'sex',
                        'birth_date', 'birth_date_precision', 'death_date', 'death_date_precision',
                        'notes']
                information = {k: get_value(st.session_state[f'{k}_new']) for k in keys}
                st.session_state['member_id'] = insert_animal(engine, information)
                get_member_data.clear()
                st.rerun()

@st.dialog('Add New Parent', width='medium')
def add_new_parent(persons, person_id):
    possible = persons[persons['member_id'] != person_id]
    with st.form('add_parent'):
        cols = st.columns([2, 1])
        with cols[0]:
            st.selectbox(f'New Parent for {get_member_name_display(persons, person_id)}', options=possible['member_id'],
                         format_func=lambda x: get_member_name_display(persons, x),
                         index=None,
                         key=f'parent_id_new')
        with cols[1]:
            st.selectbox(f'Relation type', options=relation_types['person'],
                         index=None,
                         key=f'relation_type_new')

        st.divider()
        with st.container(horizontal_alignment='right'):
            if st.form_submit_button('Add Parenthood', type='primary'):
                keys = ['parent_id', 'relation_type']
                information = {'child_id': person_id}
                information.update({k: get_value(st.session_state[f'{k}_new']) for k in keys})
                insert_parents(engine, information)
                st.rerun()

@st.dialog('Add New Owner', width='medium')
def add_new_owner(persons, animal_id):
    with st.form('add_parent'):
        with st.container():
            cols = st.columns([2, 1])
            with cols[0]:
                st.selectbox(f'New Owner for {get_member_name_display(persons, animal_id)}', options=persons['member_id'],
                             format_func=lambda x: get_member_name_display(persons, x),
                             index=None,
                             key=f'owner_id_new')
            with cols[1]:
                st.selectbox(f'Relation type', options=relation_types['animal'],
                             index=None,
                             key=f'relation_type_new')

        with st.container():
            cols = st.columns([2, 1])
            with cols[0]:
                st.date_input('Gotcha Date', value=None, min_value=date.min, max_value=date.max,
                             key=f'gotcha_date_new')
            with cols[1]:
                st.selectbox('Precision',
                             options=precisions,
                             index=None,
                             key=f'gotcha_date_precision_new')

        st.divider()
        with st.container(horizontal_alignment='right'):
            if st.form_submit_button('Add Ownership', type='primary'):
                keys = ['owner_id', 'relation_type', 'gotcha_date', 'gotcha_date_precision']
                information = {'pet_id': animal_id}
                information.update({k: get_value(st.session_state[f'{k}_new']) for k in keys})
                insert_pets(engine, information)
                st.rerun()

@st.dialog('Add New Partner', width='medium')
def add_new_partner(persons, person_id):
    possible = persons[persons['member_id'] != person_id]
    with st.form('add_partner'):
        with st.container():
            cols = st.columns([3, 2])
            with cols[0]:
                st.selectbox(f'New Partner for {get_member_name_display(persons, person_id)}', options=possible['member_id'],
                             format_func=lambda x: get_member_name_display(persons, x),
                             index=None,
                             key=f'partner_id_new')

        with st.container():
            cols = st.columns([3, 2, 2])
            with cols[0]:
                st.date_input('Union Date', value=None, min_value=date.min, max_value=date.max,
                             key=f'union_date_new')
            with cols[1]:
                st.selectbox('Precision',
                             options=precisions,
                             index=None,
                             key=f'union_date_precision_new')
            with cols[2]:
                st.selectbox(f'Union type', options=partner_types,
                             index=0 if len(partner_types)==1 else None,
                             key=f'union_type_new')


        with st.container():
            cols = st.columns([3, 1, 1, 1])
            with cols[0]:
                st.text_input('Custom Name', key=f'last_name_custom_new')
            with cols[1]:
                st.radio('Primary Name', options=[True, False, None], index=None,
                         format_func=lambda x: get_last_name_display(x),
                         key=f'last_name_primary_new')
            with cols[2]:                            
                st.checkbox('Hyphenated', key=f'last_name_hyphen_new')

        st.divider()
        with st.container(horizontal_alignment='right'):
            if st.form_submit_button('Add Partnership', type='primary'):
                keys = ['partner_id', 'union_type', 'union_date', 'union_date_precision',
                        'last_name_custom', 'last_name_hyphen']
                information = {'person_id': person_id,
                               'last_name_person_id': {True: person_id,
                                                       False: st.session_state['partner_id_new']}.get(st.session_state['last_name_primary_new'])}
                information.update({k: get_value(st.session_state[f'{k}_new']) for k in keys})
                insert_partners(engine, information)
                get_member_data.clear()
                st.rerun()

@st.dialog('Add New Friend', width='medium')
def add_new_friend(persons, person_id):
    possible = persons[persons['member_id'] != person_id]
    with st.form('add_friend'):
        with st.container():
            cols = st.columns([3, 2])
            with cols[0]:
                st.selectbox(f'New Friend for {get_member_name_display(persons, person_id)}',
                             options=possible['member_id'],
                             format_func=lambda x: get_member_name_display(persons, x),
                             index=None,
                             key=f'partner_id_new')

        with st.container():
            cols = st.columns([3, 2, 2])
            with cols[0]:
                st.date_input('Union Date', value=None, min_value=date.min, max_value=date.max,
                             key=f'union_date_new')
            with cols[1]:
                st.selectbox('Precision', options=precisions, index=None, key=f'union_date_precision_new')
            with cols[2]:
                st.selectbox(f'Union type', options=connect_types,
                             index=0 if len(connect_types)==1 else None,
                             key=f'union_type_new')

        st.divider()
        with st.container(horizontal_alignment='right'):
            if st.form_submit_button('Add Partnership', type='primary'):
                keys = ['parnter_id', 'union_type', 'union_date', 'union_date_precision']
                keys_2 = ['last_name_person_id', 'last_name_custom', 'last_name_hyphen']
                information = {'person_id': person_id}
                information.update({k: get_value(st.session_state[f'{k}_new']) for k in keys})
                information.update({k: None for k in keys_2})
                insert_partners(engine, information)
                st.rerun()

@st.dialog('Delete a Member', width='medium')
def delete_member(member_id):
    member_type = get_member_type(members, member_id)
    st.warning((f'Are you sure you want to remove {member_type} {get_member_name_display(members, member_id)}? '
                f'This cannot be undone.'))
    with st.container(horizontal_alignment='right'):
        if st.button('Confirm', type='primary'):
            match member_type:
                case 'person':
                    remove_person(engine, member_id)
                case 'animal':
                    remove_animal(engine, member_id)
            st.session_state['member_id'] = None
            get_member_data.clear()
            st.rerun()

members = get_member_data(engine)
persons = members[members['member_type'] == 'person'].reset_index(drop=True)
animals = members[members['member_type'] == 'animal'].reset_index(drop=True)

with st.container():
    x_cols = st.columns([2, 1, 1, 1], vertical_alignment='bottom')
    with x_cols[0]:
        member_id = st.selectbox('Select Member to Edit',
                                 members['member_id'], placeholder='Choose a family member to edit or add new member',
                                 format_func=lambda x: get_member_name_display(members, x), index=None, width=400,
                                 key='member_select', on_change=select_member
                                 )

    with x_cols[1]:
        if member_id is not None:
            with st.container(horizontal_alignment='center'):
                if st.button('Delete Member', type='primary'):
                    delete_member(member_id)

    with x_cols[2]:
        with st.container(horizontal_alignment='center'):
            if st.button('Add New Person', type='primary'):
                add_new_person()

    with x_cols[3]:
        with st.container(horizontal_alignment='center'):
            if st.button('Add New Animal', type='primary'):
                add_new_animal()

if member_id is not None:
    member_type = get_member_type(members, member_id)
    information = {'person': fetch_persons,
                   'animal': fetch_animals}[member_type](engine, member_id)

    match member_type:
        case 'person':
            pre_name = (information[['first_name', 'middle_names', 'last_name', 'uses_middle', 'nick_name']].iloc[0].tolist())
        case 'animal':
            pre_name = (information[['first_name', 'nick_name', 'species']].iloc[0].tolist())

    # edit basic bio
    with st.form('edit_member'):
        with st.container():
            st.markdown(f'{member_type}_id: :blue-badge[' + str(information[f'{member_type}_id'].iloc[0]) + ']')
            cols = st.columns(3)
            with cols[0]:
                if member_type == 'person':
                    st.selectbox('Prefix', options=prefixes,
                                 index=get_index(prefixes, information['prefix'].iloc[0]), width=100,
                                 key='prefix')
                st.text_input('First Name', information['first_name'].iloc[0], width=300, key='first_name')
                st.text_input('Nickname', information['nick_name'].iloc[0], width=300, key='nick_name')            
                st.text_input('Middle Names', information['middle_names'].iloc[0], width=300, key='middle_names')
                if member_type == 'person':
                    st.checkbox('Uses Middle', information['uses_middle'].iloc[0], key='uses_middle')
                    st.text_input('Last Name', information['last_name'].iloc[0], width=300, key='last_name')
                    st.number_input('Suffix', min_value=1, max_value=None,
                                    value=information['suffix'].iloc[0], width=100, key='suffix')


            with cols[1]:
                s = information['sex'].iloc[0]
                st.selectbox('Sex', options=sexes.keys(), width=100,
                             format_func=lambda x: sexes.get(x, 'Unknown'),
                             index=list(sexes.keys()).index(s) if s in sexes else None,
                             key='sex')
                if member_type == 'animal':
                    sp = information['species'].iloc[0]
                    st.selectbox('Species', options=specieses, width=200,
                                 index=specieses.index(sp) if sp in specieses else None,
                                 key='species')

                s_cols = st.columns([3, 2])
                with s_cols[0]:
                    st.date_input('Birth Date', information['birth_date'].iloc[0],
                                  min_value=date.min, max_value=date.max,width=200,
                                  key='birth_date')
                with s_cols[1]:
                    b_d_p = information['birth_date_precision'].iloc[0]
                    st.selectbox('Precision', options=precisions,
                                 index=get_index(precisions, b_d_p),
                                 key='birth_date_precision')

                s_cols = st.columns([3, 2])
                with s_cols[0]:
                    st.date_input('Death Date', information['death_date'].iloc[0],
                                  min_value=date.min, max_value=date.max, width=200,
                                  key='death_date')
                with s_cols[1]:
                    d_d_p = information['death_date_precision'].iloc[0]
                    st.selectbox('Precision', options=precisions,
                                 index=get_index(precisions, d_d_p),
                                 key='death_date_precision')

                st.divider()

                st.text_area('Notes', information['notes'].iloc[0], key='notes')

            with cols[2]:
                image_url = get_image_url(engine, cloud, member_id, profile_type=member_type, square=True)
                st.image(image_url, width=350)

                if 'image_replacement_key' in st.session_state:
                    image_replacement_key = st.session_state['image_replacement_key']
                else:
                    image_replacement_key = 0
                    st.session_state['image_replacement_key'] = image_replacement_key
                replace_image_path = st.file_uploader('Replace Image', type=['jpg', 'jpeg', 'png'],
                                                        help='Upload a new image to replace the current one.',
                                                        key=f'image_replacement_key{image_replacement_key}',
                                                        width=350)
                
        # edit parents and owners
        match member_type:
            case 'person':
                parents = fetch_parents(engine, person_id=member_id)
                if len(parents):
                    st.divider()
                    with st.container():
                        for p, (parent_id, relation_type) in parents[['parent_id', 'relation_type']].iterrows():
                            cols = st.columns([1, 8, 4, 4, 3], vertical_alignment='bottom')
                            with cols[0]:
                                st.checkbox(label=None, value=True, key=f'include_parent_{p}')
                            with cols[1]:
                                st.selectbox(f'Parent {p+1}', options=persons['member_id'],
                                             format_func=lambda x: get_member_name_display(members, x),
                                             index=persons['member_id'].tolist().index(parent_id),
                                             disabled=True,
                                             key=f'parent_id_{p}')
                            with cols[2]:
                                st.selectbox(f'Relation type', options=relation_types[member_type],
                                             index=relation_types[member_type].index(relation_type),
                                             key=f'parent_relation_{p}')

            case 'animal':
                pets = fetch_pets(engine, animal_id=member_id)
                if len(pets):
                    st.divider()
                    with st.container():
                        for p, (owner_id, relation_type,
                                gotcha_date, gotcha_date_precision) in pets[['owner_id',
                                                                             'relation_type',
                                                                             'gotcha_date',
                                                                             'gotcha_date_precision']].iterrows():
                            cols = st.columns([1, 8, 4, 4, 3], vertical_alignment='bottom')
                            with cols[0]:
                                st.checkbox(label=None, value=True, key=f'include_owner_{p}')
                            with cols[1]:
                                st.selectbox(f'Owner {p+1}', options=persons['member_id'],
                                             format_func=lambda x: get_member_name_display(members, x),
                                             index=persons['member_id'].tolist().index(owner_id),
                                             disabled=True,
                                             key=f'owner_{p}')
                            with cols[2]:
                                st.selectbox(f'Relation Type', options=relation_types[member_type],
                                             index=relation_types[member_type].index(relation_type),
                                             key=f'owner_relation_{p}')
                            with cols[3]:
                                st.date_input('Gotcha Date', gotcha_date,
                                              min_value=date.min, max_value=date.max, key=f'gotcha_date_{p}')
                            with cols[4]:
                                st.selectbox('Precision',
                                             options=precisions,
                                             index=get_index(precisions, gotcha_date_precision),
                                             key=f'gotcha_date_precision_{p}')

        # edit spouses and friends
        if member_type == 'person':
            partners = fetch_partners(engine, person_id=member_id)
            if len(partners):
                st.divider()
                with st.container():
                    spouses = partners[partners['union_type'].isin(partner_types)]
                    for p, (partner_id, union_type,
                            union_date, union_date_precision,
                            last_name_person_id, last_name_hyphen, last_name_custom) in \
                                spouses[['partner_id',
                                         'union_type', 'union_date', 'union_date_precision',
                                         'last_name_person_id', 'last_name_hyphen', 'last_name_custom']].iterrows():
                        with st.container():
                            cols = st.columns([1, 6, 2, 3, 2, 1], vertical_alignment='bottom')
                            with cols[0]:
                                st.checkbox(label=None, value=True, key=f'include_partner_{p}')
                            with cols[1]:
                                st.selectbox(f'Partner {p+1}', options=persons['member_id'],
                                             format_func=lambda x: get_member_name_display(members, x),
                                             index=persons['member_id'].tolist().index(partner_id),
                                             disabled=True,
                                             key=f'partner_id_{p}')
                            with cols[2]:
                                st.selectbox(f'Union type', options=union_types,
                                             index=union_types.index(union_type),
                                             key=f'union_type_{p}')
                            with cols[3]:
                                st.date_input('Union Date', union_date,
                                              min_value=date.min, max_value=date.max,key=f'union_date_{p}')
                            with cols[4]:
                                st.selectbox('Precision',
                                             options=precisions,
                                             index=get_index(precisions, union_date_precision),
                                             key=f'union_date_precision_{p}')
                        with st.container():
                            cols = st.columns([1, 6, 2, 2, 3, 1])
                            with cols[1]:
                                st.text_input('Custom Name', value=last_name_custom, key=f'last_name_custom_{p}')
                            with cols[2]:
                                st.checkbox('Primary Name', value=last_name_person_id==member_id, key=f'primary_name_{p}')
                            with cols[3]:                            
                                st.checkbox('Hyphenated', value=last_name_hyphen, key=f'uses_hyphen_{p}')


                    friends = partners[partners['union_type'].isin(connect_types)]
                    q = len(spouses)
                    for p, (partner_id, union_type,
                            union_date, union_date_precision) in friends[['partner_id',
                                                                          'union_type',
                                                                          'union_date',
                                                                          'union_date_precision']].iterrows():
                        cols = st.columns([1, 9, 4, 4, 2], vertical_alignment='bottom')
                        with cols[0]:
                            st.checkbox(label=None, value=True, key=f'include_partner_{p+q}')
                        with cols[1]:
                            st.selectbox(f'Friend {p+1}', options=persons['member_id'],
                                         format_func=lambda x: get_member_name_display(members, x),
                                         index=persons['member_id'].tolist().index(partner_id),
                                         disabled=True,
                                         key=f'partner_id_{p+q}')
                        with cols[2]:
                            st.selectbox(f'Union type', options=union_types,
                                         index=union_types.index(union_type),
                                         key=f'union_type_{p+q}')
                        with cols[3]:
                            st.date_input('Union Date', union_date,
                                          min_value=date.min, max_value=date.max, key=f'union_date_{p+q}')
                        with cols[4]:
                            st.selectbox('Precision',
                                         options=precisions,
                                         index=get_index(precisions, union_date_precision),
                                         key=f'union_date_precision_{p+q}')

        # wrap up
        st.divider()
        with st.container(horizontal_alignment='right'):
            form_submitted = st.form_submit_button('Update Member', type='primary')
            date_precisions_check = (check_date_precisions(st.session_state['birth_date'],
                                                           st.session_state['birth_date_precision']) and
                                     check_date_precisions(st.session_state['death_date'], 
                                                           st.session_state['death_date_precision']))
            if form_submitted: # and date_precisions_check:
                # update member bio
                match member_type:
                    case 'person':
                        keys = ['first_name', 'nick_name', 'middle_names', 'uses_middle', 'last_name',
                                'prefix', 'suffix', 'sex',
                                'birth_date', 'birth_date_precision', 'death_date', 'death_date_precision',
                                'notes']
                        information = {'person_id': member_id}
                        information.update({k: get_value(st.session_state[k]) for k in keys})
                        update_person(engine, information)
                    case 'animal':
                        keys = ['first_name', 'nick_name', 'middle_names',
                                'species', 'sex',
                                'birth_date', 'birth_date_precision', 'death_date', 'death_date_precision',
                                'notes']
                        information = {'animal_id': member_id}
                        information.update({k: get_value(st.session_state[k]) for k in keys})
                        update_animal(engine, information)

                match member_type:
                    case 'person':
                        post_name = [st.session_state[k] for k in ['first_name', 'middle_names', 'last_name',
                                                                   'uses_middle', 'nick_name']]
                    case 'animal':
                        post_name = [st.session_state[k] for k in ['first_name', 'nick_name', 'species']]

                # update profile image
                if replace_image_path:
                    display_name = get_member_name_display(members, member_id)
                    upload_image(engine, public_id=member_id, image_path=replace_image_path, display_name=display_name)
                    st.session_state['image_replacement_key'] += 1
                    get_version.clear(engine, member_id)
                    
                # update parents, partners and owners
                match member_type:
                    case 'person':
                        # update parents
                        for i in range(len(parents)):
                            if not st.session_state[f'include_parent_{i}']:
                                information = {'child_id': member_id,
                                                'parent_id_old': st.session_state[f'parent_id_{i}']}
                                remove_parents(engine, information)
                            else:
                                keys = ['parent_id', 'relation_type']
                                information = {'child_id': member_id}
                                information.update({k: get_value(st.session_state.get(f'{k}_{i}')) for k in keys})
                                update_parents(engine, information)

                        # update partners
                        for i in range(len(partners)):
                            if not st.session_state[f'include_partner_{i}']:
                                information = {'person_id': member_id,
                                               'partner_id_old': st.session_state[f'partner_id_{i}']}
                                remove_partners(engine, information)
                            else:
                                keys = ['union_id', 'union_date', 'union_date_precision', 'union_type',
                                        'last_name_person_id', 'last_name_hyphen', 'last_name_custom']
                                information = {k: get_value(st.session_state.get(f'{k}_{i}')) for k in keys}
                                update_parents(engine, information)

                    case 'animal':
                        # update owners
                        for i in range(len(pets)):
                            if not st.session_state[f'include_owner_{i}']:
                                information = {'pet_id': member_id,
                                               'owner_id_old': st.session_state[f'owner_id_{i}']}
                                remove_parents(engine, information)
                            else:
                                keys = ['owner_id', 'relation_type', 'gotcha_date', 'gotcha_date_precion']
                                information = {'pet_id': member_id}
                                information.update({k: get_value(st.session_state.get(f'{k}_{i}')) for k in keys})
                                update_pets(engine, information)

                # refresh cache for new names
                ##if pre_name != post_name:
                get_member_data.clear()


    # add a new parent
    match member_type:
        case 'person':
            cols = st.columns(3)
            with cols[0]:
                if st.button('Add New Parent', type='primary'):
                    add_new_parent(persons, member_id)
            with cols[1]:
                if st.button('Add New Partner', type='primary'):
                    add_new_partner(persons, member_id)
            with cols[2]:
                if st.button('Add New Friend', type='primary'):
                    add_new_friend(persons, member_id)


        case 'animal':
            if st.button('Add New Owner', type='primary'):
                add_new_owner(persons, member_id)