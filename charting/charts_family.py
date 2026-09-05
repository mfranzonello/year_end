from math import ceil
from uuid import UUID

from graphviz import Graph
from pandas import DataFrame
from webcolors import name_to_hex

from family_tree.cloudinary_lite import get_image_url

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

def get_attributes(node) -> str:
    SHAPE_PERSON = 'rectangle'
    SHAPE_ANIMAL = 'ellipse'

    COLOR_MALE = 'cornflowerblue'
    COLOR_FEMALE = 'deeppink1'
    COLOR_NEUTER = 'azure3'

    if node['node_type'] == 'union':
        attributes = {'shape': 'point', 'width': '0', 'height': '0', 'pendwidth': '0'}
        
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

''' main status review charts '''
def tree_chart(tree_data:DataFrame, cloud_name:str) -> Graph:
    GENERATION_LIMIT = 20

    tree = Graph()
    ##tree.attr(splines='False')
    ##tree.attr(splines='polyline')

    for generation in tree_data['generation'].unique():
        subtree = Graph()
        subtree.attr(rank='same')

        tree_data_g = tree_data[tree_data['generation']==generation]

        for _, node in tree_data_g.iterrows():
            node_type = node['node_type']
            if node_type in ['person', 'animal']:
                if node_type == 'person':
                    label = get_person_label(node)
                else:
                    label = get_animal_label(node)
                image = get_image_url(str(node['node_id']), cloud_name)
                print(f'{image=}')

            else:
                label = 'union'
                image = None

            attributes = get_attributes(node)
            subtree.node(str(node['node_id']), label=label, image=image, **attributes)

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
    for _, node in tree_data[tree_data['parent_head_id'].notna()].iterrows():       
        tree.edge(str(node['parent_head_id']), str(node['node_id']))

    return tree