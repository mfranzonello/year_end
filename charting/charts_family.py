from math import ceil
from uuid import UUID

from graphviz import Graph
from pandas import DataFrame
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

''' main family tree charts '''
def tree_chart(tree_data:DataFrame, cloud_name:str, use_images=False) -> Graph:
    GENERATION_LIMIT = 20

    tree = Graph()
    ##tree.attr(splines='False')
    ##tree.attr(splines='polyline')

    for generation in tree_data['generation'].unique():
        tree_data_g = tree_data[tree_data['generation']==generation]
        generation_size = len(tree_data_g)
        gx = ceil(generation_size / GENERATION_LIMIT)

        for i in range(gx + 1):
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