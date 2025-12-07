from collections import deque
from uuid import UUID
from datetime import date

from pandas import concat, DataFrame
from sqlalchemy import Engine

from database.db_family import fetch_members, fetch_parents, fetch_pets, fetch_spouses

def get_member_data(engine:Engine) -> tuple[DataFrame]:
    members = fetch_members(engine)
    return members

def get_map_data(engine:Engine):
    parents = fetch_parents(engine)
    pets = fetch_pets(engine)
    spouses = fetch_spouses(engine)
    return parents, pets, spouses

def create_maps(parents, pets, spouses) -> tuple[DataFrame]:
    relation_df = concat([parents.rename(columns={'child_id': 'lower_id', 'parent_id': 'above_id'}),
                          parents.rename(columns={'child_id': 'lower_id', 'parent_id': 'above_id'})])
    ancestors_map = relation_df.groupby('lower_id').agg(list).to_dict()
    descendants_map = relation_df.groupby('lower_id').agg(list).to_dict()
    spouses_map = spouses.set_index('person_id').to_dict()
    return ancestors_map, descendants_map, spouses_map

def get_lineage(start_id, relation_map, spouses_map):
    lineage = {start_id: (0, False)}   # distance, via_spouse
    queue = deque([start_id])

    while queue:
        curr = queue.popleft()
        dist, via_spouse = lineage[curr]

        # parents / owners grow upward
        for p in relation_map.get(curr, []):
            if p not in lineage:
                lineage[p] = (dist + 1, via_spouse)  # same spouse flag
                queue.append(p)

        # spouses stay same level but mark branch as “via spouse”
        for s in spouses_map.get(curr, []):
            if s not in lineage:
                lineage[s] = (dist, True)
                queue.append(s)

    return lineage

def get_ancestors_and_descendants(member_id, parents, pets, spouses):
    ancestors_map, descendants_map, spouses_map = create_maps(parents, pets, spouses)
    ancestors = get_lineage(member_id, ancestors_map, spouses_map)
    descendants = get_lineage(member_id, descendants_map, spouses_map)
    return ancestors, descendants

def nearest_common_lineage(member_id_1, member_id_2, relation_map, spouses_map):
    lin_1 = get_lineage(member_id_1, relation_map, spouses_map)
    lin_2 = get_lineage(member_id_2, relation_map, spouses_map)

    common = set(lin_1.keys()) & set(lin_2.keys())
    if not common:
        return None  # unrelated

    # Pick the NCL by minimizing total distance
    best = min(common, key=lambda a: (lin_1[a] + lin_2[a], max(lin_1[a], lin_2[a])))

    return {'lineage_id': best,
            'dist_id_1': lin_1[best][0],
            'dist_id_2': lin_2[best][0],
            'in-law': not(lin_1[best][1] and lin_2[best][1]) # related by spouse
            }

def get_relatives(member_id:UUID, members:DataFrame,
                  parents:DataFrame, pets:DataFrame, spouses:DataFrame,
                  include_animals:bool=False, cut_year:int=None) -> list[UUID]:
    members_to_search = deque([member_id])

    relatives_found = []
    inlaws_found = []

    while len(members_to_search):
        current_id = members_to_search.pop()
        if current_id not in relatives_found:
            spouse_id = spouses.query('person_id == @current_id')['spouse_id']
            children_ids = parents.query('parent_id == @current_id')['child_id']
            parent_ids = parents.query('child_id == @current_id')['parent_id']

            possible_ids = [children_ids, parent_ids]

            if include_animals:
                owner_ids = pets.query('pet_id == @current_id')['owner_id']
                pet_ids = pets.query('owner_id == @current_id')['pet_id']
                possible_ids.extend([owner_ids, pet_ids])
            

            bloodline = [r_id for r_id in concat(possible_ids).tolist()
                         if r_id not in relatives_found and r_id != current_id]
            inlaws = [spouse_id]
            relatives = [r_id for r_id in concat([spouse_id] + possible_ids).tolist() \
                if r_id not in relatives_found and r_id != current_id]
        
            members_to_search.extend(relatives)
            relatives_found.append(current_id)
            inlaws_found.append(spouse_id)

    allowed_types = ['person']
    if include_animals:
        allowed_types.append('animal')
    relevant_members = members.query('member_type in @allowed_types')

    if cut_year:
        last_birth = cut_year + 1
        last_death = cut_year
        relevant_members = relevant_members.query(
            '(birth_date.dt.year < @last_birth) & ((death_date.dt.year >= @last_death) | death_date.isnull())'
            )
        relatives_found = [r for r in relatives_found if r in relevant_members['member_id'].tolist()]

    return relatives_found

def list_relatives(engine:Engine, founder_id:UUID, include_animals=False, cut_year=None) -> list[UUID]:
    members = get_member_data(engine)
    parents, pets, spouses = get_map_data(engine)
    return get_relatives(founder_id, members, parents, pets, spouses, include_animals=include_animals, cut_year=cut_year)