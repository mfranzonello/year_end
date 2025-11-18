from math import ceil
from collections import deque
from uuid import UUID
from datetime import date
from dateutil.relativedelta import relativedelta
from calendar import monthrange
from collections import deque, defaultdict

from graphviz import Graph
from pandas import notnull, concat, DataFrame, Series

from family_tree.db import fetch_persons, fetch_animals, fetch_parents, fetch_pets, fetch_marriages
from family_tree.cloudinary_lite import get_image_url

def create_maps(parents, pets, spouses):
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

def get_tree_data(engine):
    persons = fetch_persons(engine)
    animals = fetch_animals(engine)
    parents = fetch_parents(engine)
    pets = fetch_pets(engine)
    marriages = fetch_marriages(engine)
    return persons, animals, parents, pets, marriages

def get_spouses(marriages:DataFrame) -> DataFrame:
    spouses = concat([marriages[['husband_id', 'wife_id', 'marriage_id']].rename(columns={'husband_id': 'person_id', 'wife_id': 'spouse_id'}),
                      marriages[['wife_id', 'husband_id', 'marriage_id']].rename(columns={'wife_id': 'person_id', 'husband_id': 'spouse_id'})])
    return spouses

def get_unit_spouses(unit:list[UUID], spouses:DataFrame):
    unit_sorting = {u: unit.index(u) for u in unit}
    unit_spouses = spouses.sort_values(by='person_id', key=lambda x: x.map(unit_sorting)).groupby('marriage_id').first().reset_index()
    return unit_spouses

def get_relatives(member_id:UUID, persons:DataFrame, animals:DataFrame, parents:DataFrame, pets:DataFrame, spouses:DataFrame) -> list[UUID]:
    members_to_search = deque([member_id])

    bloodline = []
    inlaws = []

    relatives_found = []

    while len(members_to_search):
        current_id = members_to_search.pop()
        if current_id not in relatives_found:
            spouse_id = spouses.query('person_id == @current_id')['spouse_id']
            children_ids = parents.query('parent_id == @current_id')['child_id']
            parent_ids = parents.query('child_id == @current_id')['parent_id']
            owner_ids = pets.query('pet_id == @current_id')['owner_id']
            pet_ids = pets.query('owner_id == @current_id')['pet_id']
            
            bloodline = [r_id for r_id in concat([children_ids, parent_ids, owner_ids, pet_ids]).tolist()
                         if r_id not in relatives_found and r_id != current_id]
            relatives = [r_id for r_id in concat([spouse_id, children_ids, parent_ids, owner_ids, pet_ids]).tolist() \
                if r_id not in relatives_found and r_id != current_id]
        
            members_to_search.extend(relatives)
            relatives_found.append(current_id)

    return relatives_found

def get_bloodline(member_id:UUID, relatives_found:list[UUID]):
    return

def get_node(member_id:UUID, parents:DataFrame, pets:DataFrame, spouses:DataFrame) -> UUID:

    if member_id in parents['child_id'].values:
        potential_id = parents.query('child_id == @member_id')['parent_id'].iloc[0]
    elif member_id in pets['pet_id'].values:
        potential_id = pets.query('pet_id == @member_id')['owner_id'].iloc[0]
    else:
        # no parent or owner
        return None
    
    # has at least one parent or owner, check if married
    if potential_id in spouses['person_id'].values:
        # parent is married
        node_id = spouses.query('person_id == @potential_id')['marriage_id'].iloc[0]
    else:
        # parent is single
        node_id = potential_id
    
    return node_id

def get_nodes(persons:DataFrame, animals:DataFrame, parents:DataFrame, pets:DataFrame, spouses:DataFrame) -> DataFrame:
    nodes = DataFrame(data=parents['child_id'].tolist() + pets['pet_id'].tolist(),
                      columns=['member_id']).drop_duplicates()
  
    nodes['node_id'] = nodes.apply(lambda x: get_node(x['member_id'], parents, pets, spouses), axis=1)

    return nodes

def get_generations():
    return

def convert_date(d:date, precision:str):
    match precision:
        case 'past':
            return date.min # earliest date
        case 'future':
            return date.max - relativedelta(days=1) # latest date - 1
        case 'day':
            return date(d.year, d.month, d.day) # actual day
        case 'month':
            return date(d.year, d.month, monthrange(d.year, d.month)[1]) # last day of month
        case 'year':
            return date(d.year + 1, 1, 1) - relativedelta(days=1) # last day of year
        case _:
            return date.max # latest date

def get_entry_date(member_id:UUID, persons:DataFrame, pets:DataFrame) -> date:
    if member_id in persons['person_id'].values:
        potential_date, precision = persons.query('person_id == @member_id')[['birth_date', 'birth_date_precision']].iloc[0]
    elif member_id in pets['pet_id'].values:
        potential_date, precision = pets.query('pet_id == @member_id')[['gotcha_date', 'gotcha_date_precision']].iloc[0]

    entry_date = convert_date(potential_date, precision)
    return entry_date

def get_sorted_units(relatives_found, nodes, persons, pets, spouses):
    sorted_units = []
    members_to_search = deque(relatives_found)

    while len(members_to_search):
        current_id = members_to_search.popleft()
        unit = [current_id]

        node = nodes.query('member_id == @current_id')['node_id']
        if not node.empty:
           node_id = node.iloc[0]
           if notnull(node_id):
                # get siblings
                siblings = nodes.query('node_id == @node_id & member_id != @current_id')['member_id']
                unit.extend(siblings)

        # sort by birth/gotcha -> add alternate function if moving pets second
        unit.sort(key=lambda x_id: get_entry_date(x_id, persons, pets))

        full_unit = []   
        for sibling_id in unit:
            full_unit.append(sibling_id)

            ### consider skipping this and only do at time of unit addition
            spouse = spouses.query('person_id == @sibling_id')
            if not spouse.empty:
                full_unit.append(spouse['spouse_id'].iloc[0])
            ###

        for member_id in full_unit:
            if member_id != current_id:
                members_to_search.remove(member_id)

        sorted_units.append(full_unit)

        ##print(f'{full_unit}')
        ##names = [persons.query('person_id == @m_id')['first_name'].iloc[0] for m_id in full_unit if m_id in persons['person_id'].values]
        ##input(f'\n\nFull Unit: {names}\n\n')

    return sorted_units

def to_roman_numeral(num):
    # List of tuples with integer values and their Roman numeral symbols
    val_map = [
        (1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
        (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
        (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')
    ]
    
    roman_num = ''
    for val, symbol in val_map:
        # Use divmod to find how many times the symbol should be repeated
        # and update the number with the remainder
        count, num = divmod(num, val) 
        roman_num += symbol * count
    return roman_num

def get_suffix(num:int):
    if isinstance(num, int) and num > 0:
        match num:
            case 1:
                s = 'Sr'
            case 2:
                s = 'Jr'
            case _:
                s = to_roman_numeral(num)
        return f' {s}'

    else:
        return ''

def get_person_name(person_s:Series) -> str:
    if person_s['birth_date_precision'].iloc[0] == 'future' or person_s['birth_date'].iloc[0].date() > date.today():
        first_name = '<new baby>'
    else:
        first_name = person_s['nick_name'].iloc[0] or person_s['first_name'].iloc[0]
    last_name = person_s['last_name'].iloc[0] + get_suffix(person_s['suffix'].iloc[0])
    return f'{first_name}\n{last_name}'

def get_animal_name(animal_s:Series) -> str:
    first_name = animal_s['nick_name'].iloc[0] or animal_s['first_name'].iloc[0]
    species_name = animal_s['species'].iloc[0]
    return f'{first_name}'

def sort_family_tree(founder_id:UUID, persons:DataFrame, animals:DataFrame, parents:DataFrame, pets:DataFrame, marriages:DataFrame,
                     cloud_name:str) -> Graph:
    ## choose whether to allow 'rooted', 'founder', 'born', 'married', 'pet' and 'preborn'
    SHAPE_PERSON = 'rectangle'
    SHAPE_ANIMAL = 'oval'

    COLOR_MALE = 'cornflowerblue'
    COLOR_FEMALE = 'deeppink1'

    male_attributes = {'shape': SHAPE_PERSON, 'color': COLOR_MALE}
    female_attributes = {'shape': SHAPE_PERSON, 'color': COLOR_FEMALE}                          
    hidden_attributes = {'label': '', 'shape': 'point', 'width': '0', 'height': '0', 'pendwidth': '0'}

    ## deceased indicator?

    spouses = get_spouses(marriages)
    
    relatives_found = get_relatives(founder_id, persons, animals, parents, pets, spouses)
    nodes = get_nodes(persons, animals, parents, pets, spouses)
    sorted_units = get_sorted_units(relatives_found, nodes, persons, pets, spouses)

    tree = Graph()
    ##tree.attr(splines='polyline')

    subtrees = []

    for unit in sorted_units:
        subtree = Graph()
        subtree_a = Graph()
        subtree_a.attr(rank='same')

        subtree_b = Graph()
        subtree_b.attr(rank='same')

        unit_spouses = get_unit_spouses(unit, spouses)
        # add nodes for members
        for member_id in unit:
            p = persons.query('person_id == @member_id')
            a = animals.query('animal_id == @member_id')
            image = get_image_url(member_id, cloud_name)

            if not p.empty:
                ##member_id in persons['person_id'].values
                
                subtree_a.node(str(member_id), label=get_person_name(p), image=image,
                               **male_attributes)
                ## image=''
            elif not a.empty: #member_id in animals['animal_id'].values:
                subtree_b.node(str(member_id), label=get_animal_name(a))

            # add nodes for weddings after first spouse
            if member_id in unit_spouses['person_id'].values: # <- only need to add only_once
                spouse = spouses.query('person_id == @member_id')
                marriage_id = spouses['marriage_id'].iloc[0]
                subtree_a.node(str(marriage_id), **hidden_attributes)

                ### consider adding spouses here
                # # spouse_id = spouses['spouse_id'].iloc[0]
                # # s = persons.query('person_id == @spouse_id')
                # # subtree_a.node(str(spouse_id), label=get_person_name(s))


            # add nodes for weddings after first spouse
            if member_id in unit_spouses['person_id'].values: # <- only need to add only_once
                marriage_id = unit_spouses.query('person_id == @member_id')['marriage_id'].iloc[0]
                subtree_a.node(str(marriage_id), **hidden_attributes)

            subtree.subgraph(subtree_a)
            subtree.subgraph(subtree_b)

        # add edges for marriages and siblings
        for i, member_id in enumerate(unit[:-1]):

            ### change to just spouses
            if member_id in unit_spouses['person_id'].values: #<- only do this for the first spouse

                ### consider dropping this for below
                marriage_id = unit_spouses.query('person_id == @member_id')['marriage_id'].iloc[0]
                subtree.edge(str(member_id), str(marriage_id))
                subtree.edge(str(marriage_id), str(unit[i+1]))

                ### consider this instead, if in-laws are not in unit
                # # spouse = spouses.query('person_id == @member_id')
                # # spouse_id, marriage_id = spouse[['spouse_id', 'marriage_id']].iloc[0]
                # # subtree.edge(str(member_id), str(marriage_id))
                # # subtree.edge(str(marriage_id), str(spouse_id))
                # # subtree.edge(str(spouse_id), str(unit[i+1]), style='invis')

            else:
                subtree.edge(str(member_id), str(unit[i+1]), style='invis')

        subtrees.append(subtree)

    for subtree in subtrees:
        tree.subgraph(subtree)

    # add edges from heads to nodes
    for node_id in nodes['node_id'].unique():
        tree.node(f'+{node_id}', **hidden_attributes)
        tree.edge(str(node_id), f'+{node_id}')

    # add edges from nodes to descendants
    for _, (member_id, node_id) in nodes[['member_id', 'node_id']].iterrows():
        tree.edge(f'+{node_id}', str(member_id))

    ###
    # add edges from nodes in the same generation by order
    ###

    # # # add invisible edges for parents and owners
    # # for _, (parent_id, child_id) in parents[['child_id', 'parent_id']].iterrows():
    # #     tree.edge(str(parent_id), str(child_id), style='invis')
    # # for _, (owner_id, pet_id) in pets[['pet_id', 'owner_id']].iterrows():
    # #     tree.edge(str(owner_id), str(pet_id), style='invis')

    return tree

def create_tree(engine, founder_id:UUID, cloud_name:str):
    persons, animals, parents, pets, marriages = get_tree_data(engine)

    tree = sort_family_tree(founder_id, persons, animals, parents, pets, marriages, cloud_name)

    return tree