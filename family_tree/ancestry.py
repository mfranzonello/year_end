from collections import deque
from uuid import UUID
from datetime import date, timedelta

from pandas import concat, DataFrame, isna, notna
from sqlalchemy import Engine

from database.db_family import fetch_members, fetch_parents, fetch_pets, fetch_spouses

def get_member_data(engine:Engine) -> DataFrame:
    members = fetch_members(engine)
    return members

def get_map_data(engine:Engine) -> tuple[DataFrame, DataFrame, DataFrame]:
    parents = fetch_parents(engine)
    pets = fetch_pets(engine)
    spouses = fetch_spouses(engine)
    return parents, pets, spouses

def create_maps(parents:DataFrame, pets:DataFrame, spouses:DataFrame) -> tuple[dict, dict, dict]:
    relation_df = concat([parents.rename(columns={'child_id': 'below_id', 'parent_id': 'above_id'}),
                          pets.rename(columns={'pet_id': 'below_id', 'owner_id': 'above_id'})])
    ancestors_map = relation_df.groupby('below_id').agg(list).to_dict()['above_id']
    descendants_map = relation_df.groupby('above_id').agg(list).to_dict()['below_id']
    spouses_map = spouses.set_index('person_id').to_dict()['spouse_id']
    return ancestors_map, descendants_map, spouses_map

def get_lineage(start_id:UUID, relation_map:dict, spouses_map:dict, direction:int):
    lineage = {start_id: (0, False)}   # distance, via_spouse
    queue = deque([start_id])

    while queue:
        curr = queue.popleft()
        dist, via_spouse = lineage[curr]

        # parents / owners grow upward
        for p in relation_map.get(curr, []):
            if p not in lineage:
                lineage[p] = (dist + direction, via_spouse)  # same spouse flag
                queue.append(p)

        # spouses stay same level but mark branch as “via spouse”
        s = spouses_map.get(curr)
        if s and (s not in lineage):
            lineage[s] = (dist, True)
            queue.append(s)

    return lineage

def get_ancestors_and_descendants(member_id:UUID, parents:DataFrame, pets:DataFrame, spouses:DataFrame) -> tuple[dict, dict]:
    ancestors_map, descendants_map, spouses_map = create_maps(parents, pets, spouses)
    ancestors = get_lineage(member_id, ancestors_map, spouses_map, direction=-1)
    descendants = get_lineage(member_id, descendants_map, spouses_map, direction=1)
    return ancestors, descendants

def nearest_common_lineage(member_id_1:UUID, member_id_2:UUID, relation_map:dict, spouses_map:dict, direction:int):
    lin_1 = get_lineage(member_id_1, relation_map, spouses_map, direction)
    lin_2 = get_lineage(member_id_2, relation_map, spouses_map, direction)

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

def get_relatives(member_id:UUID, members:DataFrame, parents:DataFrame, pets:DataFrame, spouses:DataFrame,
                    include_animals:bool=False, cut_date:date|None=date.today(), include_deceased=True) -> DataFrame:
    ancestors, descendents = get_ancestors_and_descendants(member_id, parents, pets, spouses)
    
    relatives = (DataFrame.from_dict({**ancestors, **descendents},
                                        orient='index',
                                        columns=['generation', 'in-law']).reset_index(names='member_id')
                    .merge(members, on='member_id')
    )
    if not include_animals:
        relatives = relatives[relatives['member_type']!='animal']
    if cut_date:
        relatives['born'] = relatives.apply(lambda x: (notna(x['birth_date']) and (x['birth_date'].date() <= cut_date)) or 
                                            (x['birth_date_precision']=='past'), axis=1)

        relatives['entered'] = relatives.apply(lambda x: ((not x['in-law']) & (not x['member_type']=='animal')) or
                                               (notna(x['entry_date']) and (x['entry_date'].date() <= cut_date)) or 
                                               (x['entry_date_precision']=='past'), axis=1)
        relatives = relatives[relatives['born'] & relatives['entered']].drop(['born', 'entered'], axis=1)
    if not include_deceased:
        relatives['alive'] = relatives.apply(lambda x: (notna(x['death_date']) and (x['death_date'].date() >= cut_date)) or 
                                            (isna(x['death_date']) and (x['death_date_precision']!='past')), axis=1)
        relatives = relatives[relatives['alive']].drop(['alive'], axis=1)

    return relatives

def list_relatives(engine:Engine, founder_id:UUID, include_animals=False, cut_date:date|None=None, include_deceased=False) -> DataFrame:
    members = get_member_data(engine)
    parents, pets, spouses = get_map_data(engine)
    relatives = get_relatives(founder_id, members, parents, pets, spouses,
                              include_animals=include_animals, cut_date=cut_date, include_deceased=include_deceased)
    return relatives