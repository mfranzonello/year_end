from math import ceil
from itertools import pairwise
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
    result = tree_data.copy()
    result['family_unit'] = -1
    visible_ids = set(result['node_id'])
    family_unit = -1

    ordered = result.sort_values(['generation', 'x_order'])
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

            result.loc[unit.index, 'family_unit'] = family_unit

    return result


def _visible_parent_ids(value:object, visible_ids:set[UUID]) -> set[UUID]:
    """Normalize a PostgreSQL UUID array and omit undiscovered parents."""
    if value is None:
        return set()
    values = value if is_list_like(value) and not isinstance(value, str) else [value]
    return {parent_id for parent_id in values
            if not isna(parent_id) and parent_id in visible_ids}

def reroute_tails(tree_data:DataFrame, generation_limit:int) -> DataFrame:
    """Stagger complete families and rebuild cross-family ordering tails."""
    if generation_limit < 1:
        raise ValueError('generation_limit must be at least 1.')

    result = tree_data.copy()
    result['display_generation'] = result['generation'].astype(float)
    node_families = result.set_index('node_id')['family_unit'].to_dict()

    for generation_value in result['generation'].drop_duplicates():
        generation = result[result['generation'] == generation_value]
        family_ids = generation.sort_values('x_order')['family_unit'].drop_duplicates().tolist()
        display_rows = max(1, ceil(len(generation) / generation_limit))
        family_rows = {
            family_id: position % display_rows
            for position, family_id in enumerate(family_ids)
        }

        for family_id, display_row in family_rows.items():
            mask = ((result['generation'] == generation_value)
                    & (result['family_unit'] == family_id))
            result.loc[mask, 'display_generation'] = (
                float(generation_value) + display_row / display_rows
            )

        cross_family_order = (
            (result['generation'] == generation_value)
            & (result['tail_type'] == 'order')
            & result['tail_id'].notna()
            & result.apply(
                lambda node: node_families.get(node['tail_id']) != node['family_unit'],
                axis=1,
            )
        )
        result.loc[cross_family_order, ['tail_id', 'tail_type']] = [None, None]

        for display_row in range(display_rows):
            row_families = [family_id for family_id in family_ids
                            if family_rows[family_id] == display_row]
            for left_family, right_family in pairwise(row_families):
                left = generation[generation['family_unit'] == left_family]
                right = generation[generation['family_unit'] == right_family]
                left_index = left['x_order'].idxmax()
                right_node_id = right.loc[right['x_order'].idxmin(), 'node_id']
                result.loc[left_index, ['tail_id', 'tail_type']] = [
                    right_node_id, 'order'
                ]

    return result


''' main family tree charts '''
def tree_chart(tree_data:DataFrame, cloud_name:str, use_images=False) -> Graph:
    GENERATION_LIMIT = 20

    tree_data = find_boundaries(tree_data)
    tree_data = reroute_tails(tree_data, GENERATION_LIMIT)

    tree = Graph()
    ##tree.attr(splines='False')
    ##tree.attr(splines='polyline')

    for generation in tree_data['display_generation'].unique():

        tree_data_g = tree_data[tree_data['display_generation']==generation]
        subtree = Graph()
        subtree.attr(rank='same')

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

        tree.subgraph(subtree)

    # add horizontal edges
    for _, node in tree_data[tree_data['tail_id'].notna()].iterrows():
        match node['tail_type']:
            case 'order':
                style = 'invis'
            case 'union':
                style = None
            case _:
                style = 'invis'
        tree.edge(str(node['node_id']), str(node['tail_id']), style=style)

    # add vertical edges
    for _, node in tree_data[tree_data['head_id'].notna()].iterrows():       
        tree.edge(str(node['head_id']), str(node['node_id']))

    return tree
