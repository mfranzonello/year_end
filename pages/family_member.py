from uuid import UUID
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from six import b
import streamlit as st

from database.db import get_engine
from database.db_family import fetch_person_information, fetch_animal_information
from database.db_display import fetch_member_names
from family_tree.cloudy import get_image_url, upload_image, configure_cloud
from pages.general import set_sidebar

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

def get_date_display(entry_date, entry_date_precision):
    if entry_date is not None:
        match entry_date_precision:
            case 'future':
                return 'TBD'
            case 'year':
                date_str = entry_date.strftime('%Y')
                return f'c. {date_str}'
            case 'month':
                date_str = entry_date.strftime('%B %Y')
                return f'c. {date_str}'
            case 'day':
                date_str = entry_date.strftime("%A %B %d, %Y")
                return date_str
            case _:
                return None

def get_time_passed(start_date, start_date_precision, end_date):
    if (start_date is not None) and (end_date is not None):
        match start_date_precision:
            case 'year':
                start_date = date(start_date.year + 1, 1, 1) - timedelta(days = 1)
            case 'month':
                start_date = date(start_date.year + 1, start_date.month + 1, 1) - timedelta(days = 1)
            case 'day':
                pass
            case _:
                return None

        return relativedelta(end_date, start_date)

def get_time_passed_display(start_date, start_date_precision, end_date, include_years=False):
    time_passed = get_time_passed(start_date, start_date_precision, end_date)
    if time_passed is not None:
    
        if time_passed.years < 1:
            if time_passed.months < 1:
                return f'{time_passed.days} days'
            return f'{time_passed.months} months'
        years = ' years' if include_years else ''
        return f'{time_passed.years}{years}'

def get_list_display(list_names):
    if len(list_names):
        conj = ' and ' if len(list_names) > 1 else ''
        return ', '.join(list_names[:-1]) + conj + list_names[-1]

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
    # born and living marker
    death_date = information["death_date"].iloc[0]
    death_date_precision = information["death_date_precision"].iloc[0]
    if death_date_precision == 'past' or death_date is not None:
        st.markdown(f'*Deceased*')

    birth_date = information["birth_date"].iloc[0]
    birth_date_precision = information["birth_date_precision"].iloc[0]
    if birth_date_precision == 'future':
        st.markdown(f'*Unborn*')

    if death_date:
        cut_date = min(death_date, date.today())
    else:
        cut_date = date.today()

    # name information
    first_name = information["first_name"].iloc[0]
    if first_name:
        st.markdown(f'**First Name**: {first_name}')
    middle_names = information["middle_names"].iloc[0]
    nick_name = information["nick_name"].iloc[0]
    if nick_name:
        st.markdown(f'**Nickname**: "{nick_name}"')
    if middle_names:
        st.markdown(f'**Middle Names**: {middle_names}')
    if member_type == 'person':
        last_name = information["last_name"].iloc[0]
        st.markdown(f'**Last Name**: {last_name}')

    # birth and death information
    birthday = get_date_display(birth_date, birth_date_precision)
    if birthday is not None:
        st.markdown(f'**Born**: {birthday}')

    deathday = get_date_display(death_date, death_date_precision)
    if deathday is not None:
        st.markdown(f'**Died**: {deathday}')

    if death_date_precision is not 'past':
        age = get_time_passed_display(birth_date, birth_date_precision, cut_date, include_years=False)
        if age is not None:
            st.markdown(f'**Age**: {age}')

    # species and gender information
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
        # marriage information
        spouse = information['spouse_name'].iloc[0]
        if spouse:
            spouse_name = {'m': 'Husband', 'f': 'Wife'}.get(sex, 'Spouse')
            st.markdown(f'**{spouse_name} of**: {spouse}')
        union_date = information['union_date'].iloc[0]
        if union_date:
            union_date_precision = information['union_date_precision'].iloc[0]
            anniversary = get_date_display(union_date, union_date_precision)
            st.markdown(f'**Anniversary**: {anniversary}')

            severance_date = information['severance_date'].iloc[0]
            if severance_date is not None:
                cut_date_2 = min(severance_date, cut_date)
            else:
                cut_date_2 = cut_date
            marriage_span = get_time_passed_display(union_date, union_date_precision, cut_date_2, include_years=True) ## should look at spouse end date too
            st.markdown(f'**Married for**: {marriage_span}')

        # clan information
        children = information['children_names'].iloc[0]
        if children:
            parent_name = {'m': 'Father', 'f': 'Mother'}.get(sex, 'Parent')
            st.markdown(f'**{parent_name} of {len(children)}**: {get_list_display(children)}')
        pets = information['pet_names'].iloc[0]
        if pets:
            st.markdown(f'**Owner of**: {get_list_display(pets)}')
        parents = information['parent_names'].iloc[0]
        if parents:
            st.markdown(f'**Child of**: {get_list_display(parents)}')

    elif member_type == 'animal':
        # ownership information
        owners = information['owner_names'].iloc[0]
        if owners:
            st.markdown(f'**Pet of**: {", ".join(owners)}')

        gotcha_date = information['gotcha_date'].iloc[0]
        if gotcha_date is not None:
            gotcha_date_precision = information['gotcha_date_precision'].iloc[0]
            adoption = get_date_display(gotcha_date, gotcha_date_precision)
            st.markdown(f'**Adopted on**: {adoption}')
            owned_span = get_time_passed_display(gotcha_date, gotcha_date_precision, cut_date, include_years=True)
            st.markdown(f'**Owned for**: {owned_span}')

# change image
replace_image_path = st.file_uploader('Replace Image', type=['jpg', 'jpeg', 'png'], help='Upload a new image to replace the current one.')
if replace_image_path:
    replace = st.button('Replace', type='primary')
    
    if replace:
        display_name = members[members['member_id'] == member_id]['full_name'].iloc[0]
        upload_image(public_id=member_id, image_path=replace_image_path, display_name=display_name)
