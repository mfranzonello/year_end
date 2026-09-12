from datetime import date
from uuid import UUID

from sqlalchemy import Engine
from pandas import DataFrame

from database.db import read_sql, execute_sql, build_values

# Family Tree
def fetch_persons(engine:Engine, person_id:UUID=None) -> DataFrame:
    wheres = f'WHERE person_id = :person_id' if person_id else ''
    sql = f'''
    SELECT person_id,
    first_name, middle_names, last_name, nick_name, uses_middle,
    suffix, prefix, sex,
    birth_date, birth_date_precision, death_date, death_date_precision,
    notes
    FROM persons {wheres}
    ;'''
    return read_sql(engine, sql, params={'person_id': person_id})

def update_person(engine:Engine, person_information:dict):
    sql = f'''
    UPDATE persons SET
    first_name = :first_name, nick_name = :nick_name,
    last_name = :last_name,
    middle_names = :middle_names, uses_middle = :uses_middle,
    suffix = :suffix, prefix = :prefix, sex = :sex,
    birth_date = :birth_date, birth_date_precision = :birth_date_precision,
    death_date = :death_date, death_date_precision = :death_date_precision,
    notes = :notes
    WHERE person_id = :person_id
    ;'''
    execute_sql(engine, sql, params=person_information)

def insert_person(engine, person_information:dict):
    sql = f'''
    INSERT INTO persons
    (first_name, middle_names, last_name, nick_name, uses_middle,
    suffix, prefix, sex,
    birth_date, birth_date_precision, death_date, death_date_precision,
    notes)
    VALUES
    (:first_name, :middle_names, :last_name, :nick_name, :uses_middle,
    :suffix, :prefix, :sex,
    :birth_date, :birth_date_precision, :death_date, :death_date_precision,
    :notes)
    RETURNING person_id;'''
    return execute_sql(engine, sql, params=person_information, returning=True)[0][0]

def remove_person(engine:Engine, person_id:UUID):
    sql = f'''
    DELETE FROM persons WHERE person_id = :person_id
    ;'''
    execute_sql(engine, sql, params={'person_id': person_id})

def fetch_animals(engine:Engine, animal_id:UUID=None) -> DataFrame:
    wheres = f'WHERE animal_id = :animal_id' if animal_id else ''
    sql = f'''SELECT animal_id,
    first_name, middle_names, nick_name, sex, species,
    birth_date, birth_date_precision, death_date, death_date_precision,
    notes
    FROM animals {wheres}
    ;'''
    return read_sql(engine, sql, params={'animal_id': animal_id})

def update_animal(engine:Engine, animal_information:dict):
    sql = f'''
    UPDATE animals SET
    first_name = :first_name, nick_name = :nick_name,
    middle_names = :middle_names,
    sex = :sex, species = :species,
    birth_date = :birth_date, birth_date_precision = :birth_date_precision,
    death_date = :death_date, death_date_precision = :death_date_precision,
    notes = :notes
    WHERE animal_id = :animal_id
    ;'''
    execute_sql(engine, sql, params=animal_information)

def insert_animal(engine, animal_information:dict):
    sql = f'''
    INSERT INTO animals
    (first_name, middle_names, nick_name,
    sex, species,
    birth_date, birth_date_precision, death_date, death_date_precision,
    notes)
    VALUES
    (:first_name, :middle_names, :nick_name,
    :sex, :species,
    :birth_date, :birth_date_precision, :death_date, :death_date_precision,
    :notes)
    RETURNING animal_id;'''
    return execute_sql(engine, sql, params=animal_information, returning=True)[0][0]

def remove_animal(engine:Engine, animal_id:UUID):
    sql = f'''
    DELETE FROM animals WHERE animal_id = :animal_id
    ;'''
    execute_sql(engine, sql, params={'animal_id': animal_id})

def fetch_parents(engine:Engine, person_id:UUID=None) -> DataFrame:
    wheres = 'WHERE child_id = :person_id' if person_id else ''
    sql = f'''SELECT child_id, parent_id, relation_type
    FROM parents {wheres}
    ;'''
    return read_sql(engine, sql, params={'person_id': person_id})

def update_parents(engine, parent_information):
    sql = f'''
    UPDATE parents SET 
    relation_type = :relation_type
    WHERE child_id = :child_id AND parent_id = :parent_id
    ;'''
    execute_sql(engine, sql, params=parent_information)

def insert_parents(engine, parent_information):
    sql = f'''
    INSERT INTO parents (child_id, parent_id, relation_type)
    VALUES (:child_id, :parent_id, :relation_type)
    ;'''
    execute_sql(engine, sql, params=parent_information)

def remove_parents(engine, parent_information):
    sql = f'''
    DELETE FROM parents
    WHERE child_id = :child_id AND parent_id = :parent_id_old
    ;'''
    execute_sql(engine, sql, params=parent_information)

def fetch_pets(engine:Engine, animal_id:UUID=None) -> DataFrame:
    wheres = 'WHERE pet_id = :animal_id' if animal_id else ''
    sql = f'''SELECT pet_id, owner_id, relation_type,
    gotcha_date, gotcha_date_precision
    FROM pets {wheres}
    ;'''
    return read_sql(engine, sql, params={'animal_id': animal_id})

def update_pets(engine:Engine, pet_information:dict):
    sql = f'''
    UPDATE pets SET relation_type = :relation_type,
    gotcha_date = :gotcha_date, gotcha_date_precision = gotcha_date_precision
    WHERE pet_id = :pet_id AND owner_id = :owner_id
    ;'''
    return execute_sql(engine, sql, params=pet_information)

def insert_pets(engine:Engine, pet_information:dict):
    sql = f'''
    INSERT INTO pets (pet_id, owner_id, relation_type, gotcha_date, gotcha_date_precision)
    VALUES (:pet_id, :owner_id, :relation_type, :gotcha_date, :gotcha_date_precision)
    ;'''
    execute_sql(engine, sql, params=pet_information)

def remove_pets(engine:Engine, pet_information:dict):
    sql = f'''
    DELETE FROM pets
    WHERE pet_id = :pet_id AND owner_id = :owner_id_old 
    ;'''
    execute_sql(engine, sql, params=pet_information)

def fetch_partnerships(engine: Engine) -> DataFrame:
    sql = '''
    SELECT union_id, partner_id_1, partner_id_2,
    union_date, union_date_precision, union_type
    FROM tree.partnerships
    ;'''
    return read_sql(engine, sql)

def fetch_partners(engine:Engine, person_id:UUID=None) -> DataFrame:
    wheres = 'AND u1.person_id = :person_id' if person_id else ''
    sql = f'''
    SELECT u1.person_id, u2.person_id AS partner_id,
    union_id, union_type, union_date, union_date_precision,
    last_name_person_id, last_name_hyphen, last_name_custom
    FROM unions JOIN union_members u1 USING (union_id)
    JOIN union_members u2 USING (union_id)
    WHERE u1.person_id != u2.person_id {wheres}
    ;'''
    return read_sql(engine, sql, params={'person_id': person_id})

def update_partners(engine:Engine, partner_information:dict):
    sql = f'''
    UPDATE unions SET union_type = :union_type,
    union_date = :union_date, union_date_precision = :union_date_precision,
    last_name_person_id = :last_name_person_id,
    last_name_hyphen = :last_name_person_id, last_name_custom = :last_name_custom
    WHERE union_id = :union_id
    ;'''
    execute_sql(engine, sql, params=partner_information)

def insert_partners(engine:Engine, partner_information:dict):
    sql = f'''
    INSERT INTO unions
    (union_date, union_date_precision, union_type,
    last_name_person_id, last_name_hyphen, last_name_custom)
    VALUES
    (:union_date, :union_date_precision, :union_type,
    :last_name_person_id, :last_name_hyphen, :last_name_custom)
    RETURNING union_id
    ;'''
    union_id = execute_sql(engine, sql, params=partner_information, returning=True)[0][0]
    
    partner_information.update({'union_id': union_id})
    sql = f'''
    INSERT INTO union_members
    (union_id, person_id)
    VALUES
    (:union_id, :person_id),
    (:union_id, :partner_id)
    ;'''
    execute_sql(engine, sql, params=partner_information)

def remove_partners(engine: Engine, partner_information:dict):
    sql = f'''
    DELETE FROM unions
    WHERE union_id = (SELECT union_id FROM union_members
    WHERE person_id IN (:person_id, :partner_id_old)
    GROUP BY union_id)
    ;'''
    execute_sql(engine, sql, params=partner_information)

def fetch_members(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT member_id, birth_date, birth_date_precision, death_date, death_date_precision,
    entry_date, entry_date_precision, member_type
    FROM tree.members
    ;'''
    return read_sql(engine, sql)

def fetch_households(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT member_id, clan_id
    FROM tree.households
    ;'''
    return read_sql(engine, sql)

def fetch_founder(engine:Engine) -> UUID:
    sql = f'''
    SELECT founder_id
    FROM dashboard.founder
    ;'''
    return read_sql(engine, sql).squeeze()

def fetch_family_graph(engine:Engine, founder_id:UUID,
                       cut_date:date|None=None,
                       traversal_mode:str='up_down',
                       include_partner_branches:bool=True) -> DataFrame:
    """Return the database-classified nodes and canonical graph connections."""
    sql = '''
    SELECT node_id, node_type, generation, unit_order, unit_position, x_order,
        parent_head_id, tail_id, tail_type, branch, lineage, ancestry,
        union_type, union_date, union_date_precision
    FROM dashboard.family_graph(
        :founder_id, :cut_date, :traversal_mode, :include_partner_branches
    )
    ORDER BY generation, x_order, node_id
    ;'''
    params = {
        'founder_id': founder_id,
        'cut_date': cut_date,
        'traversal_mode': traversal_mode,
        'include_partner_branches': include_partner_branches,
    }
    return read_sql(engine, sql, params=params)

def fetch_person_information(engine:Engine) -> DataFrame:
    sql = f'''
    WITH
    children AS (
    SELECT parent_id AS person_id,
    ARRAY_AGG(child_id ORDER BY birth_date) AS child_ids
    FROM parents JOIN persons ON child_id = person_id
    WHERE (COALESCE(birth_date_precision, '') != 'future') AND (COALESCE(birth_date, '-infinity'::date) <= CURRENT_DATE)
    GROUP BY parent_id
    ),

    expectations AS (
    SELECT
    parent_id AS person_id,
    ARRAY_AGG(child_id ORDER BY birth_date) AS expecting_ids
    FROM parents JOIN persons ON child_id = person_id
    WHERE (COALESCE(birth_date_precision, '') = 'future') AND (COALESCE(birth_date, '-infinity'::date) > CURRENT_DATE)
    GROUP BY parent_id
    ),

    folks AS (
    SELECT
    child_id AS person_id,
    ARRAY_AGG(parent_id ORDER BY birth_date) AS parent_ids
    FROM parents JOIN persons ON parent_id = person_id
    GROUP BY child_id
    ),

    furries AS (
    SELECT
    owner_id AS person_id,
    ARRAY_AGG(pet_id ORDER BY birth_date) AS pet_ids
    FROM pets JOIN animals ON pet_id = animal_id
    GROUP BY owner_id
    ),

    spouse AS (
    SELECT
    person_id,
    ARRAY_AGG(spouse_id) AS spouse_ids,
    MAX(union_date) AS union_date,
    MAX(union_date_precision) AS union_date_precision,
    MAX(severance_date) AS severance_date,
    MAX(married_name) AS married_name
    FROM tree.partners
    JOIN tree.partnerships USING (union_id)
    GROUP BY person_id
    ),   

    sibling_pairs AS (
    SELECT DISTINCT
    me.child_id AS person_id,
    sibling.child_id AS sibling_id,
    sibling_person.birth_date
    FROM parents me
    JOIN parents sibling
    ON sibling.parent_id = me.parent_id
    AND sibling.child_id != me.child_id
    JOIN persons sibling_person
    ON sibling.child_id = sibling_person.person_id
    WHERE sibling_person.birth_date_precision != 'future'
    ),

    siblings AS (
    SELECT
    person_id, ARRAY_AGG(sibling_id ORDER BY birth_date) AS sibling_ids
    FROM sibling_pairs
    GROUP BY person_id
    ),

    addy AS (
    SELECT DISTINCT ON (person_id)
    person_id, zip_code
    FROM messaging.address_moves
    JOIN messaging.addresses USING (address_id)
    ORDER BY person_id, start_date DESC NULLS LAST
    ),

    socials AS (
    SELECT
    person_id, email_address, phone_number
    FROM messaging.contacts
    ),

    stats_1 AS (
    SELECT
    member_id AS person_id,
    COUNT(file_id) AS total_files,
    COUNT(DISTINCT project_year) AS total_years
    FROM project.files JOIN project.folders USING (folder_id)
    GROUP BY member_id
    ),

    stats_2 AS (
    SELECT
    member_id AS person_id,
    COUNT(review_id) AS total_appearances
    FROM project.backfill
    GROUP BY member_id
    )

    SELECT
    person_id AS member_id, first_name, middle_names, last_name, married_name, nick_name,
    sex, prefix, suffix_to_text(suffix) AS suffix,
    parent_ids, spouse_ids, child_ids, expecting_ids, sibling_ids, pet_ids,
    birth_date::date, birth_date_precision, death_date::date, death_date_precision,
    union_date, union_date_precision, severance_date::date,
    JSON_BUILD_OBJECT('email_address', email_address, 'phone_number', phone_number,
    'zip_code', zip_code) AS contact_info,
    JSON_BUILD_OBJECT('files', COALESCE(total_files, 0), 'years', COALESCE(total_years, 0),
    'appearances', COALESCE(total_appearances, 0)) AS project_stats
    FROM persons
    LEFT JOIN folks USING (person_id)
    LEFT JOIN spouse USING (person_id)
    LEFT JOIN children USING (person_id)
    LEFT JOIN expectations USING (person_id)
    LEFT JOIN furries USING (person_id)
    LEFT JOIN siblings USING (person_id)
    LEFT JOIN socials USING (person_id)
    LEFT JOIN addy USING (person_id)
    LEFT JOIN stats_1 USING (person_id)
    LEFT JOIN stats_2 USING (person_id)
    ;'''
    return read_sql(engine, sql)

def fetch_animal_information(engine:Engine) -> DataFrame:
    sql = f'''
    WITH owners AS (
    SELECT pet_id AS animal_id,
    ARRAY_AGG(owner_id ORDER BY gotcha_date NULLS LAST) AS owner_ids
    FROM pets
    GROUP BY pet_id
    ),

    owner_gotchas AS (
    SELECT DISTINCT ON (pet_id)
    pet_id AS animal_id,
    gotcha_date, gotcha_date_precision
    FROM pets
    WHERE gotcha_date IS NOT NULL
    ORDER BY pet_id, gotcha_date ASC
    ),
  
    owner_addresses AS (
    SELECT
        p.pet_id AS animal_id,
        person_id,
        zip_code,
        start_date
    FROM pets p
    JOIN animals an
        ON animal_id = pet_id
    JOIN messaging.address_moves
        ON person_id = owner_id
    JOIN messaging.addresses
        USING (address_id)
    WHERE
        death_date IS NULL
        OR start_date IS NULL
        OR start_date <= death_date
    ),

    addy AS (
    SELECT DISTINCT ON (animal_id)
    animal_id, zip_code
    FROM owner_addresses
    ORDER BY animal_id, start_date DESC NULLS LAST
    ),

    stats_1 AS (
    SELECT
    member_id AS animal_id,
    COUNT(file_id) AS total_files,
    COUNT(DISTINCT project_year) AS total_years
    FROM project.files
    JOIN project.folders USING (folder_id)
    GROUP BY member_id
    ),

    stats_2 AS (
    SELECT member_id AS animal_id,
    COUNT(review_id) AS total_appearances
    FROM project.backfill
    GROUP BY member_id)

    SELECT
    animal_id AS member_id, first_name, middle_names, nick_name,
    sex, species, owner_ids,
    birth_date::date, birth_date_precision, death_date::date, death_date_precision,
    gotcha_date::date, gotcha_date_precision, 
    JSON_BUILD_OBJECT('zip_code', zip_code) AS contact_info,
    JSON_BUILD_OBJECT('files', COALESCE(total_files, 0),'years', COALESCE(total_years, 0),
    'appearances', COALESCE(total_appearances, 0)) AS project_stats
    FROM animals
    LEFT JOIN owners USING (animal_id)
    LEFT JOIN owner_gotchas USING (animal_id)
    LEFT JOIN addy USING (animal_id)
    LEFT JOIN stats_1 USING (animal_id)
    LEFT JOIN stats_2 USING (animal_id);
    ''';
    return read_sql(engine, sql)