from uuid import UUID

from graphviz import Graph

from common.secret import secrets
from database.db import get_engine
from database.db_family import fetch_founder
from family_tree.ancestry import build_tree, get_units, list_all_relatives
##from family_tree.tree_maker import create_tree


PGHOST = secrets['postgresql']['host']
PGPORT = secrets['postgresql']['port']
PGDBNAME = secrets['postgresql']['database']
PGUSER = secrets['postgresql']['user']
PGPASSWORD = secrets['postgresql']['password']

CLOUDINARY_CLOUD = secrets['cloudinary']['cloud_name']

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)
founder_id = fetch_founder(engine)

relative_ids = list_all_relatives(engine, founder_id,
                                  bloodline=True)
input(f'{relative_ids=}')

get_units(engine, founder_id)

relatives = build_tree(engine, founder_id,
                       include_animals=True, cut_date=None, include_deceased=True)

print(relatives.to_string())
##tree = create_tree(engine, founder_id, CLOUDINARY_CLOUD)

##print(tree.source)

# # tree.attr(rankdir='LR')
# # tree.format = 'png'
# # tree.render('c:/users/mfran/OneDrive/desktop/test', view=True, cleanup=True)