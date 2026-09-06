from uuid import UUID
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from six import b
import streamlit as st

from database.db import get_engine
from database.db_family import fetch_person_information, fetch_animal_information
from database.db_display import fetch_member_names
from family_tree.cloudinary_lite import get_image_url
from family_tree.cloudinary_heavy import upload_image, configure_cloud
from pages.general import set_sidebar

PGHOST = st.secrets['postgresql']['host']
PGPORT = st.secrets['postgresql'].get('port', '5432')
PGDBNAME = st.secrets['postgresql']['database']
PGUSER = st.secrets['postgresql']['user']
PGPASSWORD = st.secrets['postgresql']['password']

CLOUDINARY_CLOUD = st.secrets['cloudinary']['cloud_name']
CLOUDINARY_API = st.secrets['cloudinary']['api_key']
CLOUDINARY_SECRET = st.secrets['cloudinary']['api_secret']
configure_cloud(CLOUDINARY_CLOUD, CLOUDINARY_API, CLOUDINARY_SECRET)

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

SCHEMA_NAME = 'dashboard'  # demo if not logged in

def get_date_str():
    pass

def get_time_passed():
    pass

# set up page
set_sidebar()
st.set_page_config(page_title='Franzonello Family YIR Appearances',
                   layout='wide')

members = fetch_member_names(engine, schema_name=SCHEMA_NAME).sort_values('full_name').reset_index(drop=True)
member_id = st.selectbox('Select Family Member', members['member_id'],
                         format_func=lambda x: members[members['member_id'] == x]['full_name'].iloc[0])

member_type = members[members['member_id'] == member_id]['member_type'].iloc[0]

if member_type == 'person':
    information = fetch_person_information(engine, member_id)
elif member_type == 'animal':
    information = fetch_animal_information(engine, member_id)

col1, col2, col3 = st.columns(3)
with col1:
    image_url = get_image_url(CLOUDINARY_CLOUD, member_id, pixels=400)
    st.image(image_url)

with col2:
    first_name = information["first_name"].iloc[0]
    if first_name:
        st.markdown(f'**First Name**: {first_name}')
    middle_names = information["middle_names"].iloc[0]
    if middle_names:
        st.markdown(f'**Middle Names**: {middle_names}')
    if member_type == 'person':
        last_name = information["last_name"].iloc[0]
        st.markdown(f'**Last Name**: {last_name}')

    birth_date = information["birth_date"].iloc[0]
    birth_date_precision = information["birth_date_precision"].iloc[0]
    death_date = information["death_date"].iloc[0]
    death_date_precision = information["death_date_precision"].iloc[0]
    if death_date:
        cut_date = min(death_date, date.today())
    else:
        cut_date = date.today()

    age = None
    match birth_date_precision:
        case 'day':
            birthday = f'{birth_date.strftime("%A %B %d, %Y")}'
            if death_date_precision != 'past':
                age = relativedelta(cut_date, birth_date).years
        case 'month':
            birthday = f'c. {birth_date.strftime("%B %Y")}'
            if death_date_precision != 'past':
                age = f'~{relativedelta(cut_date, date(birth_date.year, birth_date.month + 1, 1) - timedelta(days=1)).years}'
        case 'year':
            birthday = f'c. {birth_date.strftime("%Y")}'
            if death_date_precision != 'past':
                age = f'~{relativedelta(cut_date, date(birth_date.year + 1, 1, 1) - timedelta(days=1)).years}'
        case 'future':
            birthday = 'TBD!'
        case _:
            birthday = None

    if birthday:
        st.markdown(f'**Born**: {birthday}')
    if age:
        st.markdown(f'**Age**: {age}')
    if death_date_precision == 'past' or death_date:
        st.markdown(f'*Deceased*')

    if member_type == 'animal':
        species = information["species"].iloc[0]
        if species:
            st.markdown(f'**Species**: {species}')
    sex = information["sex"].iloc[0]
    if sex:
        gender = {'m': 'Male', 'f': 'Female'}
        st.markdown(f'**Gender**: {gender[sex]}')


with col3:
    if member_type == 'person':
        spouse = information['spouse_name'].iloc[0]
        if spouse:
            st.markdown(f'**Married to**: {spouse}')
        anniversary = information['union_date'].iloc[0]
        if anniversary:
            match information['union_date_precision'].iloc[0]:
                case 'day':
                    anniversary_str = f'{anniversary.strftime("%A %B %d, %Y")}'
                case 'month':
                    anniversary_str = f'c. {anniversary.strftime("%B %Y")}'
                case 'year':
                    anniversary_str = f'c. {anniversary.strftime("%Y")}'
            st.markdown(f'**Anniversary**: {anniversary_str}')

        children = information['children_names'].iloc[0]
        if children:
            parent_name = {'m': 'Father', 'f': 'Mother'}.get(sex, 'Parent')
            children_names = ', '.join(children)
            st.markdown(f'**{parent_name} of {len(children)}**: {children_names}')
        pets = information['pet_names'].iloc[0]
        if pets:
            st.markdown(f'**Owner of**: {", ".join(pets)}')
        parents = information['parent_names'].iloc[0]
        if parents:
            st.markdown(f'**Child of**: {", ".join(parents)}')

    elif member_type == 'animal':
        owners = information['owner_names'].iloc[0]
        if owners:
            st.markdown(f'**Pet of**: {", ".join(owners)}')

replace_image_path = st.file_uploader('Replace Image', type=['jpg', 'jpeg', 'png'], help='Upload a new image to replace the current one.')
if replace_image_path:
    replace = st.button('Replace', type='primary')
    
    if replace:
        display_name = members[members['member_id'] == member_id]['full_name'].iloc[0]
        upload_image(public_id=member_id, image_path=replace_image_path, display_name=display_name)