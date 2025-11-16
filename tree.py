from uuid import UUID

from graphviz import Graph

from common.secret import secrets
from family_tree.db import get_engine
from family_tree.tree_maker import create_tree


PGHOST = secrets['postgresql']['host']
PGPORT = secrets['postgresql']['port']
PGDBNAME = secrets['postgresql']['database']
PGUSER = secrets['postgresql']['user']
PGPASSWORD = secrets['postgresql']['password']

CLOUDINARY_CLOUD = secrets['cloudinary']['cloud_name']

founder_id = UUID('b9e4e0ef-d45e-4c96-a277-a99b0d062066')

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)
##engine = get_engine(st.secrets['PGHOST'], st.secrets['PGPORT'], st.secrets['PGDATABASE'], st.secrets['PGUSER'], st.secrets['PGPASSWORD'])

tree = create_tree(engine, founder_id, CLOUDINARY_CLOUD)

##print(tree.source)

##tree.attr(rankdir='LR')
tree.format = 'png'
tree.render('c:/users/mfran/OneDrive/desktop/test', view=True, cleanup=True)