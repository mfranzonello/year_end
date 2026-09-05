from math import ceil
from uuid import UUID

from graphviz import Graph
from pandas import DataFrame, isna
from pandas.api.types import is_list_like
from webcolors import name_to_hex

from family_tree.cloudinary_lite import get_image_url, get_image_path

def get_color_hexes(color_names:list[str]) -> list[str]:
    return [name_to_hex(c) for c in color_names]

def get_color_rgb_hex(color_name:str) -> str:
    return name_to_hex(color_name).replace('#', 'rgb:')

def get_person_label(node) -> str:
    return (node['first_name'] if node['first_name'] else ('< baby >')) + '\\n' + node['last_name']

def get_animal_label(node) -> str:
    return node['first_name'] + '\\nthe ' + node['species']

def get_union_label(node) -> str:
    return

def get_attributes(node, use_images=False) -> str:
    SHAPE_PERSON = 'rectangle'
    SHAPE_ANIMAL = 'ellipse'

    COLOR_MALE = 'cornflowerblue'
    COLOR_FEMALE = 'deeppink1'
    COLOR_NEUTER = 'azure3'

    match node['node_type']:
        case 'junction':
            attributes = {'shape': 'point', 'width': '0', 'height': '0', 'pendwidth': '0'}
        case 'person' | 'animal':
            if use_images:
                shape = 'square'
                #attributes = {'shape': 'square', 'width': '1'}

            else:
                match node['node_type']:
                    case 'person':
                        shape = SHAPE_PERSON
                    case 'animal':
                        shape = SHAPE_ANIMAL
                    case _:
                        shape = 'point'

            match node['sex']:
                case 'm':
                    color = COLOR_MALE
                case 'f':
                    color = COLOR_FEMALE
                case _:
                    color = COLOR_NEUTER

            attributes = {'shape': shape, 'color': color}

    return attributes

def find_boundaries(tree_data:DataFrame) -> DataFrame:
    """Assign contiguous family blocks using overlapping visible parent sets."""
    tree_data['family_unit'] = -1
    visible_ids = set(tree_data['node_id'])
    family_unit = -1

    ordered = tree_data.sort_values(['generation', 'x_order'])
    for _, generation in ordered.groupby('generation', sort=False):
        tracked_parents:set[UUID] = set()

        for _, unit in generation.groupby('unit_order', sort=False):
            current_parents:set[UUID] = set()
            for value in unit['parent_ids']:
                current_parents.update(_visible_parent_ids(value, visible_ids))

            if family_unit < 0 or (
                    current_parents
                    and tracked_parents.isdisjoint(current_parents)):
                family_unit += 1
                tracked_parents = set(current_parents)
            else:
                tracked_parents.update(current_parents)

            tree_data.loc[unit.index, 'family_unit'] = family_unit

    return tree_data

def _visible_parent_ids(value:object, visible_ids:set[UUID]) -> set[UUID]:
    """Normalize a PostgreSQL UUID array and omit undiscovered parents."""
    if value is None:
        return set()
    values = value if is_list_like(value) and not isinstance(value, str) else [value]
    return {parent_id for parent_id in values
            if not isna(parent_id) and parent_id in visible_ids}

def find_display_generations(tree_data:DataFrame, generation_limit:int) -> DataFrame:
    """Stagger complete families and rebuild cross-family ordering tails."""
    if generation_limit < 1:
        raise ValueError('generation_limit must be at least 1.')

    tree_data['display_generation'] = tree_data['generation'].astype(float)

    subgenerations = []
    for generation_value in tree_data['generation'].unique():
        generation = tree_data[(tree_data['generation'] == generation_value)
                               & (tree_data['node_type'] != 'junction')]
        if len(generation) > generation_limit:
            subgenerations.append(generation_value)

        family_ids = generation.sort_values('x_order')['family_unit'].unique() #.drop_duplicates().tolist()
        display_rows = max(1, ceil(len(generation) / generation_limit))
        family_rows = {
            family_id: position % display_rows
            for position, family_id in enumerate(family_ids)
        }

        for family_id, display_row in family_rows.items():
            mask = ((tree_data['generation'] == generation_value)
                    & (tree_data['family_unit'] == family_id))
            tree_data.loc[mask, 'sub_generation'] = (
                float(generation_value) + (display_row / display_rows)
            )

    tree_data['is_subgeneration'] = tree_data['generation'].isin(subgenerations)
    tree_data['display_generation'] = tree_data['sub_generation'].rank(method='dense').astype(int)

    ##tree_data.loc[tree_data['node_type'] == 'animal', 'display_generation'] += 1/(2*display_rows)
    ##tree_data['edge_constraint'] = tree_data['display_generation'] == tree_data['display_generation'].shift(-1)

    return tree_data

def find_parent_nodes(subgeneration_nodes):
    return set(node['head_id'] for _, node in subgeneration_nodes.iterrows() if node['head_id'] is not None)

def find_filler_nodes(all_parent_nodes, found_parent_nodes):
    return set(node_id for node_id in all_parent_nodes if node_id not in found_parent_nodes)

def find_vertical_route(start_node, end_node, style:str=None):
    g_range = range(start_node['display_generation'] - 1, end_node['display_generation'] + 1)
    
    start_str = str(start_node['node_id'])
    middle_str = [f'{g}:{end_node["node_id"]}' for g in g_range]
    end_str = str(end_node['node_id'])
    
    connectors = [start_str] + middle_str + [end_str]
    edges = [(connectors[i], connectors[i+1], style) for i in range(len(connectors)-1)]

    return edges

def find_horizontal_route(start_node, end_node, parent_nodes, style:str=None):
    p_range = parent_nodes[parent_nodes.index(start_node['head_id']) + 1 : parent_nodes.index(end_node['head_id'])]

    start_str = str(start_node['node_id'])
    middle_str = [f'{start_node["display_generation"]}:{p}' for p in p_range]
    end_str = str(end_node['node_id'])

    connectors = [start_str] + middle_str + [end_str]
    edges = [(connectors[i], connectors[i+1], style) for i in range(len(connectors)-1)]

    return edges

''' main family tree charts '''
def tree_chart(tree_data:DataFrame, cloud_name:str, use_images=False, generation_limit:int=None) -> Graph:
    
    tree = Graph()
    ##tree.attr(splines='ortho')
    tree.graph_attr['bgcolor'] = 'transparent'
    ##tree.graph_attr['rankdir'] = 'LR'

    tree_data = find_boundaries(tree_data)
    tree_data = find_display_generations(tree_data, generation_limit)
    subgeneration_mapping = tree_data[['display_generation', 'generation', 'is_subgeneration']]\
        .groupby(['display_generation']).first().to_dict()
    
    for g in tree_data['display_generation'].unique():
        tree_data_g = tree_data[tree_data['display_generation']==g]

        subtree = Graph()
        subtree.attr(rank='same')

        # add normal nodes
        for _, node in tree_data_g.iterrows():
            node_type = node['node_type']
            if node_type in ['person', 'animal']:
                if use_images:
                    image = get_image_path(cloud_name, str(node['node_id']))
                    label = ''
                else:
                    image = None
                    if node_type == 'person':
                        label = get_person_label(node)
                    else:
                        label = get_animal_label(node)

            else:
                if use_images:
                    label = ''
                else:
                    label = node['clan_name']
                image = None

            attributes = get_attributes(node, use_images)

            subtree.node(str(node['node_id']), label=label, image=image, tooltip=label, **attributes)

        # add routing nodes
        if subgeneration_mapping['is_subgeneration'][g]:
            original_g = subgeneration_mapping['generation'][g]
            all_parent_nodes = find_parent_nodes(tree_data[tree_data['generation']==original_g])
            found_parent_nodes = find_parent_nodes(tree_data_g)
            routing_nodes = find_filler_nodes(all_parent_nodes, found_parent_nodes)
             
            for node in routing_nodes:
                subtree.node(f'{g}:{node}', shape='point', width='0', height='0', style='invis')
                pass

        tree.subgraph(subtree)

    # add edges
    edges = []

    # add horizontal edges
    for _, node in tree_data[tree_data['tail_id'].notna()].iterrows():
        match node['tail_type']:
            case 'order':
                style = 'invis'
            case 'union':
                style = None
            case _:
                style = 'invis'

        edges.append((str(node['node_id']), str(node['tail_id']), style))

    # add vertical edges
    for _, node in tree_data[tree_data['head_id'].notna()].iterrows():
        ##edges.append(find_vertical_route(node, tree_data[tree_data['node_id']==node['head_id']].iloc[0], style=None))
        edges.append((str(node['head_id']), str(node['node_id']), None))

    # replace problematic edges

    # add edges
    for edge in edges:
        tree.edge(edge[0], edge[1], style=edge[2]) # constraint = True?

    return tree