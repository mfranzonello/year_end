"""Render member biography details, with administrator-only image replacement."""

from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

import streamlit as st
from pgeocode import Nominatim
from pandas import DataFrame, Series

from database.db import Engine
from pages.streamlit_auth import current_tier, require_admin
from pages.general import get_member_name_display
from charting.cloudy import get_version, get_image_url, upload_image, CloudConfig
from charting.general import get_flag

nomi = Nominatim('us')

def go_to_member(member_id):
    st.session_state.member_id = member_id
    st.session_state.member_select = member_id

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
            st.button(get_member_name_display(members, list_id), type='secondary',
                      on_click=go_to_member, args=(list_id, ), key=f'member_{list_id}')

def get_plural(word:str, count:int=None, items:list=None, s:str='s', plural:str=None):
    if plural is None:
        plural = word + s

    if count is not None:
        quantity = count
    elif items is not None:
        quantity = len(items)

    return plural if (quantity != 1) else word

def get_location(zip_code: int):
    return nomi.query_postal_code(zip_code)

def get_location_data(location: Series):
    location_data = DataFrame([[location.latitude, location.longitude]], columns=('lat', 'lon'))
    return location_data

def plot_map(zip_code, height=300, width=350, zoom=10, markdown=None):
    location = get_location(zip_code)
    location_data = get_location_data(location)

    markdown_text = f'**{markdown}**: ' if markdown else ''
    st.markdown(f'{markdown_text}{location.place_name}, {location.state_code}')
    st.map(location_data, height=height, width=width, zoom=zoom)

def fill_image(engine:Engine, cloud:CloudConfig, members, member_type, member_id):
    # member image
    image_url = get_image_url(engine, cloud, member_id, profile_type=member_type, square=True)
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
                upload_image(engine, public_id=member_id, image_path=replace_image_path, display_name=display_name)
                st.session_state['image_replacement_key'] += 1
                get_version.clear(engine, member_id)
                st.rerun()

def fill_personal(information, member_type, sex, is_future, is_deceased):
    # born and living marker
    (birth_date, birth_date_precision,
     death_date, death_date_precision,
     first_name, middle_names,
     nick_name, 
     origin_region_code, project_stats,
     contact_info,
     ) = information[[
         'birth_date', 'birth_date_precision',
         'death_date', 'death_date_precision',
         'first_name', 'middle_names',
         'nick_name',
         'origin_region_code', 'project_stats',
         'contact_info',
         ]].iloc[0]
    
    match member_type:
        case 'person':
            (last_name, married_name,
             union_date, union_date_precision, severance_date,
             ) = information[[
                 'last_name', 'married_name',
                 'union_date', 'union_date_precision', 'severance_date',
                 ]].iloc[0]
        case 'animal':
            (species,
             gotcha_date, gotcha_date_precision,
             ) = information[[
                 'species',
                 'gotcha_date', 'gotcha_date_precision',
                 ]].iloc[0]

    if is_deceased:
        st.markdown(f'*Deceased*')
    if is_future:
        st.markdown('*Unborn*')

    if death_date:
        cut_date = min(death_date, date.today())
        cut_date_precision = death_date_precision
    else:
        cut_date = date.today()
        cut_date_precision = 'day'

    # name information
    if first_name:
        st.markdown(f'**First Name**: {first_name}')
    if nick_name:
        st.markdown(f'**Nickname**: "{nick_name}"')
    if middle_names:
        m_names = middle_names.split(';')
        m_names_all = ' '.join(m_names)
        st.markdown(f'**Middle {get_plural("Name", items=m_names)}**: {m_names_all}')
    if member_type == 'person':
        if married_name and married_name != last_name:
            nee_name = get_gendered_name('nee', sex)
            st.markdown(f'**{nee_name} Name**: {last_name}')
            st.markdown(f'**Last Name**: {married_name}')
        else:
            st.markdown(f'**Last Name**: {last_name}')

    # birth and death information
    emoji_flag = get_flag(origin_region_code)
    if emoji_flag:
        st.markdown(f'**Origin**: {emoji_flag}')

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
        if species:
            species_name = get_specied_name(species)
            st.markdown(f'**Species**: {species_name}')

    gender = get_gender(sex)
    st.markdown(f'**Gender**: {gender}')

    if member_type == 'person':
        if union_date:
            anniversary = get_date_display(union_date, union_date_precision)
            st.markdown(f'**Anniversary**: {anniversary}')

            if severance_date is not None:
                cut_date_2 = min(severance_date, cut_date)
            else:
                cut_date_2 = cut_date
            marriage_span = get_time_passed_display(union_date, union_date_precision, cut_date_2)
            st.markdown(f'**Married for**: {marriage_span}')

    if member_type == 'animal':
        if gotcha_date is not None:
            adoption = get_date_display(gotcha_date, gotcha_date_precision)
            st.markdown(f'**Adopted on**: {adoption}')
            if death_date_precision != 'past':
                owned_span = get_time_passed_display(gotcha_date, gotcha_date_precision, cut_date, cut_date_precision)
                st.markdown(f'**Owned for**: {owned_span}')

    # project information
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
    zip_code = contact_info.get('zip_code')
    if zip_code:
        plot_map(zip_code, markdown='Lives near')

def fill_lineage(information, members, member_type, sex, is_future):
    future = 'Future ' if is_future else ''

    (parents, children, siblings,
     ) = information[[
         'parent_ids', 'child_ids', 'sibling_ids'
         ]].iloc[0]

    match member_type:
        case 'person':
            (spouse, expecting, pets,
             ) = information[[
                 'spouse_ids', 'expecting_ids', 'pet_ids'
                 ]].iloc[0]

        case 'animal':
            (owners,
             ) = information[[
                 'owner_ids',
                 ]].iloc[0]

    # ancestry information
    if parents:
        child_name = get_gendered_name('child', sex)
        get_list_display(members, parents, f'**{future}{child_name} of**:')

    if member_type == 'person':
        # spousal information
        if spouse:
            spouse_name = get_gendered_name('spouse', sex)
            get_list_display(members, spouse, f'**{spouse_name} of**:')

    # descendants information
    if children:
        parent_name = get_gendered_name('parent', sex)
        get_list_display(members, children, f'**{parent_name} of {len(children)}**:')

    if member_type == 'person':
        if expecting:
            expecting_name = get_gendered_name('expecting', sex)
            get_list_display(members, expecting, f'**{expecting_name}**:')

        if pets:
            get_list_display(members, pets, '**Owner of**:')

        # siblings information
        if siblings:
            sibling_name = get_gendered_name('sibling', sex)
            get_list_display(members, siblings, f'**{future}{sibling_name} of**:')


    elif member_type == 'animal':
        # ownership information
        if owners:
            get_list_display(members, owners, '**Pet of**:')