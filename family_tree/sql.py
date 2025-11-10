### tables ###

# table containing folders
folders_table = '''
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE IF NOT EXISTS folders (
  folder_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  folder_name CITEXT NOT NULL,
  project_year INTEGER NOT NULL,
  person_id UUID REFERENCES persons(person_id) ON DELETE SET NULL,
  animal_id UUID REFERENCES animals(animal_id) ON DELETE SET NULL,
  storage_url CITEXT,
  video_count INTEGER DEFAULT 0,
  video_duration DOUBLE PRECISION DEFAULT 0,
  review_count INTEGER DEFAULT 0,
  usable_count INTEGER DEFAULT 0,
  used_count INTEGER DEFAULT 0,
  CONSTRAINT folders_name_year_uniq UNIQUE (folder_name, project_year)
);
'''


# table containing all humans
persons_table = '''
CREATE TABLE IF NOT EXISTS persons (
  person_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  first_name TEXT NOT NULL,
  middle_names TEXT,
  last_name TEXT NOT NULL,
  maiden_name TEXT,
  suffix INT,
  nickname TEXT,
  sex TEXT check (sex IN ('m', 'f')),
  birth_date TIMESTAMP,
  birth_date_precision TEXT DEFAULT 'day' CHECK (birth_date_precision IN ('day', 'month', 'year')),
  death_date TIMESTAMP,
  death_date_precision TEXT DEFAULT 'day' CHECK (death_date_precision IN ('day', 'month', 'year')),
  notes TEXT
  );
'''

# table containing all animals
animals_table = '''  
CREATE TABLE IF NOT EXISTS animals (
  animal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  first_name TEXT NOT NULL,
  middle_names TEXT,
  nickname TEXT,
  sex TEXT check (sex IN ('m', 'f')),
  species TEXT,
  birth_date TIMESTAMP,
  birth_date_precision TEXT DEFAULT 'day' CHECK (birth_date_precision IN ('day', 'month', 'year')),
  death_date TIMESTAMP,
  death_date_precision TEXT DEFAULT 'day' CHECK (death_date_precision IN ('day', 'month', 'year')),
  notes TEXT
  );
'''

# table containing unions between persons
marriages_table = '''
CREATE TABLE IF NOT EXISTS marriages (
  marriage_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  husband_id UUID NOT NULL REFERENCES persons(person_id),
  wife_id UUID NOT NULL REFERENCES persons(person_id),
  wedding_date TIMESTAMP,
  wedding_date_precision TEXT DEFAULT 'day' CHECK (wedding_date_precision IN ('day', 'month', 'year'))
);
'''

# table containing parent-child relationships between persons
parents_table = '''
CREATE TABLE IF NOT EXISTS parents (
  child_id UUID NOT NULL REFERENCES persons(person_id),
  parent_id UUID NOT NULL REFERENCES persons(person_id),
  relation_type TEXT DEFAULT 'biological' CHECK (relation_type IN ('biological', 'adoptive', 'step'))
  );
'''

# table containing relationships between persons and animals
pets_table = '''
CREATE TABLE IF NOT EXISTS pets (
  pet_id UUID NOT NULL REFERENCES animals(animal_id),
  owner_id UUID NOT NULL REFERENCES persons(person_id),
  relation_type TEXT DEFAULT 'adoptive' CHECK (relation_type IN ('adoptive', 'shared')),
  gotcha_date TIMESTAMP,
  gotcha_date_precision TEXT DEFAULT 'day' CHECK (gotcha_date_precision IN ('day', 'month', 'year'))
  );
'''

# table for identifying the founding member
founder_table = f'''
CREATE TABLE IF NOT EXISTS founder (
  founder_id UUID NOT NULL REFERENCES persons(person_id)
);
'''


### functions ###

# function to convert integer suffix to text with roman numerals
suffix_to_text_function = '''
--DROP FUNCTION IF EXISTS public.suffix_to_text(integer, boolean) CASCADE;

CREATE OR REPLACE FUNCTION suffix_to_text(x int, with_space boolean DEFAULT false)
RETURNS text AS $$
DECLARE
  n int := x;
  res text := '';
  numerals int[];
  symbols text[];
  i int;
BEGIN
  IF n IS NULL THEN
    RETURN NULL;
  ELSIF n = 1 THEN
    res := 'Sr';
  ELSIF n = 2 THEN
    res := 'Jr';
  ELSIF n >= 3 AND n <= 3000 THEN
    numerals := ARRAY[1000,900,500,400,100,90,50,40,10,9,5,4,1];
    symbols  := ARRAY['M','CM','D','CD','C','XC','L','XL','X','IX','V','IV','I'];

    FOR i IN 1..array_length(numerals,1) LOOP
      WHILE n >= numerals[i] LOOP
        res := res || symbols[i];
        n := n - numerals[i];
      END LOOP;
    END LOOP;
  ELSE
    RETURN NULL;
  END IF;

  IF with_space AND res IS NOT NULL THEN
    RETURN ' ' || res;
  ELSE
    RETURN res;
  END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
'''

# function to add grand- or great to parent/child
generation_to_text_function = '''
--DROP FUNCTION generation_to_text(int) CASCADE;

CREATE OR REPLACE FUNCTION generation_to_text(gen int, plural boolean DEFAULT true)
RETURNS text AS $$
DECLARE
  g int := gen;
  k int;
BEGIN
  IF g IS NULL THEN
    RETURN NULL;

  ELSIF g = 0 THEN
    RETURN CASE WHEN plural THEN 'parents' ELSE 'parent' END;

  ELSIF g > 0 THEN
    IF g = 1 THEN
      RETURN CASE WHEN plural THEN 'children' ELSE 'child' END;
    ELSIF g = 2 THEN
      RETURN CASE WHEN plural THEN 'grandchildren' ELSE 'grandchild' END;
    ELSE
      -- 3 => great-grand(child/children), 4 => great-great-..., etc.
      k := g - 2;
      RETURN repeat('great-', k) ||
             CASE WHEN plural THEN 'grandchildren' ELSE 'grandchild' END;
    END IF;

  ELSE  -- g < 0 (ancestors)
    k := abs(g);
    IF k = 1 THEN
      RETURN CASE WHEN plural THEN 'grandparents' ELSE 'grandparent' END;
    ELSIF k = 2 THEN
      RETURN CASE WHEN plural THEN 'great-grandparents' ELSE 'great-grandparent' END;
    ELSE
      RETURN repeat('great-', k - 2) ||
             CASE WHEN plural THEN 'grandparents' ELSE 'grandparent' END;
    END IF;
  END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
'''

### views ###

# view for name display preferences
display_names_view = '''
DROP VIEW IF EXISTS display_names CASCADE;

CREATE OR REPLACE VIEW display_names AS

WITH married_names AS
  (
  SELECT wife_id, last_name AS married_name
  FROM marriages JOIN persons ON husband_id = person_id
  )
  
  SELECT person_id AS display_id,
    CASE
      WHEN first_name IS NULL THEN '< new baby ' ||
        (CASE
          WHEN sex = 'm' THEN 'boy '
          WHEN sex = 'f' THEN 'girl '
          ELSE ''
         END) || ' >'
      ELSE COALESCE (nickname, first_name) END || ' '
      || COALESCE (married_name, last_name)
      || suffix_to_text(suffix)
    AS full_name
  FROM persons LEFT JOIN married_names ON person_id = wife_id
  
  UNION

  SELECT animal_id AS display_id,
  COALESCE (animals.nickname, animals.first_name) || ' the ' || animals.species
  /*|| ' ' || persons.last_name*/ AS full_name
  FROM animals JOIN pets ON animal_id = pet_id
  JOIN persons ON owner_id = person_id;
 '''

# view for calendar of birthdays and anniversaries
calendar_view = '''
DROP VIEW IF EXISTS calendar;

CREATE VIEW calendar AS
WITH calendar_days AS (

  SELECT
    CASE 
      WHEN birth_date_precision = 'month' THEN to_char(birth_date, 'Month')
      ELSE to_char(birth_date, 'Mon DD')
    END AS day_of_year, 'birthday' AS event_type,
    full_name, birth_date AS full_date
    FROM persons JOIN display_names ON person_id = display_id
    WHERE birth_date_precision IN ('day', 'month')
    
  UNION ALL

  SELECT
    CASE 
      WHEN gotcha_date_precision = 'month' THEN to_char(gotcha_date, 'Month')
      WHEN gotcha_date_precision = 'day' THEN to_char(gotcha_date, 'Mon DD')
    END AS day_of_year, 'gotcha' AS event_type,
    full_name, gotcha_date AS full_date
    FROM pets 
    JOIN animals ON pets.pet_id = animals.animal_id
    JOIN display_names ON animal_id = display_id
    WHERE relation_type = 'adoptive' AND gotcha_date_precision IN ('day', 'month')

  UNION ALL

  SELECT
    CASE 
      WHEN wedding_date_precision = 'month' THEN to_char(wedding_date, 'Month')
      ELSE to_char(wedding_date, 'Mon DD')
    END AS day_of_year, 'anniversary' AS day_event,
    COALESCE(husbands.nickname, husbands.first_name) || ' & ' || COALESCE(wives.nickname, wives.first_name) 
      || ' ' || husbands.last_name AS full_name,
    wedding_date AS full_date
    FROM marriages
    JOIN persons AS husbands ON husband_id = husbands.person_id
    JOIN persons AS wives ON wife_id = wives.person_id
    WHERE wedding_date_precision IN ('day', 'month')
  
  )

SELECT day_of_year, event_type, full_name, EXTRACT (YEAR FROM age(full_date::date)) AS years FROM calendar_days
  ORDER BY to_char(full_date, 'MM-DD') ASC, years DESC;
'''

# view to determine clans based on age, marriage, and parenthood
clans_view = '''
DROP VIEW IF EXISTS clans CASCADE;

CREATE OR REPLACE VIEW clans AS 

WITH leaders AS (
  SELECT parent_id AS person_id FROM parents
  UNION
  SELECT husband_id FROM marriages
  UNION
  SELECT wife_id FROM marriages
  UNION
  SELECT person_id FROM persons
  WHERE EXTRACT(YEAR FROM age(birth_date::date)) >= 30
),
  
heads AS (
  SELECT
    p.person_id,
    first_name,
    last_name,
    suffix,
    -- spouse_id is NULL for solos/one-parent households
    COALESCE (m1.wife_id, m2.husband_id) AS spouse_id,
    COALESCE (m1.wedding_date, m2.wedding_date) AS wedding_date,
    birth_date
  FROM persons p
  JOIN leaders USING (person_id)
  LEFT JOIN marriages m1 ON p.person_id = m1.husband_id
  LEFT JOIN marriages m2 ON p.person_id = m2.wife_id
),

-- Couples: exactly one row per marriage, male-first from the marriages table
couple_clans AS (
  SELECT
    m.husband_id AS person_id,
    m.wife_id AS spouse_id,
    ph.last_name || ', ' || ph.first_name || suffix_to_text(ph.suffix) || '/' || pw.first_name AS clan_name,
    m.wedding_date as clan_date
  FROM marriages m
  -- only include couples where both heads are in your leaders list
  JOIN heads ph ON ph.person_id = m.husband_id
  JOIN heads pw ON pw.person_id = m.wife_id
  WHERE m.wedding_date <= CURRENT_DATE
),

-- Solos / one-parent households: no spouse_id
solo_clans AS (
  SELECT
    h.person_id,
    NULL::uuid AS spouse_id,
    h.last_name || ', ' || h.first_name || suffix_to_text(h.suffix) AS clan_name,
    birth_date as clan_date
  FROM heads h
  WHERE h.spouse_id IS NULL
)

SELECT person_id AS head_id_1, spouse_id AS head_id_2, clan_name, clan_date::date
FROM couple_clans
UNION ALL
SELECT person_id, spouse_id, clan_name, clan_date::date
FROM solo_clans
ORDER BY clan_name;
'''

# view to determine generations and entry type based on relationship to founder
generations_view = '''
--DROP VIEW IF EXISTS generations;

CREATE OR REPLACE VIEW generations AS

WITH RECURSIVE
base AS (
  SELECT founder_id AS person_id, COALESCE(m1.husband_id, m2.wife_id) AS spouse_id
  FROM founder
    LEFT JOIN marriages m1 ON m1.wife_id = founder_id
    LEFT JOIN marriages m2 ON m2.husband_id = founder_id
  ),

fdrs AS (
  SELECT DISTINCT founder_id
  FROM base,
  LATERAL (VALUES (base.person_id), (base.spouse_id)) AS v(founder_id)
  WHERE founder_id IS NOT NULL
),
 
mf AS (
  SELECT child_id, parent_id, sex AS sex FROM parents JOIN persons ON parent_id = person_id
  ),

fathers AS (
  SELECT child_id, parent_id AS father_id FROM mf WHERE sex = 'm'
  ),

mothers AS (
  SELECT child_id, parent_id AS mother_id FROM mf WHERE sex = 'f'
  ),

diagram AS (
  SELECT person_id, birth_date,
    COALESCE (m2.husband_id, m1.wife_id) AS spouse_id,
    COALESCE(m1.wedding_date, m2.wedding_date) AS wedding_date,
    father_id, mother_id,
    CASE
      WHEN person_id IN (SELECT founder_id FROM fdrs) THEN 'founder'
    END as entry_type
    FROM persons LEFT JOIN marriages m1 ON person_id = m1.husband_id LEFT JOIN marriages m2 ON person_id = m2.wife_id
    LEFT JOIN fathers ON fathers.child_id = person_id LEFT JOIN mothers ON mothers.child_id = person_id
  ),

elders (person_id, generation) AS (
  SELECT person_id, 0, entry_type
  FROM diagram
  WHERE entry_type = 'founder'
  UNION
  SELECT diagram.person_id, elders.generation - 1, 'rooted' AS entry_type
  FROM elders
  JOIN parents ON child_id = elders.person_id
  JOIN diagram ON parent_id = diagram.person_id
),

kids (person_id, generation) AS (
  SELECT person_id, generation, entry_type
  FROM elders
  UNION 
  SELECT diagram.person_id, kids.generation + 1,
  CASE WHEN birth_date <= CURRENT_DATE THEN 'born' ELSE 'preborn' END AS entry_type
  FROM kids
  JOIN parents ON parent_id = kids.person_id
  JOIN diagram ON child_id = diagram.person_id
  ),

spouses AS (
  SELECT diagram.person_id, kids.generation,
  CASE WHEN wedding_date <= CURRENT_DATE THEN 'married' ELSE 'engaged' END AS entry_type
  FROM diagram JOIN kids ON diagram.spouse_id = kids.person_id
  WHERE kids.entry_type <> 'founder'
  ),

furries AS (
  SELECT pet_id, generation + 1 as generation, 'pet' AS entry_type
  FROM pets JOIN (
    SELECT person_id, generation FROM kids
    UNION
    SELECT person_id, generation FROM spouses
    UNION
    SELECT person_id, generation FROM elders) ON owner_id = person_id
),

all_family AS (
  SELECT DISTINCT ON (person_id) * FROM (
    SELECT person_id, generation, entry_type FROM elders
    UNION
    SELECT person_id, generation, entry_type FROM kids
    UNION
    SELECT person_id, generation, entry_type FROM spouses
    UNION
    SELECT pet_id, generation, entry_type FROM furries
    ) 
  ORDER BY person_id,
    CASE
      WHEN entry_type = 'founder' THEN 0
      WHEN entry_type = 'rooted' THEN 1
      WHEN entry_type = 'born' THEN 2
      WHEN entry_type = 'married' THEN 3
      WHEN entry_type = 'pet' THEN 4
      ELSE 5
    END
  )

SELECT peoples.person_id,
  all_family.entry_type, all_family.generation
  FROM peoples JOIN all_family USING (person_id)
  ORDER BY generation
;
'''

# view to combine persons/animals with display names, generations and entry dates
family_tree_view = '''
--DROP VIEW IF EXISTS family_tree;

CREATE OR REPLACE VIEW family_tree AS
WITH
  -- identify the heads of household from the clans view
  heads AS (
    SELECT head_id_1 AS person_id, clan_name FROM clans
      WHERE head_id_1 IS NOT NULL
    UNION
    SELECT head_id_2 AS person_id, clan_name FROM clans
      WHERE head_id_2 IS NOT NULL
    ),

  -- assign clans to each dependent based on parents and ownerships
  memberships AS (
    SELECT persons.person_id, clan_name FROM persons
      JOIN parents ON persons.person_id = child_id
      JOIN heads ON parent_id = heads.person_id 
      WHERE persons.person_id NOT IN (SELECT person_id FROM heads)
    UNION
    SELECT animals.animal_id, clan_name FROM animals
      JOIN pets ON animals.animal_id = pet_id
      JOIN heads ON owner_id = heads.person_id 
    UNION
    SELECT person_id, clan_name FROM heads
    ),

  -- get list of husbands and wives
  n_weddings AS (
    SELECT husband_id AS person_id, wedding_date FROM marriages
    UNION
    SELECT wife_id AS person_id, wedding_date FROM marriages
  ),

  -- calculate first childbirth of born/adopted children
  n_kids AS (
    SELECT p1.person_id, count(child_id) AS num_kids,
    MIN(CASE WHEN relation_type IN ('biological', 'adoptive') THEN p2.birth_date ELSE NULL END) AS min_child_birth_date
    FROM persons AS p1 JOIN parents ON p1.person_id = parent_id
    LEFT JOIN persons AS p2 ON p2.person_id = child_id
    GROUP BY p1.person_id
  ),

  -- calculate number of pets per person
  n_pets AS (
    SELECT person_id, COUNT(pet_id) AS num_pets
    FROM persons JOIN pets ON person_id = owner_id
    WHERE relation_type = 'adoptive'
    GROUP BY person_id
  ),

  -- figure out when people entered family
  entry_dates_people AS (
    SELECT person_id,
    CASE
      -- married founders use wedding date, solo founder use birthdate
      WHEN entry_type = 'founder' THEN GREATEST (LEAST (wedding_date, min_child_birth_date)::date, birth_date)
      -- ancestors and descendents use birthdate
      WHEN entry_type IN ('rooted', 'born', 'preborn') THEN birth_date    
      -- in-laws use wedding date
      WHEN entry_type IN ('married', 'engaged') THEN wedding_date    
    END AS entry_date,
      CASE
        -- preborn don't have age yet
        WHEN birth_date > CURRENT_DATE THEN NULL
        -- use death date for deceased, current date for living
        ELSE EXTRACT (YEAR FROM age(COALESCE(death_date::date, CURRENT_DATE), birth_date::date))
      END AS age_years
  
      FROM peoples JOIN generations USING (person_id)
      LEFT JOIN n_kids USING (person_id) LEFT JOIN n_weddings USING (person_id)
      WHERE entry_type IN ('founder', 'rooted', 'born', 'preborn', 'married', 'engaged')
  ),

  -- find the owner entry date for each pet
  n_owners AS (
    SELECT pet_id, MIN (gotcha_date) AS gotcha_date, MAX (entry_date) AS min_entry_date
    FROM pets JOIN entry_dates_people ON person_id = owner_id
    WHERE relation_type = 'adoptive'
    GROUP BY pet_id
  ),

  -- add pet entry dates
  entry_dates_all AS (
    SELECT person_id, entry_date, age_years FROM entry_dates_people UNION
    SELECT person_id,
    CASE
      WHEN entry_type = 'pet' THEN
        CASE
          -- if it's unclear when the animal entered the family, leave blank
          -- otherwise make sure it's not before the owner
          WHEN COALESCE (birth_date, gotcha_date) IS NOT NULL THEN GREATEST (birth_date, gotcha_date, min_entry_date)
        END
    END AS entry_date,
      CASE
        WHEN birth_date > CURRENT_DATE THEN NULL
        ELSE EXTRACT (YEAR FROM age(COALESCE(death_date::date, CURRENT_DATE), birth_date::date))
      END AS age_years
    
      FROM peoples JOIN generations USING (person_id)
      LEFT JOIN n_owners ON person_id = pet_id --AND relation_type = 'adoptive'
      LEFT JOIN memberships USING (person_id)
      LEFT JOIN clans USING (clan_name)
      WHERE entry_type = 'pet'
  ),

  -- add entry # and clan ID
  tree AS (
    SELECT person_id, birth_date,
    ROW_NUMBER() OVER (ORDER BY entry_date ASC, age_years DESC) AS entry_number, generation,
    full_name, entry_date::date, age_years, clan_name, entry_type, num_kids, num_pets
    
    FROM peoples JOIN display_names ON person_id = display_id
    JOIN entry_dates_all USING (person_id) JOIN generations USING (person_id)
    LEFT JOIN memberships USING (person_id)
    LEFT JOIN n_kids USING (person_id) LEFT JOIN n_pets USING (person_id)
  )

-- normalize for founder
SELECT entry_number - (SELECT entry_number FROM tree JOIN founder ON person_id = founder_id LIMIT 1) + 1
    - CASE WHEN entry_number < (SELECT entry_number FROM tree JOIN founder ON person_id = founder_id LIMIT 1)
    THEN 1 ELSE 0 END
    AS entry_number,
  generation, full_name, entry_date, age_years, clan_name, entry_type, num_kids, num_pets, person_id
    FROM tree
  
    ORDER BY entry_date ASC, birth_date ASC;
'''