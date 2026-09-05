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

def find_boundaries(tree_data:DataFrame) -> DataFrame:
    tree_data['family_unit'] = 0
    c = 0
    parent_ids = {}
    for i, node in tree_data.iterrows():
        p_ids = node['parent_ids']

        if p_ids:
            if any(p_id in parent_ids for p_id in p_ids):
                parent_ids.update(p_ids)
            else:
                parent_ids = {}
                c += 1
        tree_data['family_unit'].loc[i] = c

    return tree_data

def reroute_tails(tree_data:DataFrame, generation_limit:int) -> DataFrame:
    for g in tree_data['generation'].unique():
        tree_data_g = tree_data[tree_data['generation'] == g]
        
        tree_gb = tree_data_g.groupby(['family_unit'])['x_order']
        max_nodes = tree_data_g.loc[tree_gb.idxmax(), ['family_unit', 'node_id']]
        min_nodes = tree_data_g.loc[tree_gb.idxmin(), ['family_unit', 'node_id']]
        min_family_unit = tree_data_g['family_unit'].min()
        max_family_unit = tree_data_g['family_unit'].max()

        if len(tree_data_g) > generation_limit:
            gx = ceil(len(tree_data_g) / generation_limit)

            for i in range(min_family_unit, max_family_unit - gx + 1):
                print(max_nodes)
                max_node_i = max_nodes[max_nodes['family_unit'] == i]['node_id'].iloc[0]
                min_node_j = min_nodes[min_nodes['family_unit'] == i + gx]['node_id'].iloc[0]
                tree_data.loc[tree_data['node_id'] == max_node_i, 'tail_id'] = min_node_j


            for i in range(gx + 1):
                mask = ((tree_data['generation'] == g)
                        & (tree_data['family_unit'] % (i + 1) == 0))

                tree_data.loc[mask, 'generation'] = g + i / gx
            
    return tree_data


''' main family tree charts '''
def tree_chart(tree_data:DataFrame, cloud_name:str, use_images=False) -> Graph:
    GENERATION_LIMIT = 20

    tree_data = find_boundaries(tree_data)
    tree_data = reroute_tails(tree_data, GENERATION_LIMIT)

    tree = Graph()
    ##tree.attr(splines='False')
    ##tree.attr(splines='polyline')

    for generation in tree_data['generation'].unique():

        tree_data_g = tree_data[tree_data['generation']==generation]
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