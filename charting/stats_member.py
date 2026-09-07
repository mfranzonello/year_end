from uuid import UUID
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

import streamlit as st

from database.db import get_engine
from database.db_family import fetch_person_information, fetch_animal_information
from family_tree.cloudy import get_image_url, upload_image, configure_cloud
from pages.general import set_sidebar

def get_member_name_display(members, member_id):
    return members[members['member_id'] == member_id]['full_name'].iloc[0]

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

def get_gender(sex):
    gender_types = {'m': 'Male ♂',
                    'f': 'Female ♀️',
                    }
    return gender_types.get(sex, 'Unknown ⚥')

def get_gendered_name(name_type, sex):
    name_types = {'parent': {'m': 'Father', 'f': 'Mother'},
                  'sibling': {'m': 'Brother', 'f': 'Sister'},
                  'child': {'m': 'Son', 'f': 'Daughter'},
                  'spouse': {'m': 'Husband', 'f': 'Wife'},
                  'nee': {'m': 'Bachelor', 'f': 'Maiden'},
                  }
    return name_types[name_type].get(sex, name_type.title())

def get_specied_name(species):
    species_types = {'cat': '🐈',
                     'dog': '🐕',
                     'fish': '🐟',
                     'rabbit': '🐇',
                     'bird': '🐦'}
    return species.title() + ' ' + species_types.get(species, '🧸')

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

def get_list_display(members, list_ids, callout):
    with st.container(horizontal=True, gap='small'):
        st.markdown(callout)

    with st.container(width='content'):
        for list_id in list_ids:
            if st.button(get_member_name_display(members, list_id), type='secondary'):
                st.session_state['member_id'] = list_id
                st.rerun()

def get_plural(word, items, s='s', plural=None):
    if plural is None:
        plural = word + s
    return plural if (len(items) != 1) else word

def fill_in_bio(engine, member_id, members, cloud_name):
    member_type = members[members['member_id'] == member_id]['member_type'].iloc[0]

    if member_type == 'person':
        information = fetch_person_information(engine, member_id)
    elif member_type == 'animal':
        information = fetch_animal_information(engine, member_id)
    sex = information['sex'].iloc[0]

    col1, col2, col3 = st.columns(3)
    with col1:
        # member image
        image_url = get_image_url(engine, cloud_name, member_id, profile_type=member_type, pixels=400)
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
            m_names = middle_names.split(';')
            m_names_all = ' '.join(m_names)
            st.markdown(f'**Middle {get_plural("Name", m_names)}**: {m_names_all}')
        if member_type == 'person':
            last_name = information['last_name'].iloc[0]
            married_name = information['married_name'].iloc[0]
            if married_name and married_name != last_name:
                nee_name = get_gendered_name('nee', sex)
                st.markdown(f'**{nee_name} Name**: {last_name}')
                st.markdown(f'**Last Name**: {married_name}')
            else:
                st.markdown(f'**Last Name**: {last_name}')

        # birth and death information
        birthday = get_date_display(birth_date, birth_date_precision)
        if birthday is not None:
            st.markdown(f'**Born**: {birthday}')

        deathday = get_date_display(death_date, death_date_precision)
        if deathday is not None:
            st.markdown(f'**Died**: {deathday}')

        if death_date_precision != 'past':
            age = get_time_passed_display(birth_date, birth_date_precision, cut_date, include_years=False)
            if age is not None:
                st.markdown(f'**Age**: {age}')

        # species and gender information
        if member_type == 'animal':
            species = information["species"].iloc[0]
            if species:
                species_name = get_specied_name(species)
                st.markdown(f'**Species**: {species_name}')

        if sex:
            gender = get_gender(sex)
            st.markdown(f'**Gender**: {gender}')

    with col3:
        if member_type == 'person':
            # marriage information
            spouse = information['spouse_ids'].iloc[0]
            if spouse:
                spouse_name = get_gendered_name('spouse', sex)
                get_list_display(members, spouse, f'**{spouse_name} of**:')

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
            children = information['child_ids'].iloc[0]
            if children:
                parent_name = get_gendered_name('parent', sex)
                get_list_display(members, children, f'**{parent_name} of {len(children)}**:')

            pets = information['pet_ids'].iloc[0]
            if pets:
                get_list_display(members, pets, '**Owner of**:')

            parents = information['parent_ids'].iloc[0]
            if parents:
                child_name = get_gendered_name('child', sex)
                get_list_display(members, parents, f'**{child_name} of**:')

        elif member_type == 'animal':
            # ownership information
            owners = information['owner_ids'].iloc[0]
            if owners:
                get_list_display(members, owners, '**Pet of**:')

            gotcha_date = information['gotcha_date'].iloc[0]
            if gotcha_date is not None:
                gotcha_date_precision = information['gotcha_date_precision'].iloc[0]
                adoption = get_date_display(gotcha_date, gotcha_date_precision)
                st.markdown(f'**Adopted on**: {adoption}')
                if death_date_precision != 'past':
                    owned_span = get_time_passed_display(gotcha_date, gotcha_date_precision, cut_date, include_years=True)
                    st.markdown(f'**Owned for**: {owned_span}')

    # change image
    if 'image_replacement_key' in st.session_state:
        image_replacement_key = st.session_state['image_replacement_key']
    else:
        image_replacement_key = 0
        st.session_state['image_replacement_key'] = image_replacement_key
    replace_image_path = st.file_uploader('Replace Image', type=['jpg', 'jpeg', 'png'],
                                          help='Upload a new image to replace the current one.',
                                          key=f'image_replacement_key{image_replacement_key}')
    if replace_image_path:
        replace = st.button('Replace', type='primary')
    
        if replace:
            display_name = members[members['member_id'] == member_id]['full_name'].iloc[0]
            upload_image(engine, public_id=member_id, image_path=replace_image_path, display_name=display_name)
            st.session_state['image_replacement_key'] += 1
            st.rerun()

