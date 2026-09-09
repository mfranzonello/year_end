"""Render member biography details, with administrator-only image replacement."""

from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

import streamlit as st
from pgeocode import Nominatim
from pandas import DataFrame

from family_tree.cloudy import get_version, get_image_url, upload_image
from pages.streamlit_auth import current_tier, require_admin

nomi = Nominatim('us')

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

def get_gender(sex:str):
    gender_types = {'m': 'Male ♂',
                    'f': 'Female ♀️',
                    }
    return gender_types.get(sex, 'Unknown ⚥')

def get_gendered_name(name_type:str, sex:str):
    name_types = {'parent': {'m': 'Father', 'f': 'Mother'},
                  'sibling': {'m': 'Brother', 'f': 'Sister'},
                  'child': {'m': 'Son', 'f': 'Daughter'},
                  'spouse': {'m': 'Husband', 'f': 'Wife'},
                  'nee': {'m': 'Bachelor', 'f': 'Maiden'},
                  'expecting': {'m': 'Waiting for', 'f': 'Pregnant with'}
                  }
    return name_types[name_type].get(sex, name_type.title())

def get_specied_name(species:str):
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

def get_time_passed_display(start_date, start_date_precision, end_date, end_date_precision='day'):
    time_passed = get_time_passed(start_date, start_date_precision, end_date)
    if any(p != 'day' for p in [start_date_precision, end_date_precision]):
        approx = '~'
    else:
        approx = ''
    if time_passed is not None:
        if time_passed.years < 1:
            if time_passed.months < 1:
                d = time_passed.days
                return f'{approx}{d} {get_plural("day", count=d)}'
            m = time_passed.months
            return f'{approx}{m} {get_plural("month", count=m)}'
        y = time_passed.years
        return f'{approx}{y} {get_plural("year", count=y)}'

def get_list_display(members, list_ids, callout):
    with st.container(horizontal=True, gap='small'):
        st.markdown(callout)

    with st.container(width='content'):
        for list_id in list_ids:
            if st.button(get_member_name_display(members, list_id), type='secondary'):
                st.session_state['member_id'] = list_id
                st.rerun()

def get_plural(word:str, count:int=None, items:list=None, s:str='s', plural:str=None):
    if plural is None:
        plural = word + s

    if count is not None:
        quantity = count
    elif items is not None:
        quantity = len(items)

    return plural if (quantity != 1) else word

def plot_map(zip_code:int):
    if zip_code:
        location = nomi.query_postal_code(zip_code)
        location_data = DataFrame([[location.latitude, location.longitude]], columns=('lat', 'lon'))
        return location_data

def fill_image(_engine, cloud_name, members, member_type, member_id):
    # member image
    image_url = get_image_url(_engine, cloud_name, member_id, profile_type=member_type, square=True)
    st.image(image_url, width=350)

    if current_tier() == "admin":
        # change image
        if 'image_replacement_key' in st.session_state:
            image_replacement_key = st.session_state['image_replacement_key']
        else:
            image_replacement_key = 0
            st.session_state['image_replacement_key'] = image_replacement_key
        replace_image_path = st.file_uploader('Replace Image', type=['jpg', 'jpeg', 'png'],
                                                help='Upload a new image to replace the current one.',
                                                key=f'image_replacement_key{image_replacement_key}',
                                                width=350)
        if replace_image_path:
            replace = st.button('Replace', type='primary')

            if replace:
                require_admin()
                display_name = members[members['member_id'] == member_id]['full_name'].iloc[0]
                upload_image(_engine, public_id=member_id, image_path=replace_image_path, display_name=display_name)
                st.session_state['image_replacement_key'] += 1
                get_version.clear(_engine, member_id)
                st.rerun()

def fill_personal(information, member_type, sex, is_future, is_deceased):
    # born and living marker
    death_date = information["death_date"].iloc[0]
    death_date_precision = information["death_date_precision"].iloc[0]
    if is_deceased:
        st.markdown(f'*Deceased*')

    birth_date = information["birth_date"].iloc[0]
    birth_date_precision = information["birth_date_precision"].iloc[0]
    if is_future:
        st.markdown('*Unborn*')

    if death_date:
        cut_date = min(death_date, date.today())
        cut_date_precision = death_date_precision
    else:
        cut_date = date.today()
        cut_date_precision = 'day'

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
        st.markdown(f'**Middle {get_plural("Name", items=m_names)}**: {m_names_all}')
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
        age = get_time_passed_display(birth_date, birth_date_precision, cut_date, cut_date_precision)
        if age is not None:
            st.markdown(f'**Age**: {age}')

    # species and gender information
    if member_type == 'animal':
        species = information["species"].iloc[0]
        if species:
            species_name = get_specied_name(species)
            st.markdown(f'**Species**: {species_name}')

    gender = get_gender(sex)
    st.markdown(f'**Gender**: {gender}')

    if member_type == 'person':
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
            marriage_span = get_time_passed_display(union_date, union_date_precision, cut_date_2)
            st.markdown(f'**Married for**: {marriage_span}')

    if member_type == 'animal':
        gotcha_date = information['gotcha_date'].iloc[0]
        if gotcha_date is not None:
            gotcha_date_precision = information['gotcha_date_precision'].iloc[0]
            adoption = get_date_display(gotcha_date, gotcha_date_precision)
            st.markdown(f'**Adopted on**: {adoption}')
            if death_date_precision != 'past':
                owned_span = get_time_passed_display(gotcha_date, gotcha_date_precision, cut_date, cut_date_precision)
                st.markdown(f'**Owned for**: {owned_span}')

    # project information
    project_stats = information['project_stats'].iloc[0]
    if project_stats.get('files'):
        v = project_stats['files']
        y = project_stats['years']
        video_s = get_plural('video', count=v)
        years_s = get_plural('year', count=y)
        st.markdown(f'**Submitted**: {v} {video_s}')
        st.markdown(f'**Participated for**: {y} {years_s}')
    if project_stats.get('appearances'):
        r = project_stats['appearances']
        review_s = get_plural('review', count=r)
        st.markdown(f'**Appeared in**: {r} {review_s}')

    # location information
    contact_info = information['contact_info'].iloc[0]
    zip_code = contact_info.get('zip_code')
    if zip_code:
        location_data = plot_map(zip_code)
        st.map(location_data, height=300, zoom=10)

def fill_lineage(information, members, member_type, sex, is_future):
    future = 'Future ' if is_future else ''

    if member_type == 'person':
        # ancestry information
        parents = information['parent_ids'].iloc[0]
        if parents:
            child_name = get_gendered_name('child', sex)
            get_list_display(members, parents, f'**{future}{child_name} of**:')

        # spousal information
        spouse = information['spouse_ids'].iloc[0]
        if spouse:
            spouse_name = get_gendered_name('spouse', sex)
            get_list_display(members, spouse, f'**{spouse_name} of**:')

        # descendants information
        children = information['child_ids'].iloc[0]
        if children:
            parent_name = get_gendered_name('parent', sex)
            get_list_display(members, children, f'**{parent_name} of {len(children)}**:')

        expecting = information['expecting_ids'].iloc[0]
        if expecting:
            expecting_name = get_gendered_name('expecting', sex)
            get_list_display(members, expecting, f'**{expecting_name}**:')

        pets = information['pet_ids'].iloc[0]
        if pets:
            get_list_display(members, pets, '**Owner of**:')

        # siblings information
        siblings = information['sibling_ids'].iloc[0]
        if siblings:
            sibling_name = get_gendered_name('sibling', sex)
            get_list_display(members, siblings, f'**{future}{sibling_name} of**:')


    elif member_type == 'animal':
        # ownership information
        owners = information['owner_ids'].iloc[0]
        if owners:
            get_list_display(members, owners, '**Pet of**:')


def fill_in_bio(engine, cloud_name, members, information, member_type, member_id):
    sex = information['sex'].iloc[0]

    birth_date = information['birth_date'].iloc[0]
    birth_date_precision = information['birth_date_precision'].iloc[0]
    is_future = ((birth_date is None or birth_date > date.today()) or birth_date_precision == 'future')

    death_date = information['death_date'].iloc[0]
    death_date_precision = information['death_date_precision'].iloc[0]
    is_deceased = ((death_date is not None and death_date > date.today()) or death_date_precision == 'past')

    cols = st.columns(3)
    with cols[0]:
        fill_image(engine, cloud_name, members, member_type, member_id)

    with cols[1]:
        fill_personal(information, member_type, sex, is_future, is_deceased)

    with cols[2]:
        fill_lineage(information, members, member_type, sex, is_future)

