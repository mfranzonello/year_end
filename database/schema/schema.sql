-- Application-owned structure only. No table data, owners, or grants.
CREATE EXTENSION IF NOT EXISTS "citext" WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;
--
-- PostgreSQL database dump
--



SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: _debugging; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA _debugging;


--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA IF NOT EXISTS public;


--
-- Name: config; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA config;


--
-- Name: dashboard; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA dashboard;


--
-- Name: ingestion; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA ingestion;


--
-- Name: messaging; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA messaging;


--
-- Name: nello; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA nello;


--
-- Name: project; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA project;


--
-- Name: publishing; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA publishing;


--
-- Name: tree; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA tree;


--
-- Name: users; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA users;


--
-- Name: phone_number; Type: DOMAIN; Schema: messaging; Owner: -
--

CREATE DOMAIN messaging.phone_number AS text
	CONSTRAINT phone_number_check CHECK ((VALUE ~ '^[0-9]{10}$'::text));


--
-- Name: zip_code; Type: DOMAIN; Schema: messaging; Owner: -
--

CREATE DOMAIN messaging.zip_code AS text
	CONSTRAINT zip_code_check CHECK ((VALUE ~ '^[0-9]{5}(-[0-9]{4})?$'::text));


--
-- Name: media_type; Type: TYPE; Schema: project; Owner: -
--

CREATE TYPE project.media_type AS ENUM (
    '8mm',
    'vhs',
    'dvd',
    'digital camera',
    'smartphone'
);


--
-- Name: resolution; Type: TYPE; Schema: project; Owner: -
--

CREATE TYPE project.resolution AS ENUM (
    'na',
    'xx',
    'vhs',
    'sd',
    'hd',
    'fhd',
    '4k',
    '8k'
);


--
-- Name: review_span; Type: TYPE; Schema: project; Owner: -
--

CREATE TYPE project.review_span AS ENUM (
    'year',
    'decade',
    'history'
);


--
-- Name: ceremony; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.ceremony AS ENUM (
    'marriage',
    'civil',
    'friends'
);


--
-- Name: date_precision; Type: DOMAIN; Schema: public; Owner: -
--

CREATE DOMAIN public.date_precision AS text
	CONSTRAINT date_precision_check CHECK ((VALUE = ANY (ARRAY['past'::text, 'day'::text, 'month'::text, 'year'::text, 'future'::text])));


--
-- Name: gender; Type: DOMAIN; Schema: public; Owner: -
--

CREATE DOMAIN public.gender AS character(1)
	CONSTRAINT gender_check CHECK ((VALUE = ANY (ARRAY['m'::bpchar, 'f'::bpchar])));


--
-- Name: hexcolor; Type: DOMAIN; Schema: public; Owner: -
--

CREATE DOMAIN public.hexcolor AS character(7)
	CONSTRAINT hexcolor_check CHECK (((VALUE)::text ~* '^#[a-f0-9]{6}$'::text));


--
-- Name: parent_relation; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.parent_relation AS ENUM (
    'adoptive',
    'shared'
);


--
-- Name: pet_relation; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.pet_relation AS ENUM (
    'biological',
    'adoptive',
    'step'
);


--
-- Name: family_branches(uuid, date, text, boolean, text, boolean); Type: FUNCTION; Schema: dashboard; Owner: -
--

CREATE FUNCTION dashboard.family_branches(p_start_member_id uuid, p_cut_date date DEFAULT CURRENT_DATE, p_traversal_mode text DEFAULT 'up_down'::text, p_include_partner_branches boolean DEFAULT true, p_pet_visibility text DEFAULT 'all'::text, p_living_people_only boolean DEFAULT false) RETURNS TABLE(member_id uuid, generation integer, traversal_depth integer, discovered_from uuid, discovery_direction text, relation_type text, in_law boolean, parent_node_key uuid, parent_node_type text, parent_node_head_ids uuid[], headed_node_keys uuid[], sibling_order integer, lineage integer[], ancestry integer[], branch text)
    LANGUAGE sql STABLE
    AS $$ WITH family AS MATERIALIZED (SELECT member.* FROM dashboard.family_members(p_start_member_id,p_cut_date,p_traversal_mode,p_include_partner_branches,p_pet_visibility,p_living_people_only) member), classified AS (SELECT member.*, CASE cardinality(member.parent_node_head_ids) WHEN 2 THEN 'shared' WHEN 1 THEN CASE WHEN head.generation IS NULL THEN NULL WHEN head.member_id=p_start_member_id THEN 'core' WHEN head.generation=0 THEN 'partner' WHEN head.generation<0 AND head.ancestry[cardinality(head.ancestry)]=1 THEN 'core' WHEN head.generation<0 AND head.ancestry[cardinality(head.ancestry)]=2 THEN 'partner' WHEN head.generation<0 THEN NULL WHEN head.in_law IS FALSE THEN 'core' WHEN head.in_law IS TRUE THEN 'partner' ELSE NULL END ELSE NULL END branch FROM family member LEFT JOIN family head ON head.member_id=member.parent_node_head_ids[1]) SELECT member_id,generation,traversal_depth,discovered_from,discovery_direction,relation_type,in_law,parent_node_key,parent_node_type,parent_node_head_ids,headed_node_keys,sibling_order,lineage,ancestry,branch FROM classified ORDER BY generation NULLS LAST,traversal_depth NULLS LAST,member_id $$;


--
-- Name: family_graph(uuid, date, text, boolean, text, boolean); Type: FUNCTION; Schema: dashboard; Owner: -
--

CREATE FUNCTION dashboard.family_graph(p_start_member_id uuid, p_cut_date date DEFAULT CURRENT_DATE, p_traversal_mode text DEFAULT 'up_down'::text, p_include_partner_branches boolean DEFAULT true, p_pet_visibility text DEFAULT 'all'::text, p_living_people_only boolean DEFAULT false) RETURNS TABLE(node_id uuid, node_type text, generation integer, unit_order integer, unit_position integer, x_order integer, parent_head_ids uuid[], parent_head_id uuid, tail_id uuid, tail_type text, branch text, lineage integer[], ancestry integer[])
    LANGUAGE sql STABLE
    AS $$
WITH RECURSIVE
settings AS (
    SELECT COALESCE(p_cut_date, CURRENT_DATE) AS cut_date
),
family AS MATERIALIZED (
    SELECT member.*
      FROM dashboard.family_branches(
          p_start_member_id,
          p_cut_date,
          p_traversal_mode,
          p_include_partner_branches,
          p_pet_visibility,
          p_living_people_only
      ) AS member
     WHERE member.generation IS NOT NULL
),
graph_paths AS (
    SELECT
        member.member_id,
        member.generation,
        member.traversal_depth,
        ARRAY[]::integer[] AS sort_lineage
      FROM family AS member
     WHERE member.generation = 0
       AND member.discovered_from IS NULL

    UNION ALL

    SELECT
        member.member_id,
        member.generation,
        member.traversal_depth,
        CASE
            WHEN member.generation > source.generation THEN
                source.sort_lineage || ARRAY[
                    CASE member.branch
                        WHEN 'core' THEN 0
                        WHEN 'shared' THEN 1
                        WHEN 'partner' THEN 2
                        ELSE 3
                    END,
                    COALESCE(member.sibling_order, 0)
                ]
            ELSE source.sort_lineage
        END
      FROM graph_paths AS source
      JOIN family AS member
        ON member.discovered_from = source.member_id
       AND member.traversal_depth > source.traversal_depth
),
effective_unions AS (
    SELECT
        union_record.union_id,
        union_record.union_type,
        union_record.union_date,
        union_record.union_date_precision,
        CASE
            WHEN union_record.union_date_precision = 'past' THEN '-infinity'::date
            WHEN union_record.union_date_precision = 'future'
                 AND union_record.union_date IS NULL THEN 'infinity'::date
            WHEN union_record.union_date IS NULL THEN '-infinity'::date
            WHEN union_record.union_date_precision = 'year'
                THEN make_date(extract(year FROM union_record.union_date)::integer, 12, 31)
            WHEN union_record.union_date_precision = 'month'
                THEN (
                    date_trunc('month', union_record.union_date)
                    + interval '1 month - 1 day'
                )::date
            ELSE union_record.union_date
        END AS effective_date
      FROM public.unions AS union_record
      CROSS JOIN settings
     WHERE union_record.union_type IN ('marriage', 'civil')
       AND CASE
               WHEN union_record.union_date_precision = 'past' THEN '-infinity'::date
               WHEN union_record.union_date_precision = 'future'
                    AND union_record.union_date IS NULL THEN 'infinity'::date
               WHEN union_record.union_date IS NULL THEN '-infinity'::date
               WHEN union_record.union_date_precision = 'year'
                   THEN make_date(extract(year FROM union_record.union_date)::integer, 12, 31)
               WHEN union_record.union_date_precision = 'month'
                   THEN (
                       date_trunc('month', union_record.union_date)
                       + interval '1 month - 1 day'
                   )::date
               ELSE union_record.union_date
           END <= settings.cut_date
),
union_groups AS (
    SELECT
        effective_union.union_id,
        effective_union.union_type,
        effective_union.union_date,
        effective_union.union_date_precision,
        effective_union.effective_date,
        array_agg(member.person_id ORDER BY member.person_id) AS head_ids
      FROM effective_unions AS effective_union
      JOIN public.union_members AS member
        ON member.union_id = effective_union.union_id
      JOIN family
        ON family.member_id = member.person_id
     GROUP BY
        effective_union.union_id,
        effective_union.union_type,
        effective_union.union_date,
        effective_union.union_date_precision,
        effective_union.effective_date
    HAVING count(*) = 2
),
selected_unions AS (
    SELECT DISTINCT ON (union_group.head_ids)
        union_group.*
      FROM union_groups AS union_group
     ORDER BY
        union_group.head_ids,
        union_group.effective_date DESC,
        union_group.union_id
),
parent_head_sets AS (
    SELECT DISTINCT
        member.parent_node_key,
        member.parent_node_head_ids AS head_ids
      FROM family AS member
     WHERE cardinality(member.parent_node_head_ids) >= 2
),
junctions AS (
    SELECT
        COALESCE(selected_union.union_id, parent.parent_node_key) AS node_id,
        parent.head_ids,
        selected_union.union_type,
        selected_union.union_date,
        selected_union.union_date_precision,
        selected_union.effective_date
      FROM parent_head_sets AS parent
      LEFT JOIN selected_unions AS selected_union
        ON selected_union.head_ids = parent.head_ids

    UNION ALL

    SELECT
        selected_union.union_id,
        selected_union.head_ids,
        selected_union.union_type,
        selected_union.union_date,
        selected_union.union_date_precision,
        selected_union.effective_date
      FROM selected_unions AS selected_union
     WHERE NOT EXISTS (
         SELECT 1
           FROM parent_head_sets AS parent
          WHERE parent.head_ids = selected_union.head_ids
     )
),
junction_heads AS (
    SELECT
        junction.node_id AS junction_id,
        head.member_id,
        family.generation,
        family.lineage,
        family.ancestry,
        COALESCE(path.sort_lineage, family.lineage) AS graph_lineage,
        family.in_law,
        CASE
            WHEN head.member_id = p_start_member_id THEN 1
            WHEN family.generation = 0 THEN 2
            WHEN family.generation < 0
                THEN COALESCE(
                    family.ancestry[cardinality(family.ancestry)],
                    head.ordinality::integer
                )
            WHEN family.in_law IS FALSE THEN 1
            WHEN family.in_law IS TRUE THEN 2
            ELSE head.ordinality::integer
        END AS side
      FROM junctions AS junction
      CROSS JOIN LATERAL
        unnest(junction.head_ids) WITH ORDINALITY AS head(member_id, ordinality)
      JOIN family
        ON family.member_id = head.member_id
      LEFT JOIN graph_paths AS path
        ON path.member_id = family.member_id
),
preferred_junctions AS (
    SELECT DISTINCT ON (head.member_id)
        head.member_id,
        head.junction_id,
        head.side
      FROM junction_heads AS head
      JOIN junctions AS junction
        ON junction.node_id = head.junction_id
     ORDER BY
        head.member_id,
        (junction.union_type IS NOT NULL) DESC,
        junction.effective_date DESC NULLS LAST,
        head.junction_id
),
parent_connectors AS (
    SELECT
        member.member_id,
        CASE cardinality(member.parent_node_head_ids)
            WHEN 1 THEN member.parent_node_head_ids[1]
            ELSE junction.node_id
        END AS parent_head_id
      FROM family AS member
      LEFT JOIN junctions AS junction
        ON junction.head_ids = member.parent_node_head_ids
),
member_layout AS (
    SELECT
        member.member_id AS node_id,
        tree_member.member_type AS node_type,
        member.generation,
        CASE
            WHEN member.generation > 0
                 AND cardinality(member.lineage) > 0
                THEN COALESCE(own.junction_id, member.member_id)
            ELSE COALESCE(
                own.junction_id,
                connector.parent_head_id,
                member.member_id
            )
        END AS unit_id,
        CASE
            WHEN own.junction_id IS NOT NULL AND member.generation < 0
                 AND cardinality(member.ancestry) > 0
                THEN member.ancestry[1:cardinality(member.ancestry) - 1]
            ELSE member.ancestry
        END AS sort_ancestry,
        CASE
            WHEN member.generation > 0
                THEN COALESCE(path.sort_lineage, member.lineage)
            WHEN own.junction_id IS NULL AND cardinality(member.lineage) > 0
                THEN member.lineage[1:cardinality(member.lineage) - 1]
            ELSE member.lineage
        END AS sort_lineage,
        CASE
            WHEN own.junction_id IS NOT NULL THEN (own.side - 1) * 2
            ELSE 10
                 + CASE member.branch
                       WHEN 'core' THEN 0
                       WHEN 'shared' THEN 1000
                       WHEN 'partner' THEN 2000
                       ELSE 3000
                   END
                 + COALESCE(member.sibling_order, 0)
        END AS position,
        member.parent_node_head_ids AS parent_head_ids,
        connector.parent_head_id,
        own.junction_id,
        member.branch,
        member.lineage,
        member.ancestry
      FROM family AS member
      JOIN tree.members AS tree_member
        ON tree_member.member_id = member.member_id
      LEFT JOIN preferred_junctions AS own
        ON own.member_id = member.member_id
      LEFT JOIN parent_connectors AS connector
        ON connector.member_id = member.member_id
      LEFT JOIN graph_paths AS path
        ON path.member_id = member.member_id
),
junction_anchors AS (
    SELECT DISTINCT ON (head.junction_id)
        head.junction_id,
        head.generation,
        head.lineage,
        head.ancestry,
        head.graph_lineage
      FROM junction_heads AS head
     ORDER BY head.junction_id, head.side, head.member_id
),
junction_layout AS (
    SELECT
        junction.node_id,
        'junction'::text AS node_type,
        anchor.generation,
        junction.node_id AS unit_id,
        CASE
            WHEN anchor.generation < 0
                 AND cardinality(anchor.ancestry) > 0
                THEN anchor.ancestry[1:cardinality(anchor.ancestry) - 1]
            ELSE anchor.ancestry
        END AS sort_ancestry,
        CASE
            WHEN anchor.generation > 0 THEN anchor.graph_lineage
            ELSE anchor.lineage
        END AS sort_lineage,
        1 AS position,
        NULL::uuid[] AS parent_head_ids,
        NULL::uuid AS parent_head_id,
        junction.node_id AS junction_id,
        NULL::text AS branch,
        anchor.lineage,
        anchor.ancestry,
        junction.union_type,
        junction.union_date,
        junction.union_date_precision
      FROM junctions AS junction
      JOIN junction_anchors AS anchor
        ON anchor.junction_id = junction.node_id
),
all_nodes AS (
    SELECT
        member.node_id,
        member.node_type,
        member.generation,
        member.unit_id,
        member.sort_ancestry,
        member.sort_lineage,
        member.position,
        member.parent_head_ids,
        member.parent_head_id,
        member.junction_id,
        member.branch,
        member.lineage,
        member.ancestry,
        NULL::text AS union_type,
        NULL::date AS union_date,
        NULL::text AS union_date_precision
      FROM member_layout AS member

    UNION ALL

    SELECT * FROM junction_layout
),
ranked_nodes AS (
    SELECT
        node.*,
        dense_rank() OVER (
            PARTITION BY node.generation
            ORDER BY node.sort_ancestry, node.sort_lineage, node.unit_id
        )::integer AS unit_order,
        row_number() OVER (
            PARTITION BY node.generation
            ORDER BY
                node.sort_ancestry,
                node.sort_lineage,
                node.unit_id,
                node.position,
                node.node_id
        )::integer AS x_order
      FROM all_nodes AS node
),
nodes_with_tails AS (
    SELECT
        node.*,
        lead(node.node_id) OVER (
            PARTITION BY node.generation
            ORDER BY node.x_order
        ) AS tail_id,
        lead(node.node_type) OVER (
            PARTITION BY node.generation
            ORDER BY node.x_order
        ) AS tail_node_type,
        lead(node.junction_id) OVER (
            PARTITION BY node.generation
            ORDER BY node.x_order
        ) AS tail_junction_id
      FROM ranked_nodes AS node
)
SELECT
    node.node_id,
    node.node_type,
    node.generation,
    node.unit_order,
    node.position AS unit_position,
    node.x_order,
    node.parent_head_ids,
    node.parent_head_id,
    node.tail_id,
    CASE
        WHEN node.union_type IS NOT NULL
             AND node.tail_junction_id = node.node_id THEN 'union'
        WHEN node.tail_node_type = 'junction'
             AND node.junction_id = node.tail_id
             AND EXISTS (
                 SELECT 1 FROM junctions AS junction
                  WHERE junction.node_id = node.tail_id
                    AND junction.union_type IS NOT NULL
             ) THEN 'union'
        ELSE 'order'
    END AS tail_type,
    node.branch,
    node.lineage,
    node.ancestry--,
--    node.union_type,
--    node.union_date,
--    node.union_date_precision
  FROM nodes_with_tails AS node
 ORDER BY node.generation, node.x_order;
$$;


--
-- Name: family_members(uuid, date, text, boolean, text, boolean); Type: FUNCTION; Schema: dashboard; Owner: -
--

CREATE FUNCTION dashboard.family_members(p_start_member_id uuid, p_cut_date date DEFAULT CURRENT_DATE, p_traversal_mode text DEFAULT 'up_down'::text, p_include_partner_branches boolean DEFAULT true, p_pet_visibility text DEFAULT 'all'::text, p_living_people_only boolean DEFAULT false) RETURNS TABLE(member_id uuid, generation integer, traversal_depth integer, discovered_from uuid, discovery_direction text, relation_type text, in_law boolean, parent_node_key uuid, parent_node_type text, parent_node_head_ids uuid[], headed_node_keys uuid[], sibling_order integer, lineage integer[], ancestry integer[])
    LANGUAGE plpgsql STABLE
    AS $$
DECLARE
    v_cut_date date := COALESCE(p_cut_date, CURRENT_DATE);
    v_pet_visibility text := COALESCE(p_pet_visibility, 'all');
    v_living_people_only boolean := COALESCE(p_living_people_only, false);
BEGIN
    IF p_start_member_id IS NULL THEN
        RAISE EXCEPTION 'A starting dashboard member is required.';
    END IF;

    IF p_traversal_mode NOT IN ('up', 'down', 'up_down', 'bidirectional') THEN
        RAISE EXCEPTION
            'Unsupported traversal mode: %. Expected up, down, up_down, or bidirectional.',
            p_traversal_mode;
    END IF;

    IF v_pet_visibility NOT IN ('all', 'living', 'none') THEN
        RAISE EXCEPTION
            'Unsupported pet visibility: %. Expected all, living, or none.',
            v_pet_visibility;
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM tree.members AS member
         WHERE member.member_id = p_start_member_id
    ) THEN
        RAISE EXCEPTION 'Unknown dashboard member: %', p_start_member_id;
    END IF;

    RETURN QUERY
    WITH RECURSIVE
    members AS (
        SELECT
            person.person_id AS member_id,
            'person'::text AS member_type,
            CASE
                WHEN person.birth_date_precision = 'past' THEN '-infinity'::date
                WHEN person.birth_date_precision = 'future'
                     AND person.birth_date IS NULL THEN 'infinity'::date
                WHEN person.birth_date IS NULL THEN '-infinity'::date
                WHEN person.birth_date_precision = 'year'
                    THEN make_date(
                        extract(year FROM person.birth_date)::integer,
                        12,
                        31
                    )
                WHEN person.birth_date_precision = 'month'
                    THEN (
                        date_trunc('month', person.birth_date)
                        + interval '1 month - 1 day'
                    )::date
                ELSE person.birth_date::date
            END AS entry_date,
            person.birth_date::date AS sort_date
          FROM public.persons AS person
         WHERE NOT v_living_people_only
            OR NOT (
                COALESCE(person.death_date::date < v_cut_date, false)
                OR COALESCE(person.death_date_precision = 'past', false)
            )

        UNION ALL

        SELECT
            animal.animal_id AS member_id,
            'animal'::text AS member_type,
            CASE
                WHEN animal.birth_date_precision = 'past' THEN '-infinity'::date
                WHEN animal.birth_date_precision = 'future'
                     AND animal.birth_date IS NULL THEN 'infinity'::date
                WHEN animal.birth_date IS NULL THEN '-infinity'::date
                WHEN animal.birth_date_precision = 'year'
                    THEN make_date(extract(year FROM animal.birth_date)::integer, 12, 31)
                WHEN animal.birth_date_precision = 'month'
                    THEN (
                        date_trunc('month', animal.birth_date)
                        + interval '1 month - 1 day'
                    )::date
                ELSE animal.birth_date::date
            END AS entry_date,
            animal.birth_date AS sort_date
          FROM public.animals AS animal
         WHERE v_pet_visibility = 'all'
            OR (
                v_pet_visibility = 'living'
                AND NOT (
                    COALESCE(animal.death_date::date < v_cut_date, false)
                    OR COALESCE(animal.death_date_precision = 'past', false)
                )
            )
    ),
    present_members AS (
        SELECT member.member_id, member.member_type, member.entry_date, member.sort_date
          FROM members AS member
         WHERE member.entry_date <= v_cut_date
    ),
    effective_pet_relationships AS (
        SELECT
            pet.owner_id,
            pet.pet_id,
            pet.relation_type
          FROM public.pets AS pet
          JOIN present_members AS present_owner
            ON present_owner.member_id = pet.owner_id
          JOIN present_members AS present_pet
            ON present_pet.member_id = pet.pet_id
           AND present_pet.member_type = 'animal'
         WHERE CASE
                   WHEN pet.gotcha_date_precision = 'past' THEN '-infinity'::date
                   WHEN pet.gotcha_date_precision = 'future'
                        AND pet.gotcha_date IS NULL THEN 'infinity'::date
                   WHEN pet.gotcha_date IS NULL THEN '-infinity'::date
                   WHEN pet.gotcha_date_precision = 'year'
                       THEN make_date(extract(year FROM pet.gotcha_date)::integer, 12, 31)
                   WHEN pet.gotcha_date_precision = 'month'
                       THEN (
                           date_trunc('month', pet.gotcha_date)
                           + interval '1 month - 1 day'
                       )::date
                   ELSE pet.gotcha_date::date
               END <= v_cut_date
    ),
    effective_unions AS (
        SELECT union_record.union_id, union_record.union_type
          FROM public.unions AS union_record
         WHERE union_record.union_type IN ('marriage', 'civil')
           AND CASE
                   WHEN union_record.union_date_precision = 'past' THEN '-infinity'::date
                   WHEN union_record.union_date_precision = 'future'
                        AND union_record.union_date IS NULL THEN 'infinity'::date
                   WHEN union_record.union_date IS NULL THEN '-infinity'::date
                   WHEN union_record.union_date_precision = 'year'
                       THEN make_date(extract(year FROM union_record.union_date)::integer, 12, 31)
                   WHEN union_record.union_date_precision = 'month'
                       THEN (
                           date_trunc('month', union_record.union_date)
                           + interval '1 month - 1 day'
                       )::date
                   ELSE union_record.union_date::date
               END <= v_cut_date
    ),
    structural_links AS (
        SELECT DISTINCT
            parent.child_id AS dependent_id,
            parent.parent_id AS head_id,
            'person'::text AS dependent_type,
            parent.relation_type,
            present_child.sort_date
          FROM public.parents AS parent
          JOIN present_members AS present_parent
            ON present_parent.member_id = parent.parent_id
          JOIN present_members AS present_child
            ON present_child.member_id = parent.child_id

        UNION

        SELECT DISTINCT
            pet.pet_id AS dependent_id,
            pet.owner_id AS head_id,
            'animal'::text AS dependent_type,
            pet.relation_type,
            COALESCE(present_pet.sort_date, public_pet.gotcha_date::date) AS sort_date
          FROM effective_pet_relationships AS pet
          JOIN public.pets AS public_pet
            ON public_pet.pet_id = pet.pet_id
           AND public_pet.owner_id = pet.owner_id
          JOIN present_members AS present_owner
            ON present_owner.member_id = pet.owner_id
          JOIN present_members AS present_pet
            ON present_pet.member_id = pet.pet_id
    ),
    node_heads AS (
        SELECT DISTINCT
            link.dependent_id,
            link.dependent_type,
            link.head_id,
            link.sort_date,
            head.member_type AS head_type,
            head.sort_date AS head_sort_date
          FROM structural_links AS link
          JOIN present_members AS head
            ON head.member_id = link.head_id
    ),
    node_head_sets AS (
        SELECT
            link.dependent_id,
            link.dependent_type,
            array_agg(DISTINCT link.head_id ORDER BY link.head_id) AS head_ids,
            array_agg(
                link.head_id
                ORDER BY
                    CASE link.head_type WHEN 'person' THEN 0 ELSE 1 END,
                    link.head_sort_date NULLS LAST,
                    link.head_id
            ) AS ordered_head_ids,
            max(link.sort_date) AS sort_date
          FROM node_heads AS link
         GROUP BY link.dependent_id, link.dependent_type
    ),
    classified_nodes AS (
        SELECT
            head_set.dependent_id AS member_id,
            public.uuid_generate_v5(
                '6ba7b811-9dad-11d1-80b4-00c04fd430c8'::uuid,
                'dashboard.family-node:v1:heads:'
                || array_to_string(head_set.head_ids, ':')
            ) AS node_key,
            CASE cardinality(head_set.head_ids)
                WHEN 1 THEN 'solo'
                WHEN 2 THEN 'pair'
                ELSE 'multiple'
            END AS node_type,
            head_set.head_ids,
            head_set.ordered_head_ids,
            head_set.dependent_type,
            head_set.sort_date
          FROM node_head_sets AS head_set
    ),
    node_members AS (
        SELECT
            node.member_id,
            node.node_key,
            node.node_type,
            node.head_ids,
            node.ordered_head_ids,
            row_number() OVER (
                PARTITION BY node.node_key
                ORDER BY
                    CASE node.dependent_type WHEN 'person' THEN 0 ELSE 1 END,
                    node.sort_date NULLS LAST,
                    node.member_id
            )::integer AS sibling_order
          FROM classified_nodes AS node
    ),
    headed_nodes AS (
        SELECT
            head.head_id AS member_id,
            array_agg(DISTINCT node.node_key ORDER BY node.node_key) AS node_keys
          FROM classified_nodes AS node
          CROSS JOIN LATERAL unnest(node.head_ids) AS head(head_id)
         GROUP BY head.head_id
    ),
    partner_pairs AS (
        SELECT DISTINCT
            member_1.person_id AS member_id_1,
            member_2.person_id AS member_id_2,
            effective_union.union_type
          FROM effective_unions AS effective_union
          JOIN public.union_members AS member_1
            ON member_1.union_id = effective_union.union_id
          JOIN public.union_members AS member_2
            ON member_2.union_id = effective_union.union_id
           AND member_1.person_id <> member_2.person_id
          JOIN present_members AS present_1
            ON present_1.member_id = member_1.person_id
          JOIN present_members AS present_2
            ON present_2.member_id = member_2.person_id
    ),
    edges AS (
        SELECT DISTINCT
            parent.parent_id AS source_id,
            parent.child_id AS target_id,
            1 AS generation_delta,
            'down'::text AS edge_direction,
            parent.relation_type
          FROM public.parents AS parent
          JOIN present_members AS present_parent
            ON present_parent.member_id = parent.parent_id
          JOIN present_members AS present_child
            ON present_child.member_id = parent.child_id

        UNION

        SELECT DISTINCT
            parent.child_id AS source_id,
            parent.parent_id AS target_id,
            -1 AS generation_delta,
            'up'::text AS edge_direction,
            parent.relation_type
          FROM public.parents AS parent
          JOIN present_members AS present_parent
            ON present_parent.member_id = parent.parent_id
          JOIN present_members AS present_child
            ON present_child.member_id = parent.child_id

        UNION

        SELECT DISTINCT
            pet.owner_id AS source_id,
            pet.pet_id AS target_id,
            1 AS generation_delta,
            'down'::text AS edge_direction,
            pet.relation_type
          FROM effective_pet_relationships AS pet
          JOIN present_members AS present_owner
            ON present_owner.member_id = pet.owner_id
          JOIN present_members AS present_pet
            ON present_pet.member_id = pet.pet_id

        UNION

        SELECT DISTINCT
            pet.pet_id AS source_id,
            pet.owner_id AS target_id,
            -1 AS generation_delta,
            'up'::text AS edge_direction,
            pet.relation_type
          FROM effective_pet_relationships AS pet
          JOIN present_members AS present_owner
            ON present_owner.member_id = pet.owner_id
          JOIN present_members AS present_pet
            ON present_pet.member_id = pet.pet_id

        UNION

        SELECT DISTINCT
            partner.member_id_1 AS source_id,
            partner.member_id_2 AS target_id,
            0 AS generation_delta,
            'partner'::text AS edge_direction,
            partner.union_type AS relation_type
          FROM partner_pairs AS partner
         WHERE p_include_partner_branches
    ),
    opening_members AS (
        SELECT p_start_member_id AS member_id

        UNION

        SELECT partner.member_id_2
          FROM partner_pairs AS partner
         WHERE p_include_partner_branches
           AND partner.member_id_1 = p_start_member_id
    ),
    ordered_opening_members AS (
        SELECT
            opening.member_id,
            row_number() OVER (
                ORDER BY
                    CASE WHEN opening.member_id = p_start_member_id THEN 0 ELSE 1 END,
                    opening.member_id
            )::integer AS opening_order
          FROM opening_members AS opening
    ),
    seeds AS (
        SELECT
            opening.member_id,
            0 AS generation,
            0 AS traversal_depth,
            NULL::uuid AS discovered_from,
            CASE
                WHEN p_traversal_mode = 'up_down' THEN mode.direction
                ELSE p_traversal_mode
            END AS walk_direction,
            'seed'::text AS discovery_direction,
            'opening'::text AS relation_type,
            false AS in_law,
            opening.opening_order,
            ARRAY[]::integer[] AS lineage,
            ARRAY[]::integer[] AS ancestry,
            ARRAY[opening.member_id]::uuid[] AS member_path
          FROM ordered_opening_members AS opening
          CROSS JOIN LATERAL (
              SELECT 'up'::text AS direction
               WHERE p_traversal_mode = 'up_down'
              UNION ALL
              SELECT 'down'::text AS direction
               WHERE p_traversal_mode = 'up_down'
              UNION ALL
              SELECT p_traversal_mode
               WHERE p_traversal_mode <> 'up_down'
          ) AS mode
    ),
    walk AS (
        SELECT * FROM seeds

        UNION ALL

        SELECT
            edge.target_id,
            walk.generation + edge.generation_delta,
            walk.traversal_depth + 1,
            walk.member_id,
            walk.walk_direction,
            edge.edge_direction,
            edge.relation_type,
            walk.in_law
                OR (
                    edge.edge_direction = 'partner'
                    AND NOT EXISTS (
                        SELECT 1
                          FROM opening_members AS opening
                         WHERE opening.member_id = edge.target_id
                    )
                ),
            walk.opening_order,
            CASE edge.edge_direction
                WHEN 'down' THEN
                    walk.lineage || COALESCE(target_node.sibling_order, 0)
                WHEN 'up' THEN
                    CASE
                        WHEN cardinality(walk.lineage) > 0
                            THEN walk.lineage[1:cardinality(walk.lineage) - 1]
                        ELSE ARRAY[]::integer[]
                    END
                ELSE walk.lineage
            END,
            CASE edge.edge_direction
                WHEN 'up' THEN
                    walk.ancestry
                    || CASE
                           WHEN cardinality(walk.ancestry) = 0 THEN
                               ARRAY[
                                   walk.opening_order,
                                   COALESCE(
                                       array_position(
                                           source_node.ordered_head_ids,
                                           edge.target_id
                                       ),
                                       0
                                   )
                               ]
                           ELSE ARRAY[
                               COALESCE(
                                   array_position(
                                       source_node.ordered_head_ids,
                                       edge.target_id
                                   ),
                                   0
                               )
                           ]
                       END
                ELSE walk.ancestry
            END,
            walk.member_path || edge.target_id
          FROM walk
          JOIN edges AS edge
            ON edge.source_id = walk.member_id
          LEFT JOIN node_members AS target_node
            ON target_node.member_id = edge.target_id
          LEFT JOIN node_members AS source_node
            ON source_node.member_id = walk.member_id
         WHERE edge.target_id <> ALL(walk.member_path)
           AND (
               walk.walk_direction = 'bidirectional'
               OR edge.edge_direction = 'partner'
               OR edge.edge_direction = walk.walk_direction
           )
    ),
    ranked AS (
        SELECT
            walk.member_id,
            walk.generation,
            walk.traversal_depth,
            walk.discovered_from,
            walk.discovery_direction,
            walk.relation_type,
            walk.in_law,
            walk.lineage,
            walk.ancestry,
            row_number() OVER (
                PARTITION BY walk.member_id
                ORDER BY
                    walk.in_law,
                    abs(walk.generation),
                    walk.generation DESC,
                    walk.traversal_depth,
                    walk.discovery_direction,
                    walk.discovered_from NULLS FIRST
            ) AS preference
          FROM walk
    )
    SELECT
        information.member_id,
        ranked.generation,
        ranked.traversal_depth,
        ranked.discovered_from,
        ranked.discovery_direction,
        ranked.relation_type,
        ranked.in_law,
        node_member.node_key,
        node_member.node_type,
        node_member.head_ids,
        headed_node.node_keys,
        node_member.sibling_order,
        ranked.lineage,
        ranked.ancestry
      FROM members AS information
      LEFT JOIN ranked
       ON ranked.member_id = information.member_id
       AND ranked.preference = 1
      LEFT JOIN node_members AS node_member
        ON node_member.member_id = information.member_id
      LEFT JOIN headed_nodes AS headed_node
        ON headed_node.member_id = information.member_id
     ORDER BY
        ranked.generation NULLS LAST,
        ranked.traversal_depth NULLS LAST,
        information.member_id;
END;
$$;


--
-- Name: family_timeline(uuid, date, text, boolean); Type: FUNCTION; Schema: dashboard; Owner: -
--

CREATE FUNCTION dashboard.family_timeline(p_start_member_id uuid, p_cut_date date DEFAULT CURRENT_DATE, p_traversal_mode text DEFAULT 'down'::text, p_include_partner_branches boolean DEFAULT true) RETURNS TABLE(member_id uuid, generation integer, traversal_depth integer, discovered_from uuid, discovery_direction text, relation_type text, in_law boolean, parent_node_key uuid, parent_node_type text, parent_node_head_ids uuid[], headed_node_keys uuid[], sibling_order integer, lineage integer[], ancestry integer[], display_unit_key uuid, display_unit_generation integer, display_unit_lineage integer[], display_unit_ancestry integer[], display_unit_depth integer, display_unit_order integer, display_role text, display_order integer)
    LANGUAGE sql STABLE
    AS $$
WITH
settings AS (
    SELECT COALESCE(p_cut_date, CURRENT_DATE) AS cut_date
),
family AS (
    SELECT member.*
      FROM dashboard.family_members(
          p_start_member_id,
          p_cut_date,
          p_traversal_mode,
          p_include_partner_branches,
          'all',
          false
      ) AS member
),
effective_unions AS (
    SELECT
        union_record.union_id,
        CASE
            WHEN union_record.union_date_precision = 'past' THEN '-infinity'::date
            WHEN union_record.union_date_precision = 'future'
                 AND union_record.union_date IS NULL THEN 'infinity'::date
            WHEN union_record.union_date IS NULL THEN '-infinity'::date
            WHEN union_record.union_date_precision = 'year'
                THEN make_date(extract(year FROM union_record.union_date)::integer, 12, 31)
            WHEN union_record.union_date_precision = 'month'
                THEN (
                    date_trunc('month', union_record.union_date)
                    + interval '1 month - 1 day'
                )::date
            ELSE union_record.union_date::date
        END AS effective_date
      FROM public.unions AS union_record
      CROSS JOIN settings
     WHERE union_record.union_type IN ('marriage', 'civil')
       AND CASE
               WHEN union_record.union_date_precision = 'past' THEN '-infinity'::date
               WHEN union_record.union_date_precision = 'future'
                    AND union_record.union_date IS NULL THEN 'infinity'::date
               WHEN union_record.union_date IS NULL THEN '-infinity'::date
               WHEN union_record.union_date_precision = 'year'
                   THEN make_date(extract(year FROM union_record.union_date)::integer, 12, 31)
               WHEN union_record.union_date_precision = 'month'
                   THEN (
                       date_trunc('month', union_record.union_date)
                       + interval '1 month - 1 day'
                   )::date
               ELSE union_record.union_date::date
           END <= settings.cut_date
),
partner_units AS (
    SELECT
        effective_union.union_id,
        public.uuid_generate_v5(
            '6ba7b811-9dad-11d1-80b4-00c04fd430c8'::uuid,
            'dashboard.family-node:v1:heads:'
            || array_to_string(
                array_agg(union_member.person_id ORDER BY union_member.person_id),
                ':'
            )
        ) AS unit_key,
        array_agg(union_member.person_id ORDER BY union_member.person_id) AS member_ids,
        effective_union.effective_date
      FROM effective_unions AS effective_union
      JOIN public.union_members AS union_member
        ON union_member.union_id = effective_union.union_id
      JOIN family
        ON family.member_id = union_member.person_id
       AND family.generation IS NOT NULL
     GROUP BY effective_union.union_id, effective_union.effective_date
    HAVING count(*) >= 2
),
human_parent_units AS (
    SELECT DISTINCT
        head.member_id,
        dependent.parent_node_key AS unit_key
      FROM family AS dependent
      JOIN dashboard.member_information AS information
        ON information.member_id = dependent.member_id
      CROSS JOIN LATERAL unnest(dependent.parent_node_head_ids) AS head(member_id)
     WHERE dependent.generation IS NOT NULL
       AND information.member_type = 'person'
),
unit_candidates AS (
    SELECT
        partner.member_id,
        partner_unit.unit_key,
        0 AS unit_priority,
        partner_unit.effective_date
      FROM partner_units AS partner_unit
      CROSS JOIN LATERAL unnest(partner_unit.member_ids) AS partner(member_id)

    UNION ALL

    SELECT
        parent.member_id,
        parent.unit_key,
        1 AS unit_priority,
        NULL::date AS effective_date
      FROM human_parent_units AS parent

    UNION ALL

    SELECT
        family.member_id,
        public.uuid_generate_v5(
            '6ba7b811-9dad-11d1-80b4-00c04fd430c8'::uuid,
            'dashboard.family-node:v1:heads:' || family.member_id::text
        ),
        2 AS unit_priority,
        (information.birth_date + interval '30 years')::date AS effective_date
      FROM family
      JOIN dashboard.member_information AS information
        ON information.member_id = family.member_id
      CROSS JOIN settings
     WHERE family.generation IS NOT NULL
       AND information.member_type = 'person'
       AND (
           information.birth_date::date + interval '30 years' <= settings.cut_date
           OR information.birth_date_precision = 'past'
           OR information.birth_date_precision IS NULL
       )
),
selected_own_units AS (
    SELECT DISTINCT ON (candidate.member_id)
        candidate.member_id,
        candidate.unit_key
      FROM unit_candidates AS candidate
     ORDER BY
        candidate.member_id,
        candidate.unit_priority,
        candidate.effective_date DESC NULLS LAST,
        candidate.unit_key
),
parent_unit_options AS (
    SELECT
        dependent.member_id,
        head_unit.unit_key
      FROM family AS dependent
      CROSS JOIN LATERAL unnest(dependent.parent_node_head_ids) AS head(member_id)
      JOIN selected_own_units AS head_unit
        ON head_unit.member_id = head.member_id
     WHERE dependent.generation IS NOT NULL
),
parent_unit_redirects AS (
    SELECT
        option.member_id,
        CASE
            WHEN count(DISTINCT option.unit_key) = 1
                THEN (array_agg(DISTINCT option.unit_key))[1]
        END AS unit_key
      FROM parent_unit_options AS option
     GROUP BY option.member_id
),
initial_assignments AS (
    SELECT
        family.*,
        own_unit.unit_key AS own_unit_key,
        COALESCE(
            own_unit.unit_key,
            parent_redirect.unit_key,
            family.parent_node_key,
            public.uuid_generate_v5(
                '6ba7b811-9dad-11d1-80b4-00c04fd430c8'::uuid,
                'dashboard.family-node:v1:heads:' || family.member_id::text
            )
        ) AS provisional_unit_key,
        information.member_type,
        information.birth_date,
        information.entry_date
      FROM family
      JOIN dashboard.member_information AS information
        ON information.member_id = family.member_id
      LEFT JOIN selected_own_units AS own_unit
        ON own_unit.member_id = family.member_id
      LEFT JOIN parent_unit_redirects AS parent_redirect
        ON parent_redirect.member_id = family.member_id
     WHERE family.generation IS NOT NULL
),
animal_unit_options AS (
    SELECT
        animal.member_id,
        owner.provisional_unit_key AS unit_key
      FROM initial_assignments AS animal
      CROSS JOIN LATERAL unnest(animal.parent_node_head_ids) AS head(member_id)
      JOIN initial_assignments AS owner
        ON owner.member_id = head.member_id
       AND owner.member_type = 'person'
     WHERE animal.member_type = 'animal'
),
animal_unit_redirects AS (
    SELECT
        option.member_id,
        CASE
            WHEN count(DISTINCT option.unit_key) = 1
                THEN (array_agg(DISTINCT option.unit_key))[1]
        END AS unit_key
      FROM animal_unit_options AS option
     GROUP BY option.member_id
),
assigned_units AS (
    SELECT
        initial.*,
        CASE
            WHEN initial.member_type = 'animal'
                THEN COALESCE(animal_redirect.unit_key, initial.provisional_unit_key)
            ELSE initial.provisional_unit_key
        END AS unit_key
      FROM initial_assignments AS initial
      LEFT JOIN animal_unit_redirects AS animal_redirect
        ON animal_redirect.member_id = initial.member_id
),
unit_anchors AS (
    SELECT DISTINCT ON (assigned.unit_key)
        assigned.unit_key,
        CASE
            WHEN assigned.own_unit_key = assigned.unit_key THEN assigned.generation
            ELSE assigned.generation - 1
        END AS unit_generation,
        CASE
            WHEN assigned.own_unit_key = assigned.unit_key THEN assigned.lineage
            WHEN cardinality(assigned.lineage) > 0
                THEN assigned.lineage[1:cardinality(assigned.lineage) - 1]
            ELSE ARRAY[]::integer[]
        END AS unit_lineage,
        assigned.ancestry AS unit_ancestry
      FROM assigned_units AS assigned
     ORDER BY
        assigned.unit_key,
        CASE WHEN assigned.own_unit_key = assigned.unit_key THEN 0 ELSE 1 END,
        assigned.in_law,
        cardinality(assigned.lineage),
        assigned.member_id
),
unit_rankings AS (
    SELECT
        anchor.*,
        row_number() OVER (
            ORDER BY
                anchor.unit_generation,
                anchor.unit_lineage,
                anchor.unit_ancestry,
                anchor.unit_key
        )::integer AS unit_order
      FROM unit_anchors AS anchor
),
display_members AS (
    SELECT
        assigned.*,
        unit.unit_generation,
        unit.unit_lineage,
        unit.unit_ancestry,
        unit.unit_order,
        CASE
            WHEN assigned.member_type = 'animal' THEN 'animal'
            WHEN assigned.own_unit_key = assigned.unit_key AND assigned.in_law
                THEN 'partner'
            WHEN assigned.own_unit_key = assigned.unit_key THEN 'head'
            ELSE 'dependent'
        END AS unit_role
      FROM assigned_units AS assigned
      JOIN unit_rankings AS unit
        ON unit.unit_key = assigned.unit_key
)
SELECT
    display.member_id,
    display.generation,
    display.traversal_depth,
    display.discovered_from,
    display.discovery_direction,
    display.relation_type,
    display.in_law,
    display.parent_node_key,
    display.parent_node_type,
    display.parent_node_head_ids,
    display.headed_node_keys,
    display.sibling_order,
    display.lineage,
    display.ancestry,
    display.unit_key AS display_unit_key,
    display.unit_generation AS display_unit_generation,
    display.unit_lineage AS display_unit_lineage,
    display.unit_ancestry AS display_unit_ancestry,
    cardinality(display.unit_lineage)::integer AS display_unit_depth,
    display.unit_order AS display_unit_order,
    display.unit_role AS display_role,
    row_number() OVER (
        PARTITION BY display.unit_key
        ORDER BY
            CASE display.unit_role
                WHEN 'head' THEN 0
                WHEN 'partner' THEN 1
                WHEN 'dependent' THEN 2
                ELSE 3
            END,
            display.sibling_order NULLS LAST,
            COALESCE(display.birth_date, display.entry_date) NULLS LAST,
            display.member_id
    )::integer AS display_order
  FROM display_members AS display
 ORDER BY
    display.unit_order,
    display_order;
$$;


--
-- Name: founder_id(); Type: FUNCTION; Schema: nello; Owner: -
--

CREATE FUNCTION nello.founder_id() RETURNS uuid
    LANGUAGE sql STABLE
    AS $$
  SELECT founder_id FROM nello.founder
$$;


--
-- Name: check_union_member_limit(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.check_union_member_limit() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN -- Serialize concurrent membership changes for this union.
  PERFORM 1 FROM unions WHERE union_id = NEW.union_id FOR UPDATE;
  IF ( SELECT count(*) FROM union_members WHERE union_id = NEW.union_id ) > 2
  THEN RAISE EXCEPTION 'A union cannot have more than two members (union_id: %)',
  NEW.union_id; END IF; RETURN NULL; END;
  $$;


--
-- Name: generation_to_text(integer, boolean); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.generation_to_text(gen integer, plural boolean DEFAULT true) RETURNS text
    LANGUAGE plpgsql IMMUTABLE
    AS $$
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
$$;


--
-- Name: show_db_tree(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.show_db_tree() RETURNS TABLE(tree_structure text)
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- First show all databases
    RETURN QUERY
    SELECT ':file_folder: ' || datname || ' (DATABASE)'
    FROM pg_database 
    WHERE datistemplate = false;

    -- Then show current database structure
    RETURN QUERY
    WITH RECURSIVE 
    -- Get schemas
    schemas AS (
        SELECT 
            n.nspname AS object_name,
            1 AS level,
            n.nspname AS path,
            'SCHEMA' AS object_type
        FROM pg_namespace n
        WHERE n.nspname NOT LIKE 'pg_%' 
        AND n.nspname != 'information_schema'
    ),

    -- Get all objects (tables, views, functions, etc.)
    objects AS (
        SELECT 
            c.relname AS object_name,
            2 AS level,
            s.path || ' → ' || c.relname AS path,
            CASE c.relkind
                WHEN 'r' THEN 'TABLE'
                WHEN 'v' THEN 'VIEW'
                WHEN 'm' THEN 'MATERIALIZED VIEW'
                WHEN 'i' THEN 'INDEX'
                WHEN 'S' THEN 'SEQUENCE'
                WHEN 'f' THEN 'FOREIGN TABLE'
            END AS object_type
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN schemas s ON n.nspname = s.object_name
        WHERE c.relkind IN ('r','v','m','i','S','f')

        UNION ALL

        SELECT 
            p.proname AS object_name,
            2 AS level,
            s.path || ' → ' || p.proname AS path,
            'FUNCTION' AS object_type
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        JOIN schemas s ON n.nspname = s.object_name
    ),

    -- Combine schemas and objects
    combined AS (
        SELECT * FROM schemas
        UNION ALL
        SELECT * FROM objects
    )

    -- Final output with tree-like formatting
    SELECT 
        REPEAT('    ', level) || 
        CASE 
            WHEN level = 1 THEN '└── :open_file_folder: '
            ELSE '    └── ' || 
                CASE object_type
                    WHEN 'TABLE' THEN ':bar_chart: '
                    WHEN 'VIEW' THEN ':eye: '
                    WHEN 'MATERIALIZED VIEW' THEN ':newspaper: '
                    WHEN 'FUNCTION' THEN ':zap: '
                    WHEN 'INDEX' THEN ':mag: '
                    WHEN 'SEQUENCE' THEN ':1234: '
                    WHEN 'FOREIGN TABLE' THEN ':globe_with_meridians: '
                    ELSE ''
                END
        END || object_name || ' (' || object_type || ')'
    FROM combined
    ORDER BY path;
END;
$$;


--
-- Name: suffix_to_text(integer, boolean); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.suffix_to_text(x integer, with_space boolean DEFAULT true) RETURNS text
    LANGUAGE plpgsql IMMUTABLE
    AS $$
DECLARE
  n int := x;
  res text := NULL;           -- will stay NULL unless we build a valid suffix
  numerals int[];
  symbols  text[];
  i int;
BEGIN
  -- build result for valid values
  IF n = 1 THEN
    res := 'Sr';
  ELSIF n = 2 THEN
    res := 'Jr';
  ELSIF n >= 3 AND n <= 3000 THEN
    numerals := ARRAY[1000,900,500,400,100,90,50,40,10,9,5,4,1];
    symbols  := ARRAY['M','CM','D','CD','C','XC','L','XL','X','IX','V','IV','I'];
    FOR i IN 1..array_length(numerals,1) LOOP
      WHILE n >= numerals[i] LOOP
        res := COALESCE(res, '') || symbols[i];
        n := n - numerals[i];
      END LOOP;
    END LOOP;
  END IF;

  -- no valid suffix → return empty string (so concatenation is safe)
  IF res IS NULL OR res = '' THEN
    RETURN '';
  END IF;

  -- valid suffix: optionally prepend a space
  IF with_space THEN
    RETURN ' ' || res;
  ELSE
    RETURN res;
  END IF;
END;
$$;


--
-- Name: __columns_used; Type: VIEW; Schema: _debugging; Owner: -
--

CREATE VIEW _debugging.__columns_used AS
 SELECT table_schema AS schema_nsp,
    table_name,
    column_name,
        CASE
            WHEN ((data_type)::text = 'USER-DEFINED'::text) THEN (udt_name)::name
            ELSE (data_type)::name
        END AS data_type,
    is_nullable,
    column_default,
        CASE
            WHEN (domain_name IS NOT NULL) THEN (((domain_schema)::text || '.'::text) || (domain_name)::text)
            ELSE NULL::text
        END AS domain_name,
    is_generated,
    generation_expression
   FROM information_schema.columns c
  WHERE ((table_schema)::name <> ALL (ARRAY['pgrst'::name, 'pg_catalog'::name, 'auth'::name, 'neon_auth'::name, 'information_schema'::name, '_debugging'::name]))
  ORDER BY ((table_schema)::name = 'public'::name) DESC, table_schema, table_name, ordinal_position;


--
-- Name: __constraints_used; Type: VIEW; Schema: _debugging; Owner: -
--

CREATE VIEW _debugging.__constraints_used AS
 SELECT n.nspname AS schema_nsp,
    cls.relname AS table_named,
    con.conname AS constraint_named,
    con.contype AS constraint_type,
    pg_get_constraintdef(con.oid) AS definition
   FROM ((pg_constraint con
     JOIN pg_namespace n ON ((n.oid = con.connamespace)))
     JOIN pg_class cls ON ((cls.oid = con.conrelid)))
  WHERE (n.nspname <> ALL (ARRAY['pgrst'::name, 'pg_catalog'::name, 'auth'::name, 'neon_auth'::name, 'information_schema'::name]))
  ORDER BY (n.nspname = 'public'::name) DESC, n.nspname, cls.relname, con.conname;


--
-- Name: __custom_types_used; Type: VIEW; Schema: _debugging; Owner: -
--

CREATE VIEW _debugging.__custom_types_used AS
 SELECT n.nspname AS schema_nsp,
    t.typname AS type_name,
    t.typtype AS type_type,
        CASE t.typtype
            WHEN 'e'::"char" THEN ( SELECT string_agg((e.enumlabel)::text, ', '::text ORDER BY e.enumsortorder) AS string_agg
               FROM pg_enum e
              WHERE (e.enumtypid = t.oid))
            WHEN 'r'::"char" THEN ( SELECT format('range of %s'::text, format_type(r.rngsubtype, NULL::integer)) AS format
               FROM pg_range r
              WHERE (r.rngtypid = t.oid))
            WHEN 'd'::"char" THEN (format_type(t.typbasetype, t.typtypmod) || COALESCE(( SELECT (' '::text || string_agg(pg_get_constraintdef(c.oid), ' '::text ORDER BY c.conname))
               FROM pg_constraint c
              WHERE (c.contypid = t.oid)), ''::text))
            ELSE NULL::text
        END AS definition
   FROM (pg_type t
     JOIN pg_namespace n ON ((n.oid = t.typnamespace)))
  WHERE ((t.typtype = ANY (ARRAY['e'::"char", 'r'::"char", 'd'::"char"])) AND (n.nspname <> ALL (ARRAY['pgrst'::name, 'pg_catalog'::name, 'auth'::name, 'neon_auth'::name, 'information_schema'::name])))
  ORDER BY (n.nspname = 'public'::name) DESC, n.nspname, t.typname;


--
-- Name: __direct_dependents; Type: VIEW; Schema: _debugging; Owner: -
--

CREATE VIEW _debugging.__direct_dependents AS
 WITH deps AS (
         SELECT DISTINCT ref_ns.nspname AS schema_nsp,
            ref.relname AS referenced_name,
            ref.relkind AS referenced_kind,
            dep.relname AS dependent_name,
            dep.relkind AS dependent_kind
           FROM (((((pg_depend d
             JOIN pg_rewrite rw ON ((d.objid = rw.oid)))
             JOIN pg_class dep ON ((rw.ev_class = dep.oid)))
             JOIN pg_class ref ON ((d.refobjid = ref.oid)))
             JOIN pg_namespace dep_ns ON ((dep_ns.oid = dep.relnamespace)))
             JOIN pg_namespace ref_ns ON ((ref_ns.oid = ref.relnamespace)))
          WHERE ((d.deptype = 'n'::"char") AND (dep.relkind = ANY (ARRAY['v'::"char", 'm'::"char"])) AND (ref.relkind = ANY (ARRAY['r'::"char", 'v'::"char", 'm'::"char", 'p'::"char", 'f'::"char"])) AND (ref_ns.nspname <> ALL (ARRAY['pgrst'::name, 'pg_catalog'::name, 'auth'::name, 'neon_auth'::name, 'information_schema'::name])))
        )
 SELECT schema_nsp,
    referenced_name,
    referenced_kind,
    array_agg(format('%s (%s)'::text, dependent_name, dependent_kind) ORDER BY dependent_kind, dependent_name) AS direct_dependents
   FROM deps
  GROUP BY schema_nsp, referenced_name, referenced_kind
  ORDER BY (schema_nsp = 'public'::name) DESC, schema_nsp, referenced_name;


--
-- Name: __direct_references; Type: VIEW; Schema: _debugging; Owner: -
--

CREATE VIEW _debugging.__direct_references AS
 WITH refs AS (
         SELECT DISTINCT ON (v.relname, ref.relname) ref_ns.nspname AS schema_nsp,
            v.relname AS view_name,
            ref.relname AS referenced_name,
            ref.relkind AS referenced_kind
           FROM (((((pg_rewrite rw
             JOIN pg_depend d ON (((d.objid = rw.oid) AND (d.deptype = 'n'::"char"))))
             JOIN pg_class v ON ((v.oid = rw.ev_class)))
             JOIN pg_namespace vns ON ((vns.oid = v.relnamespace)))
             JOIN pg_class ref ON ((ref.oid = d.refobjid)))
             JOIN pg_namespace ref_ns ON ((ref_ns.oid = ref.relnamespace)))
          WHERE (vns.nspname <> ALL (ARRAY['pgrst'::name, 'pg_catalog'::name, 'auth'::name, 'neon_auth'::name, 'information_schema'::name]))
        )
 SELECT schema_nsp,
    view_name,
    array_agg(format('%s (%s)'::text, referenced_name, referenced_kind) ORDER BY referenced_kind DESC, referenced_name) AS direct_references
   FROM refs
  GROUP BY schema_nsp, view_name
  ORDER BY (schema_nsp = 'public'::name) DESC, schema_nsp, view_name;


--
-- Name: __extensions_used; Type: VIEW; Schema: _debugging; Owner: -
--

CREATE VIEW _debugging.__extensions_used AS
 SELECT n.nspname AS schema_nsp,
    e.extname AS extension_name,
    e.extversion AS extension_version
   FROM (pg_extension e
     JOIN pg_namespace n ON ((n.oid = e.extnamespace)))
  WHERE (n.nspname <> ALL (ARRAY['pgrst'::name, 'pg_catalog'::name, 'auth'::name, 'neon_auth'::name, 'information_schema'::name]))
  ORDER BY (n.nspname = 'public'::name) DESC, n.nspname, e.extname;


--
-- Name: __functions_used; Type: VIEW; Schema: _debugging; Owner: -
--

CREATE VIEW _debugging.__functions_used AS
 SELECT n.nspname AS schema_nsp,
    p.proname AS user_function,
        CASE p.prokind
            WHEN 'f'::"char" THEN 'function'::text
            WHEN 'p'::"char" THEN 'procedure'::text
            WHEN 'a'::"char" THEN 'aggregate'::text
            WHEN 'w'::"char" THEN 'window'::text
            ELSE NULL::text
        END AS kind,
    pg_get_function_arguments(p.oid) AS args,
    pg_get_function_result(p.oid) AS result_type,
    pg_get_functiondef((((((n.nspname)::text || '.'::text) || (p.proname)::text))::regproc)::oid) AS definition
   FROM (pg_proc p
     JOIN pg_namespace n ON ((n.oid = p.pronamespace)))
  WHERE ((n.nspname <> ALL (ARRAY['pgrst'::name, 'pg_catalog'::name, 'auth'::name, 'neon_auth'::name, 'information_schema'::name])) AND (NOT (EXISTS ( SELECT 1
           FROM pg_depend d
          WHERE ((d.classid = ('pg_proc'::regclass)::oid) AND (d.objid = p.oid) AND (d.deptype = 'e'::"char"))))))
  ORDER BY (n.nspname = 'public'::name) DESC, n.nspname, p.proname, (pg_get_function_arguments(p.oid));


--
-- Name: __indexes_used; Type: VIEW; Schema: _debugging; Owner: -
--

CREATE VIEW _debugging.__indexes_used AS
 SELECT table_ns.nspname AS schema_nsp,
    table_cls.relname AS table_named,
    index_cls.relname AS index_named,
    con.conname AS constraint_named,
    con.contype AS constraint_type,
    idx.indisprimary AS is_primary,
    idx.indisunique AS is_unique,
    (idx.indpred IS NOT NULL) AS is_partial,
    pg_get_indexdef(idx.indexrelid) AS definition
   FROM ((((pg_index idx
     JOIN pg_class table_cls ON ((table_cls.oid = idx.indrelid)))
     JOIN pg_namespace table_ns ON ((table_ns.oid = table_cls.relnamespace)))
     JOIN pg_class index_cls ON ((index_cls.oid = idx.indexrelid)))
     LEFT JOIN pg_constraint con ON (((con.conrelid = table_cls.oid) AND (con.conindid = idx.indexrelid) AND (con.contype = ANY (ARRAY['p'::"char", 'u'::"char", 'x'::"char"])))))
  WHERE (table_ns.nspname <> ALL (ARRAY['pgrst'::text, 'pg_catalog'::text, 'pg_toast'::text, 'auth'::text, 'neon_auth'::text, 'information_schema'::text, '_debugging'::text]))
  ORDER BY (table_ns.nspname = 'public'::name) DESC, table_ns.nspname, table_cls.relname, index_cls.relname;


--
-- Name: __triggers_used; Type: VIEW; Schema: _debugging; Owner: -
--

CREATE VIEW _debugging.__triggers_used AS
 SELECT table_ns.nspname AS schema_nsp,
    table_cls.relname AS table_named,
    trg.tgname AS trigger_named,
    function_ns.nspname AS function_schema_nsp,
    fn.proname AS function_named,
    trg.tgenabled AS enabled_setting,
    pg_get_triggerdef(trg.oid, true) AS trigger_definition,
    pg_get_functiondef(fn.oid) AS function_definition
   FROM ((((pg_trigger trg
     JOIN pg_class table_cls ON ((table_cls.oid = trg.tgrelid)))
     JOIN pg_namespace table_ns ON ((table_ns.oid = table_cls.relnamespace)))
     JOIN pg_proc fn ON ((fn.oid = trg.tgfoid)))
     JOIN pg_namespace function_ns ON ((function_ns.oid = fn.pronamespace)))
  WHERE ((NOT trg.tgisinternal) AND (table_ns.nspname <> ALL (ARRAY['pgrst'::text, 'pg_catalog'::text, 'auth'::text, 'neon_auth'::text, 'information_schema'::text, '_debugging'::text])) AND (table_ns.nspname !~~ 'pg_toast%'::text))
  ORDER BY (table_ns.nspname = 'public'::name) DESC, table_ns.nspname, table_cls.relname, trg.tgname;


--
-- Name: __view_definitions; Type: VIEW; Schema: _debugging; Owner: -
--

CREATE VIEW _debugging.__view_definitions AS
 SELECT table_schema AS schema_nsp,
    table_name,
    pg_get_viewdef((((((table_schema)::text || '.'::text) || (table_name)::text))::regclass)::oid, true) AS definition
   FROM information_schema.views
  WHERE ((table_schema)::name <> ALL (ARRAY['pgrst'::name, 'pg_catalog'::name, 'auth'::name, 'neon_auth'::name, 'information_schema'::name]))
  ORDER BY ((table_schema)::name = 'public'::name) DESC, table_schema, table_name;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: adobe_labels; Type: TABLE; Schema: config; Owner: -
--

CREATE TABLE config.adobe_labels (
    label_id integer NOT NULL,
    label_name text NOT NULL,
    color_name text
);


--
-- Name: adobe_labels_label_id_seq; Type: SEQUENCE; Schema: config; Owner: -
--

ALTER TABLE config.adobe_labels ALTER COLUMN label_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME config.adobe_labels_label_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: color_palette; Type: TABLE; Schema: config; Owner: -
--

CREATE TABLE config.color_palette (
    color_hex public.hexcolor NOT NULL,
    color_name text NOT NULL
);


--
-- Name: compilations; Type: TABLE; Schema: config; Owner: -
--

CREATE TABLE config.compilations (
    compilation_id integer NOT NULL,
    review_id uuid NOT NULL,
    file_name public.citext NOT NULL,
    timeline_name public.citext NOT NULL,
    banned_bins text[]
);


--
-- Name: compilations_2_compilation_id_seq; Type: SEQUENCE; Schema: config; Owner: -
--

ALTER TABLE config.compilations ALTER COLUMN compilation_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME config.compilations_2_compilation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: images; Type: TABLE; Schema: config; Owner: -
--

CREATE TABLE config.images (
    public_id uuid NOT NULL,
    version_number integer NOT NULL,
    upload_time timestamp without time zone NOT NULL,
    update_time timestamp without time zone,
    display_name text
);


--
-- Name: media; Type: TABLE; Schema: config; Owner: -
--

CREATE TABLE config.media (
    medium_id integer NOT NULL,
    media_type project.media_type NOT NULL,
    supfolder_name public.citext NOT NULL,
    max_resolution project.resolution
);


--
-- Name: media_medium_id_seq; Type: SEQUENCE; Schema: config; Owner: -
--

ALTER TABLE config.media ALTER COLUMN medium_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME config.media_medium_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: member_labels; Type: TABLE; Schema: config; Owner: -
--

CREATE TABLE config.member_labels (
    submitter_id integer NOT NULL,
    person_id uuid,
    animal_id uuid,
    source_id uuid,
    label_id integer,
    member_id uuid GENERATED ALWAYS AS (COALESCE(person_id, animal_id, source_id)) STORED,
    CONSTRAINT member_id_check CHECK ((num_nonnulls(person_id, animal_id, source_id) = 1))
);


--
-- Name: member_labels_submitter_id_seq; Type: SEQUENCE; Schema: config; Owner: -
--

ALTER TABLE config.member_labels ALTER COLUMN submitter_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME config.member_labels_submitter_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: appearances; Type: TABLE; Schema: publishing; Owner: -
--

CREATE TABLE publishing.appearances (
    review_id uuid NOT NULL,
    member_id uuid NOT NULL,
    start_time double precision NOT NULL,
    end_time double precision NOT NULL
);


--
-- Name: appearance_spans; Type: VIEW; Schema: dashboard; Owner: -
--

CREATE VIEW dashboard.appearance_spans AS
 WITH ordered AS (
         SELECT appearances.review_id,
            appearances.member_id,
            appearances.start_time,
            appearances.end_time,
            max(appearances.end_time) OVER (PARTITION BY appearances.review_id, appearances.member_id ORDER BY appearances.start_time, appearances.end_time ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_max_end
           FROM publishing.appearances
        ), marked AS (
         SELECT ordered.review_id,
            ordered.member_id,
            ordered.start_time,
            ordered.end_time,
            ordered.running_max_end,
                CASE
                    WHEN (ordered.start_time <= lag(ordered.running_max_end) OVER (PARTITION BY ordered.review_id, ordered.member_id ORDER BY ordered.start_time, ordered.end_time)) THEN 0
                    ELSE 1
                END AS island_start
           FROM ordered
        ), islands AS (
         SELECT marked.review_id,
            marked.member_id,
            marked.start_time,
            marked.end_time,
            sum(marked.island_start) OVER (PARTITION BY marked.review_id, marked.member_id ORDER BY marked.start_time, marked.end_time) AS island_id
           FROM marked
        )
 SELECT review_id,
    member_id,
    min(start_time) AS start_time,
    max(end_time) AS end_time,
    (max(end_time) - min(start_time)) AS span
   FROM islands
  GROUP BY review_id, member_id, island_id;


--
-- Name: sources; Type: TABLE; Schema: project; Owner: -
--

CREATE TABLE project.sources (
    source_id uuid DEFAULT gen_random_uuid() NOT NULL,
    source_name text NOT NULL
);


--
-- Name: animals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.animals (
    animal_id uuid DEFAULT gen_random_uuid() NOT NULL,
    first_name text NOT NULL,
    middle_names text,
    nick_name text,
    sex public.gender,
    species text,
    birth_date date,
    birth_date_precision public.date_precision DEFAULT 'day'::text,
    death_date date,
    death_date_precision public.date_precision DEFAULT 'day'::text,
    notes text
);


--
-- Name: persons; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.persons (
    person_id uuid DEFAULT gen_random_uuid() NOT NULL,
    first_name text,
    middle_names text,
    last_name text NOT NULL,
    suffix integer,
    nick_name text,
    sex public.gender,
    birth_date timestamp without time zone,
    birth_date_precision public.date_precision DEFAULT 'day'::text,
    death_date timestamp without time zone,
    death_date_precision public.date_precision DEFAULT 'day'::text,
    notes text,
    prefix text,
    uses_middle boolean,
    CONSTRAINT persons_prefix_check CHECK ((prefix = ANY (ARRAY['Dr'::text, 'Fr'::text])))
);


--
-- Name: pets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pets (
    pet_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    relation_type text DEFAULT 'adoptive'::text,
    gotcha_date timestamp without time zone,
    gotcha_date_precision public.date_precision DEFAULT 'day'::text,
    CONSTRAINT pets_relation_type_check CHECK ((relation_type = ANY (ARRAY['adoptive'::text, 'shared'::text])))
);


--
-- Name: union_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.union_members (
    person_id uuid NOT NULL,
    union_id uuid NOT NULL
);


--
-- Name: unions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.unions (
    union_id uuid DEFAULT gen_random_uuid() NOT NULL,
    union_date date,
    union_date_precision public.date_precision,
    union_type text,
    last_name_person_id uuid,
    last_name_hyphen boolean,
    last_name_custom text,
    CONSTRAINT unions_union_type_check CHECK ((union_type = ANY (ARRAY['marriage'::text, 'friends'::text, 'civil'::text])))
);


--
-- Name: display_names; Type: VIEW; Schema: dashboard; Owner: -
--

CREATE VIEW dashboard.display_names AS
 WITH unioned_names AS (
         SELECT p1.person_id,
            p1.first_name,
                CASE
                    WHEN (unions.last_name_person_id IS NULL) THEN p1.last_name
                    ELSE p2.last_name
                END AS unioned_name
           FROM (((public.unions
             JOIN public.union_members USING (union_id))
             JOIN public.persons p1 USING (person_id))
             JOIN public.persons p2 ON ((p2.person_id = unions.last_name_person_id)))
        )
 SELECT persons.person_id AS member_id,
    (((((COALESCE((persons.prefix || ' '::text), ''::text) ||
        CASE
            WHEN (persons.first_name IS NULL) THEN (('< baby '::text ||
            CASE
                WHEN ((persons.sex)::text = 'm'::text) THEN 'boy '::text
                WHEN ((persons.sex)::text = 'f'::text) THEN 'girl '::text
                ELSE ''::text
            END) || ' >'::text)
            ELSE COALESCE(persons.nick_name, persons.first_name)
        END) || ' '::text) ||
        CASE
            WHEN persons.uses_middle THEN (split_part(persons.middle_names, ';'::text, 1) || ' '::text)
            ELSE ''::text
        END) || COALESCE(unioned_names.unioned_name, persons.last_name)) || public.suffix_to_text(persons.suffix)) AS full_name
   FROM (public.persons
     LEFT JOIN unioned_names ON ((persons.person_id = unioned_names.person_id)))
UNION
 SELECT animals.animal_id AS member_id,
    ((COALESCE(animals.nick_name, animals.first_name) || ' the '::text) || animals.species) AS full_name
   FROM ((public.animals
     JOIN public.pets ON ((animals.animal_id = pets.pet_id)))
     JOIN public.persons ON ((pets.owner_id = persons.person_id)))
UNION
 SELECT sources.source_id AS member_id,
    sources.source_name AS full_name
   FROM project.sources;


--
-- Name: files; Type: TABLE; Schema: project; Owner: -
--

CREATE TABLE project.files (
    file_id uuid DEFAULT gen_random_uuid() NOT NULL,
    file_name public.citext NOT NULL,
    folder_id uuid,
    file_size numeric,
    video_duration integer,
    video_rating integer,
    video_resolution project.resolution,
    used_status boolean,
    subfolder_name public.citext,
    video_date timestamp with time zone,
    file_extension text GENERATED ALWAYS AS (lower(public.regexp_replace(file_name, '.*\.'::public.citext, ''::text))) STORED,
    base_name text GENERATED ALWAYS AS (lower(regexp_replace(regexp_replace(public.regexp_replace(file_name, '\.[^.]+$'::public.citext, ''::text), '^(copy of\s+)+'::text, ''::text, 'i'::text), '( copy|_copy|\s+\(\d+\)|\s+\d+)$'::text, ''::text, 'i'::text))) STORED,
    CONSTRAINT files_video_rating_check CHECK (((video_rating >= 0) AND (video_rating <= 5)))
);


--
-- Name: folders; Type: TABLE; Schema: project; Owner: -
--

CREATE TABLE project.folders (
    folder_id uuid DEFAULT gen_random_uuid() NOT NULL,
    folder_name public.citext,
    project_year integer NOT NULL,
    person_id uuid,
    animal_id uuid,
    source_id uuid,
    member_id uuid GENERATED ALWAYS AS (COALESCE(person_id, animal_id, source_id)) STORED,
    media_type project.media_type NOT NULL,
    CONSTRAINT check_one_null CHECK ((num_nonnulls(person_id, animal_id, source_id) <= 1))
);


--
-- Name: folders_summary; Type: VIEW; Schema: dashboard; Owner: -
--

CREATE VIEW dashboard.folders_summary AS
 WITH file_summary AS (
         SELECT files.folder_id,
            count(files.file_id) AS video_count,
            sum(files.video_duration) AS video_duration,
            sum(files.file_size) AS file_size,
            sum(
                CASE
                    WHEN (files.video_rating IS NOT NULL) THEN 1
                    ELSE NULL::integer
                END) AS review_count,
            sum(
                CASE
                    WHEN (files.video_rating >= 3) THEN 1
                    ELSE NULL::integer
                END) AS usable_count,
            sum(
                CASE
                    WHEN files.used_status THEN 1
                    ELSE NULL::integer
                END) AS used_count
           FROM project.files
          GROUP BY files.folder_id
        ), rating_summary AS (
         SELECT unnamed_subquery.folder_id,
            jsonb_object_agg(unnamed_subquery.video_rating, unnamed_subquery.cnt) AS rating_count
           FROM ( SELECT files.folder_id,
                    COALESCE(files.video_rating, 0) AS video_rating,
                    count(*) AS cnt
                   FROM project.files
                  GROUP BY files.folder_id, COALESCE(files.video_rating, 0)) unnamed_subquery
          GROUP BY unnamed_subquery.folder_id
        ), resolution_summary AS (
         SELECT t.folder_id,
            jsonb_object_agg(t.video_resolution, t.cnt) AS resolution_count
           FROM ( SELECT files.folder_id,
                    files.video_resolution,
                    count(*) AS cnt
                   FROM project.files
                  GROUP BY files.folder_id, files.video_resolution) t
          WHERE (t.video_resolution IS NOT NULL)
          GROUP BY t.folder_id
        )
 SELECT folders.folder_id,
    folders.folder_name,
    folders.project_year,
    folders.media_type,
    media.supfolder_name,
    display_names.full_name,
    folders.member_id,
    file_summary.video_count,
    file_summary.video_duration,
    file_summary.file_size,
    rating_summary.rating_count,
    resolution_summary.resolution_count
   FROM (((((project.folders
     LEFT JOIN file_summary USING (folder_id))
     LEFT JOIN resolution_summary USING (folder_id))
     LEFT JOIN rating_summary USING (folder_id))
     JOIN config.media USING (media_type))
     LEFT JOIN dashboard.display_names USING (member_id));


--
-- Name: founder; Type: TABLE; Schema: nello; Owner: -
--

CREATE TABLE nello.founder (
    founder_id uuid NOT NULL,
    is_singleton boolean DEFAULT true NOT NULL,
    CONSTRAINT founder_single_row CHECK (is_singleton)
);


--
-- Name: founder; Type: VIEW; Schema: dashboard; Owner: -
--

CREATE VIEW dashboard.founder AS
 SELECT founder_id
   FROM nello.founder;


--
-- Name: parents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.parents (
    child_id uuid NOT NULL,
    parent_id uuid NOT NULL,
    relation_type text DEFAULT 'biological'::text,
    CONSTRAINT parents_relation_type_check CHECK ((relation_type = ANY (ARRAY['biological'::text, 'adoptive'::text, 'step'::text])))
);


--
-- Name: partners; Type: VIEW; Schema: tree; Owner: -
--

CREATE VIEW tree.partners AS
SELECT
    NULL::uuid AS person_id,
    NULL::uuid AS spouse_id,
    NULL::uuid AS union_id,
    NULL::text AS union_type;


--
-- Name: clans; Type: VIEW; Schema: tree; Owner: -
--

CREATE VIEW tree.clans AS
 WITH partnered_name_ids AS (
         SELECT unions.last_name_person_id,
            union_members_1.person_id,
            unions.union_id
           FROM (public.unions
             JOIN public.union_members union_members_1 USING (union_id))
          WHERE ((unions.last_name_person_id <> union_members_1.person_id) AND (unions.last_name_person_id IS NOT NULL) AND (unions.union_type = ANY (ARRAY['marriage'::text, 'civil'::text])))
        ), partnered_names AS (
         SELECT partnered_name_ids.union_id,
            ((((((p1.last_name || '-'::text) || p2.last_name) || ','::text) || p1.first_name) || '/'::text) || p2.first_name) AS clan_name,
            p1.person_id,
            p2.person_id AS spouse_id
           FROM ((partnered_name_ids
             JOIN public.persons p1 ON ((partnered_name_ids.last_name_person_id = p1.person_id)))
             JOIN public.persons p2 ON ((partnered_name_ids.person_id = p2.person_id)))
        ), leaders AS (
         SELECT parents.parent_id AS person_id
           FROM public.parents
        UNION
         SELECT partners.person_id
           FROM tree.partners
        UNION
         SELECT persons.person_id
           FROM public.persons
          WHERE ((NOT (EXISTS ( SELECT 1
                   FROM public.parents
                  WHERE ((persons.person_id = parents.parent_id) OR (persons.person_id = parents.child_id))))) AND (NOT (EXISTS ( SELECT 1
                   FROM public.union_members union_members_1
                  WHERE (persons.person_id = union_members_1.person_id)))))
        UNION
         SELECT persons.person_id
           FROM public.persons
          WHERE ((EXTRACT(year FROM age(((persons.birth_date)::date)::timestamp with time zone)) >= (30)::numeric) OR ((persons.birth_date_precision)::text = 'past'::text) OR (persons.birth_date_precision IS NULL))
        ), heads AS (
         SELECT p.person_id,
            p.first_name,
            p.last_name,
            p.suffix,
            partners.person_id AS spouse_id,
            unions.union_date AS wedding_date,
            p.birth_date
           FROM (((public.persons p
             JOIN leaders USING (person_id))
             LEFT JOIN tree.partners ON ((p.person_id = partners.person_id)))
             LEFT JOIN public.unions USING (union_id))
          WHERE (unions.union_type = ANY (ARRAY['marriage'::text, 'civil'::text]))
        ), couple_clans AS (
         SELECT partnered_names.person_id,
            partnered_names.spouse_id,
            partnered_names.clan_name,
            unions.union_date AS clan_date,
            'partnered'::text AS clan_type
           FROM (partnered_names
             JOIN public.unions USING (union_id))
          WHERE (((unions.union_date <= CURRENT_DATE) OR ((unions.union_date_precision)::text = 'past'::text)) AND (unions.union_type = ANY (ARRAY['marriage'::text, 'civil'::text])))
        ), solo_clans AS (
         SELECT h.person_id,
            NULL::uuid AS spouse_id,
            (((h.last_name || ', '::text) || h.first_name) || public.suffix_to_text(h.suffix)) AS clan_name,
            (h.birth_date + '30 years'::interval) AS clan_date,
            'solo'::text AS clan_type
           FROM heads h
          WHERE (h.spouse_id IS NULL)
        ), clan_values AS (
         SELECT couple_clans.person_id AS head_id_1,
            couple_clans.spouse_id AS head_id_2,
            couple_clans.clan_name,
            couple_clans.clan_date,
            couple_clans.clan_type
           FROM couple_clans
        UNION ALL
         SELECT solo_clans.person_id,
            solo_clans.spouse_id,
            solo_clans.clan_name,
            (solo_clans.clan_date)::date AS clan_date,
            solo_clans.clan_type
           FROM solo_clans
        )
 SELECT clan_values.head_id_1,
    clan_values.head_id_2,
    clan_values.clan_name,
    clan_values.clan_date,
    clan_values.clan_type,
    COALESCE(union_members.union_id, clan_values.head_id_1, clan_values.head_id_2) AS clan_id,
    num_nonnulls(clan_values.head_id_1, clan_values.head_id_2) AS n_heads,
    union_members.union_id
   FROM (clan_values
     LEFT JOIN public.union_members ON ((clan_values.head_id_1 = union_members.person_id)));


--
-- Name: members; Type: VIEW; Schema: tree; Owner: -
--

CREATE VIEW tree.members AS
 WITH people AS (
         SELECT persons.person_id,
            persons.birth_date,
            persons.birth_date_precision,
            persons.death_date,
            persons.death_date_precision,
            unions.union_date,
            unions.union_date_precision
           FROM ((public.persons
             LEFT JOIN tree.partners USING (person_id))
             LEFT JOIN public.unions ON ((partners.union_id = unions.union_id)))
        ), furries AS (
         SELECT DISTINCT ON (animals.animal_id) animals.animal_id,
            animals.birth_date,
            animals.birth_date_precision,
            animals.death_date,
            animals.death_date_precision,
            pets.gotcha_date,
            pets.gotcha_date_precision
           FROM (public.animals
             JOIN public.pets ON ((animals.animal_id = pets.pet_id)))
        )
 SELECT people.person_id AS member_id,
    people.birth_date,
    people.birth_date_precision,
    people.death_date,
    people.death_date_precision,
    people.union_date AS entry_date,
    people.union_date_precision AS entry_date_precision,
    'person'::text AS member_type
   FROM people
UNION
 SELECT furries.animal_id AS member_id,
    furries.birth_date,
    furries.birth_date_precision,
    furries.death_date,
    furries.death_date_precision,
    furries.gotcha_date AS entry_date,
    furries.gotcha_date_precision AS entry_date_precision,
    'animal'::text AS member_type
   FROM furries;


--
-- Name: nodes; Type: VIEW; Schema: tree; Owner: -
--

CREATE VIEW tree.nodes AS
SELECT
    NULL::uuid AS member_id,
    NULL::uuid AS node_id;


--
-- Name: households; Type: VIEW; Schema: tree; Owner: -
--

CREATE VIEW tree.households AS
 WITH leaders AS (
         SELECT members.member_id,
            clans.clan_id
           FROM (tree.members
             JOIN tree.clans ON (((members.member_id = clans.head_id_1) OR (members.member_id = clans.head_id_2))))
        ), followers AS (
         SELECT members.member_id
           FROM tree.members
        EXCEPT
         SELECT leaders.member_id
           FROM leaders
        ), people AS (
         SELECT leaders.member_id,
            leaders.clan_id
           FROM leaders
        UNION
         SELECT followers.member_id,
            clans.clan_id
           FROM ((followers
             JOIN tree.nodes USING (member_id))
             JOIN tree.clans ON (((nodes.node_id = clans.union_id) OR (nodes.node_id = clans.head_id_1))))
        ), missed AS (
         SELECT members.member_id AS missed_id
           FROM tree.members
        EXCEPT
         SELECT people.member_id
           FROM people
        ), current_households AS (
         SELECT people.member_id,
            people.clan_id
           FROM people
        UNION
         SELECT missed.missed_id,
            people.clan_id
           FROM ((missed
             JOIN public.pets ON ((missed.missed_id = pets.pet_id)))
             JOIN people ON ((pets.owner_id = people.member_id)))
        ), grandparents AS (
         SELECT parents.child_id AS grandchild_id,
            parents.parent_id AS grandparent_id
           FROM public.parents
        UNION
         SELECT c.pet_id AS grandchild_id,
            p.parent_id AS grandparent_id
           FROM (public.pets c
             JOIN public.parents p ON ((c.owner_id = p.child_id)))
        ), grandclans AS (
         SELECT DISTINCT grandparents.grandchild_id,
            current_households.clan_id AS grandclan_id
           FROM (grandparents
             JOIN current_households ON ((grandparents.grandparent_id = current_households.member_id)))
        ), heads AS (
         SELECT clans.head_id_1 AS head_id
           FROM tree.clans
        UNION
         SELECT clans.head_id_2 AS head_id
           FROM tree.clans
        ), birth_clans AS (
         SELECT heads.head_id AS member_id,
            grandclans.grandclan_id
           FROM (heads
             JOIN grandclans ON ((grandclans.grandchild_id = heads.head_id)))
        ), nees AS (
         SELECT current_households.member_id,
            current_households.clan_id AS current_clan_id,
            birth_clans.grandclan_id AS nee_clan_id
           FROM (((current_households
             LEFT JOIN birth_clans USING (member_id))
             JOIN tree.clans USING (clan_id))
             JOIN dashboard.display_names display_names_1 USING (member_id))
        )
 SELECT nees.member_id,
    nees.current_clan_id,
    nees.nee_clan_id
   FROM (nees
     JOIN dashboard.display_names USING (member_id));


--
-- Name: member_information; Type: VIEW; Schema: dashboard; Owner: -
--

CREATE VIEW dashboard.member_information AS
 SELECT display_names.member_id,
    display_names.full_name,
    c1.clan_date,
    c1.clan_id AS clan_id_1,
    c1.clan_name AS clan_name_1,
    c2.clan_id AS clan_id_2,
    c2.clan_name AS clan_name_2,
    members.birth_date,
    members.birth_date_precision,
    members.death_date,
    members.death_date_precision,
    members.entry_date,
    members.entry_date_precision,
    members.member_type
   FROM ((((dashboard.display_names
     JOIN tree.members USING (member_id))
     LEFT JOIN tree.households USING (member_id))
     LEFT JOIN tree.clans c1 ON ((households.current_clan_id = c1.clan_id)))
     LEFT JOIN tree.clans c2 ON ((households.nee_clan_id = c2.clan_id)));


--
-- Name: member_summary; Type: VIEW; Schema: dashboard; Owner: -
--

CREATE VIEW dashboard.member_summary AS
 SELECT member_information.member_id,
    member_information.full_name,
    member_information.member_type,
    rank() OVER (ORDER BY COALESCE(p.first_name, a.first_name), p.last_name, p.suffix) AS sort_order
   FROM ((dashboard.member_information
     LEFT JOIN public.persons p ON ((member_information.member_id = p.person_id)))
     LEFT JOIN public.animals a ON ((member_information.member_id = a.animal_id)));


--
-- Name: partnerships; Type: VIEW; Schema: tree; Owner: -
--

CREATE VIEW tree.partnerships AS
 WITH spouses AS (
         SELECT union_members.union_id,
            array_agg(union_members.person_id ORDER BY
                CASE
                    WHEN (union_members.person_id = unions_1.last_name_person_id) THEN 0
                    ELSE 1
                END) AS partner_ids
           FROM (public.union_members
             JOIN public.unions unions_1 USING (union_id))
          WHERE (unions_1.union_type = ANY (ARRAY['marriage'::text, 'civil'::text]))
          GROUP BY union_members.union_id
        ), severances AS (
         SELECT union_members.union_id,
            min(persons.death_date) AS severance_date
           FROM (public.union_members
             JOIN public.persons USING (person_id))
          GROUP BY union_members.union_id
        )
 SELECT unions.union_id,
    spouses.partner_ids[1] AS partner_id_1,
    spouses.partner_ids[2] AS partner_id_2,
    unions.union_date,
    unions.union_date_precision,
    unions.union_type,
    severances.severance_date,
    COALESCE(unions.last_name_custom, p0.last_name,
        CASE
            WHEN unions.last_name_hyphen THEN ((p1.last_name || '-'::text) || p2.last_name)
            ELSE NULL::text
        END) AS married_name
   FROM (((((public.unions
     JOIN spouses USING (union_id))
     JOIN severances USING (union_id))
     LEFT JOIN public.persons p0 ON ((p0.person_id = unions.last_name_person_id)))
     JOIN public.persons p1 ON ((p1.person_id = spouses.partner_ids[1])))
     JOIN public.persons p2 ON ((p2.person_id = spouses.partner_ids[2])));


--
-- Name: relations_summary; Type: VIEW; Schema: dashboard; Owner: -
--

CREATE VIEW dashboard.relations_summary AS
 SELECT parents.child_id AS member_id_1,
    parents.parent_id AS member_id_2,
    parents.relation_type,
    persons.birth_date AS entry_date,
    persons.birth_date_precision AS entry_date_precision,
    'child'::text AS relation
   FROM (public.parents
     JOIN public.persons ON ((persons.person_id = parents.child_id)))
UNION
 SELECT pets.pet_id AS member_id_1,
    pets.owner_id AS member_id_2,
    pets.relation_type,
    COALESCE(pets.gotcha_date, (animals.birth_date)::timestamp without time zone) AS entry_date,
        CASE
            WHEN (pets.gotcha_date IS NOT NULL) THEN pets.gotcha_date_precision
            ELSE animals.birth_date_precision
        END AS entry_date_precision,
    'pet'::text AS relation
   FROM (public.pets
     JOIN public.animals ON ((animals.animal_id = pets.pet_id)))
UNION
 SELECT partnerships.partner_id_1 AS member_id_1,
    partnerships.partner_id_2 AS member_id_2,
    partnerships.union_type AS relation_type,
    partnerships.union_date AS entry_date,
    partnerships.union_date_precision AS entry_date_precision,
    'spouse'::text AS relation
   FROM tree.partnerships;


--
-- Name: resolution_order; Type: VIEW; Schema: dashboard; Owner: -
--

CREATE VIEW dashboard.resolution_order AS
 SELECT value AS resolution
   FROM unnest(enum_range(NULL::project.resolution)) "values"(value);


--
-- Name: years_summary; Type: VIEW; Schema: dashboard; Owner: -
--

CREATE VIEW dashboard.years_summary AS
 WITH summary_counts AS (
         SELECT folders.project_year,
            count(DISTINCT folders.folder_id) AS total_folders,
            count(files.file_id) AS total_videos,
            sum(files.file_size) AS total_file_size,
            sum(files.video_duration) AS total_duration
           FROM (project.folders
             JOIN project.files USING (folder_id))
          GROUP BY folders.project_year
          ORDER BY folders.project_year
        ), resolution_counts AS (
         SELECT folders.project_year,
            COALESCE(
                CASE
                    WHEN (num_nulls(media.max_resolution, files.video_resolution) = 0) THEN LEAST(files.video_resolution, media.max_resolution)
                    ELSE files.video_resolution
                END, 'na'::project.resolution) AS resolution_key,
            sum(files.video_duration) AS cnt
           FROM ((project.files
             JOIN project.folders USING (folder_id))
             JOIN config.media USING (media_type))
          WHERE (folders.source_id IS NULL)
          GROUP BY folders.project_year, COALESCE(
                CASE
                    WHEN (num_nulls(media.max_resolution, files.video_resolution) = 0) THEN LEAST(files.video_resolution, media.max_resolution)
                    ELSE files.video_resolution
                END, 'na'::project.resolution)
        ), status_counts AS (
         SELECT folders.project_year,
                CASE
                    WHEN files.used_status THEN 'used'::text
                    ELSE (COALESCE(files.video_rating, 0))::text
                END AS status_key,
            count(*) AS cnt
           FROM (project.files
             JOIN project.folders USING (folder_id))
          GROUP BY folders.project_year,
                CASE
                    WHEN files.used_status THEN 'used'::text
                    ELSE (COALESCE(files.video_rating, 0))::text
                END
        ), agg_counts AS (
         SELECT r.project_year,
            jsonb_object_agg(r.resolution_key, r.cnt ORDER BY r.resolution_key) AS video_resolutions,
            jsonb_object_agg(s.status_key, s.cnt ORDER BY s.status_key) AS video_status
           FROM (resolution_counts r
             JOIN status_counts s USING (project_year))
          GROUP BY r.project_year
        )
 SELECT summary_counts.project_year,
    summary_counts.total_folders,
    summary_counts.total_videos,
    summary_counts.total_file_size,
    summary_counts.total_duration,
    agg_counts.video_resolutions,
    agg_counts.video_status
   FROM (summary_counts
     JOIN agg_counts USING (project_year));


--
-- Name: browser_profiles; Type: TABLE; Schema: ingestion; Owner: -
--

CREATE TABLE ingestion.browser_profiles (
    profile_id integer NOT NULL,
    browser_id integer NOT NULL,
    profile_name text
);


--
-- Name: browser_profiles_profile_id_seq; Type: SEQUENCE; Schema: ingestion; Owner: -
--

ALTER TABLE ingestion.browser_profiles ALTER COLUMN profile_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME ingestion.browser_profiles_profile_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: browsers; Type: TABLE; Schema: ingestion; Owner: -
--

CREATE TABLE ingestion.browsers (
    browser_id integer NOT NULL,
    browser_name text NOT NULL
);


--
-- Name: browsers_browser_id_seq; Type: SEQUENCE; Schema: ingestion; Owner: -
--

ALTER TABLE ingestion.browsers ALTER COLUMN browser_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME ingestion.browsers_browser_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: repositories; Type: TABLE; Schema: ingestion; Owner: -
--

CREATE TABLE ingestion.repositories (
    repository_id integer NOT NULL,
    repository_name text NOT NULL
);


--
-- Name: repositories_repository_id_seq; Type: SEQUENCE; Schema: ingestion; Owner: -
--

ALTER TABLE ingestion.repositories ALTER COLUMN repository_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME ingestion.repositories_repository_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: scrape_sources; Type: TABLE; Schema: ingestion; Owner: -
--

CREATE TABLE ingestion.scrape_sources (
    scrape_id integer NOT NULL,
    scrape_name text NOT NULL,
    scrape_domain text NOT NULL
);


--
-- Name: scrape_sources_scrape_id_seq; Type: SEQUENCE; Schema: ingestion; Owner: -
--

ALTER TABLE ingestion.scrape_sources ALTER COLUMN scrape_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME ingestion.scrape_sources_scrape_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: shared_albums; Type: TABLE; Schema: ingestion; Owner: -
--

CREATE TABLE ingestion.shared_albums (
    album_id uuid DEFAULT gen_random_uuid() NOT NULL,
    share_url text NOT NULL,
    folder_id uuid NOT NULL,
    profile_id integer NOT NULL,
    notes text
);


--
-- Name: shared_album_details; Type: VIEW; Schema: ingestion; Owner: -
--

CREATE VIEW ingestion.shared_album_details AS
 SELECT shared_albums.album_id,
    shared_albums.share_url,
    folders.folder_name,
    folders.project_year,
    media.supfolder_name,
    scrape_sources.scrape_name,
    browsers.browser_name,
    browser_profiles.profile_name,
    shared_albums.notes
   FROM (((((ingestion.shared_albums
     JOIN ingestion.browser_profiles USING (profile_id))
     JOIN ingestion.browsers USING (browser_id))
     JOIN project.folders USING (folder_id))
     JOIN ingestion.scrape_sources ON ((shared_albums.share_url ~~* (('http%'::text || scrape_sources.scrape_domain) || '/%'::text))))
     JOIN config.media USING (media_type));


--
-- Name: address_moves; Type: TABLE; Schema: messaging; Owner: -
--

CREATE TABLE messaging.address_moves (
    move_id integer NOT NULL,
    person_id uuid NOT NULL,
    address_id integer NOT NULL,
    start_date date
);


--
-- Name: address_moves_move_id_seq; Type: SEQUENCE; Schema: messaging; Owner: -
--

ALTER TABLE messaging.address_moves ALTER COLUMN move_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME messaging.address_moves_move_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: addresses; Type: TABLE; Schema: messaging; Owner: -
--

CREATE TABLE messaging.addresses (
    address_id integer NOT NULL,
    address_name text,
    zip_code messaging.zip_code NOT NULL
);


--
-- Name: addresses_address_id_seq; Type: SEQUENCE; Schema: messaging; Owner: -
--

ALTER TABLE messaging.addresses ALTER COLUMN address_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME messaging.addresses_address_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: calendar_events; Type: TABLE; Schema: messaging; Owner: -
--

CREATE TABLE messaging.calendar_events (
    calendar_event_id uuid DEFAULT gen_random_uuid() NOT NULL,
    person_id uuid,
    union_id uuid,
    external_event_id text NOT NULL,
    last_verified_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT calendar_events_one_source CHECK ((num_nonnulls(person_id, union_id) = 1))
);


--
-- Name: contacts; Type: TABLE; Schema: messaging; Owner: -
--

CREATE TABLE messaging.contacts (
    person_id uuid NOT NULL,
    email_address text,
    phone_number messaging.phone_number
);


--
-- Name: events; Type: TABLE; Schema: messaging; Owner: -
--

CREATE TABLE messaging.events (
    event_id integer NOT NULL,
    event_name text NOT NULL,
    start_date date NOT NULL,
    end_date date,
    event_type text
);


--
-- Name: events_event_id_seq; Type: SEQUENCE; Schema: messaging; Owner: -
--

ALTER TABLE messaging.events ALTER COLUMN event_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME messaging.events_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: holidays; Type: TABLE; Schema: messaging; Owner: -
--

CREATE TABLE messaging.holidays (
    holiday_id integer NOT NULL,
    holiday_name text NOT NULL,
    start_date date NOT NULL,
    end_date date
);


--
-- Name: holidays_holiday_id_seq; Type: SEQUENCE; Schema: messaging; Owner: -
--

ALTER TABLE messaging.holidays ALTER COLUMN holiday_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME messaging.holidays_holiday_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: no_contacts; Type: TABLE; Schema: messaging; Owner: -
--

CREATE TABLE messaging.no_contacts (
    no_contact_id integer NOT NULL,
    person_id uuid,
    project_year integer NOT NULL
);


--
-- Name: no_contacts_no_contact_id_seq; Type: SEQUENCE; Schema: messaging; Owner: -
--

ALTER TABLE messaging.no_contacts ALTER COLUMN no_contact_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME messaging.no_contacts_no_contact_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: templates; Type: TABLE; Schema: messaging; Owner: -
--

CREATE TABLE messaging.templates (
    template_id integer NOT NULL,
    project_year integer NOT NULL
);


--
-- Name: templates_template_id_seq; Type: SEQUENCE; Schema: messaging; Owner: -
--

ALTER TABLE messaging.templates ALTER COLUMN template_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME messaging.templates_template_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: appearances; Type: TABLE; Schema: project; Owner: -
--

CREATE TABLE project.appearances (
    project_year integer,
    member_id uuid,
    start_time double precision,
    end_time double precision
);


--
-- Name: backfill; Type: TABLE; Schema: project; Owner: -
--

CREATE TABLE project.backfill (
    review_id uuid NOT NULL,
    member_id uuid NOT NULL
);


--
-- Name: chapters; Type: TABLE; Schema: project; Owner: -
--

CREATE TABLE project.chapters (
    project_year integer,
    chapter_name text,
    start_time double precision
);


--
-- Name: duplicates; Type: VIEW; Schema: project; Owner: -
--

CREATE VIEW project.duplicates AS
 WITH duplicate_same_date AS (
         SELECT files.folder_id,
            files.video_date,
            files.video_duration,
            jsonb_agg(files.file_id) AS potential_duplicates
           FROM project.files
          WHERE ((files.video_date IS NOT NULL) AND (files.video_date > '1985-04-25 00:00:00+00'::timestamp with time zone) AND (files.video_duration IS NOT NULL))
          GROUP BY files.folder_id, files.video_date, files.video_duration
         HAVING (count(files.file_id) > 1)
        ), duplicate_same_name AS (
         SELECT files.folder_id,
            (round((files.file_size * (5)::numeric)) / (5)::numeric) AS file_size,
            files.file_extension,
            files.base_name,
            jsonb_agg(files.file_id) AS potential_duplicates
           FROM project.files
          WHERE (files.file_size > (0)::numeric)
          GROUP BY files.folder_id, (round((files.file_size * (5)::numeric)) / (5)::numeric), files.file_extension, files.base_name
         HAVING (count(files.file_id) > 1)
        )
 SELECT duplicate_same_date.folder_id,
    'date+duration'::text AS duplicate_reason,
    duplicate_same_date.potential_duplicates,
    jsonb_build_object('date', duplicate_same_date.video_date, 'duration', duplicate_same_date.video_duration) AS duplicate_flags
   FROM duplicate_same_date
UNION
 SELECT duplicate_same_name.folder_id,
    'norm+size'::text AS duplicate_reason,
    duplicate_same_name.potential_duplicates,
    jsonb_build_object('norm', ((duplicate_same_name.base_name || '.'::text) || duplicate_same_name.file_extension), 'size', duplicate_same_name.file_size) AS duplicate_flags
   FROM duplicate_same_name
  ORDER BY 2;


--
-- Name: duplicates_summary; Type: VIEW; Schema: project; Owner: -
--

CREATE VIEW project.duplicates_summary AS
 WITH grouped_dupes AS (
         SELECT row_number() OVER () AS dupe_num,
            duplicates.folder_id,
            array_agg(DISTINCT duplicates.duplicate_reason) AS flags,
            jsonb_agg(DISTINCT elem.value ORDER BY elem.value) AS potential_duplicates_sorted
           FROM project.duplicates,
            LATERAL jsonb_array_elements(duplicates.potential_duplicates) elem(value)
          GROUP BY duplicates.folder_id, ( SELECT jsonb_agg(ordered_elem.value ORDER BY ordered_elem.value) AS jsonb_agg
                   FROM jsonb_array_elements(duplicates.potential_duplicates) ordered_elem(value))
        ), expanded AS (
         SELECT grouped_dupes_1.dupe_num,
            (elements.value)::uuid AS file_id
           FROM (grouped_dupes grouped_dupes_1
             CROSS JOIN LATERAL jsonb_array_elements_text(grouped_dupes_1.potential_duplicates_sorted) elements(value))
        ), filled AS (
         SELECT expanded.dupe_num,
            expanded.file_id,
            folders_1.project_year,
            files.subfolder_name,
            folders_1.folder_name,
            files.file_name,
            files.file_size,
            files.video_duration,
            files.video_resolution,
            (length((files.file_name)::text) - length(files.file_extension)) AS len_name,
                CASE
                    WHEN (files.subfolder_name IS NULL) THEN 0
                    ELSE ((length((files.subfolder_name)::text) - length(public.replace(files.subfolder_name, '/'::public.citext, ''::public.citext))) + 1)
                END AS folder_depth
           FROM ((expanded
             JOIN project.files USING (file_id))
             JOIN project.folders folders_1 USING (folder_id))
        ), compressed AS (
         SELECT filled.dupe_num,
            jsonb_agg(jsonb_build_object('file_id', filled.file_id, 'project_year', filled.project_year, 'folder_name', filled.folder_name, 'subfolder_name', filled.subfolder_name, 'file_name', filled.file_name, 'file_size', filled.file_size, 'video_resolution', filled.video_resolution, 'video_duration', filled.video_duration) ORDER BY filled.video_resolution DESC NULLS LAST, filled.video_duration DESC NULLS LAST, filled.file_size DESC, filled.folder_depth, filled.len_name, filled.file_name) AS duplicates_sorted
           FROM filled
          GROUP BY filled.dupe_num
        )
 SELECT folders.project_year,
    folders.folder_name,
    folders.media_type,
    grouped_dupes.flags,
    compressed.duplicates_sorted
   FROM (((grouped_dupes
     JOIN compressed USING (dupe_num))
     JOIN project.folders USING (folder_id))
     JOIN config.media USING (media_type));


--
-- Name: folder_locations; Type: TABLE; Schema: project; Owner: -
--

CREATE TABLE project.folder_locations (
    folder_location_id uuid NOT NULL,
    folder_id uuid NOT NULL,
    repository_id integer NOT NULL,
    repository_item_id text NOT NULL,
    is_canonical boolean DEFAULT false NOT NULL
);


--
-- Name: shares; Type: TABLE; Schema: project; Owner: -
--

CREATE TABLE project.shares (
    share_id integer NOT NULL,
    folder_location_id uuid NOT NULL,
    share_url text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    expires_at timestamp without time zone,
    last_verified_at timestamp without time zone
);


--
-- Name: shares_share_id_seq; Type: SEQUENCE; Schema: project; Owner: -
--

ALTER TABLE project.shares ALTER COLUMN share_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME project.shares_share_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: chapters; Type: TABLE; Schema: publishing; Owner: -
--

CREATE TABLE publishing.chapters (
    review_id uuid NOT NULL,
    chapter_name text NOT NULL,
    start_time double precision NOT NULL
);


--
-- Name: music; Type: TABLE; Schema: publishing; Owner: -
--

CREATE TABLE publishing.music (
    track_id uuid DEFAULT gen_random_uuid() NOT NULL,
    track_title text,
    artist_name text,
    track_duration integer,
    track_url text,
    review_id uuid NOT NULL,
    main_track boolean,
    lyrics_url text
);


--
-- Name: reviews; Type: TABLE; Schema: publishing; Owner: -
--

CREATE TABLE publishing.reviews (
    review_id uuid DEFAULT gen_random_uuid() NOT NULL,
    review_type text,
    project_year integer NOT NULL,
    video_theme text,
    video_duration integer,
    video_resolution project.resolution,
    cloud_url text,
    public_date date,
    CONSTRAINT reviews_review_type_check CHECK ((review_type = ANY (ARRAY['year'::text, 'decade'::text, 'era'::text])))
);


--
-- Name: apexes; Type: VIEW; Schema: tree; Owner: -
--

CREATE VIEW tree.apexes AS
SELECT
    NULL::uuid AS node_id,
    NULL::uuid AS member_id;


--
-- Name: friends; Type: VIEW; Schema: tree; Owner: -
--

CREATE VIEW tree.friends AS
SELECT
    NULL::uuid AS person_id,
    NULL::uuid AS spouse_id,
    NULL::uuid AS union_id,
    NULL::text AS union_type;


--
-- Name: friendships; Type: VIEW; Schema: tree; Owner: -
--

CREATE VIEW tree.friendships AS
 WITH spouses AS (
         SELECT union_members.union_id,
            array_agg(union_members.person_id ORDER BY
                CASE
                    WHEN (union_members.person_id = unions_1.last_name_person_id) THEN 0
                    ELSE 1
                END) AS partner_ids
           FROM (public.union_members
             JOIN public.unions unions_1 USING (union_id))
          WHERE (unions_1.union_type = 'friends'::text)
          GROUP BY union_members.union_id
        )
 SELECT unions.union_id,
    spouses.partner_ids[1] AS partner_id_1,
    spouses.partner_ids[2] AS partner_id_2,
    unions.union_date,
    unions.union_date_precision,
    unions.union_type
   FROM (public.unions
     JOIN spouses USING (union_id));


--
-- Name: heads; Type: VIEW; Schema: tree; Owner: -
--

CREATE VIEW tree.heads AS
 WITH full_unions AS (
         SELECT u1.union_id,
            u1.person_id AS head_id_1,
            u2.person_id AS head_id_2
           FROM (public.union_members u1
             JOIN public.union_members u2 ON (((u1.union_id = u2.union_id) AND (u1.person_id <> u2.person_id))))
        ), node_ids AS (
         SELECT DISTINCT nodes.node_id
           FROM tree.nodes
        ), node_heads AS (
         SELECT node_ids.node_id,
            persons.person_id AS head_id_0,
            NULL::uuid AS head_id_1,
            NULL::uuid AS head_id_2
           FROM (node_ids
             JOIN public.persons ON ((node_ids.node_id = persons.person_id)))
        UNION
         SELECT node_ids.node_id,
            NULL::uuid AS head_id_0,
            full_unions.head_id_1,
            full_unions.head_id_2
           FROM (node_ids
             JOIN full_unions ON ((node_ids.node_id = full_unions.union_id)))
        )
 SELECT node_heads.node_id,
    node_heads.head_id_0 AS head_id
   FROM node_heads
  WHERE (node_heads.head_id_0 IS NOT NULL)
UNION
 SELECT node_heads.node_id,
    node_heads.head_id_1 AS head_id
   FROM node_heads
  WHERE (node_heads.head_id_1 IS NOT NULL)
UNION
 SELECT node_heads.node_id,
    node_heads.head_id_2 AS head_id
   FROM node_heads
  WHERE (node_heads.head_id_2 IS NOT NULL);


--
-- Name: memberships; Type: VIEW; Schema: tree; Owner: -
--

CREATE VIEW tree.memberships AS
 WITH people AS (
         SELECT persons.person_id,
            persons.birth_date,
            persons.birth_date_precision,
            persons.death_date,
            persons.death_date_precision,
            unions.union_date,
            unions.union_date_precision
           FROM ((public.persons
             LEFT JOIN tree.partners USING (person_id))
             LEFT JOIN public.unions ON ((partners.union_id = unions.union_id)))
        ), furries AS (
         SELECT DISTINCT ON (animals.animal_id) animals.animal_id,
            animals.birth_date,
            animals.birth_date_precision,
            animals.death_date,
            animals.death_date_precision,
            pets.gotcha_date,
            pets.gotcha_date_precision
           FROM (public.animals
             JOIN public.pets ON ((animals.animal_id = pets.pet_id)))
        )
 SELECT people.person_id AS member_id,
    people.birth_date,
    people.birth_date_precision,
    people.death_date,
    people.death_date_precision,
    people.union_date AS entry_date,
    people.union_date_precision AS entry_date_precision,
    'person'::text AS member_type
   FROM people
UNION
 SELECT furries.animal_id AS member_id,
    furries.birth_date,
    furries.birth_date_precision,
    furries.death_date,
    furries.death_date_precision,
    furries.gotcha_date AS entry_date,
    furries.gotcha_date_precision AS entry_date_precision,
    'animal'::text AS member_type
   FROM furries;


--
-- Name: identities; Type: TABLE; Schema: users; Owner: -
--

CREATE TABLE users.identities (
    user_id integer NOT NULL,
    issuer_name text NOT NULL,
    subject_id text NOT NULL,
    user_email text NOT NULL,
    display_name text NOT NULL,
    first_login timestamp without time zone NOT NULL,
    last_login timestamp without time zone NOT NULL,
    person_id uuid
);


--
-- Name: identities_user_id_seq; Type: SEQUENCE; Schema: users; Owner: -
--

ALTER TABLE users.identities ALTER COLUMN user_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME users.identities_user_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: identity_roles; Type: TABLE; Schema: users; Owner: -
--

CREATE TABLE users.identity_roles (
    user_id integer NOT NULL,
    role_id integer NOT NULL
);


--
-- Name: issuers; Type: TABLE; Schema: users; Owner: -
--

CREATE TABLE users.issuers (
    issuer_id integer NOT NULL,
    issuer_name text NOT NULL
);


--
-- Name: issuers_issuer_id_seq; Type: SEQUENCE; Schema: users; Owner: -
--

ALTER TABLE users.issuers ALTER COLUMN issuer_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME users.issuers_issuer_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: pre_approvals; Type: TABLE; Schema: users; Owner: -
--

CREATE TABLE users.pre_approvals (
    email_address public.citext NOT NULL,
    role_id integer NOT NULL
);


--
-- Name: roles; Type: TABLE; Schema: users; Owner: -
--

CREATE TABLE users.roles (
    role_id integer NOT NULL,
    role_name text NOT NULL
);


--
-- Name: roles_role_id_seq; Type: SEQUENCE; Schema: users; Owner: -
--

ALTER TABLE users.roles ALTER COLUMN role_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME users.roles_role_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: adobe_labels adobe_labels_pkey; Type: CONSTRAINT; Schema: config; Owner: -
--

ALTER TABLE ONLY config.adobe_labels
    ADD CONSTRAINT adobe_labels_pkey PRIMARY KEY (label_id);


--
-- Name: color_palette color_name_unique; Type: CONSTRAINT; Schema: config; Owner: -
--

ALTER TABLE ONLY config.color_palette
    ADD CONSTRAINT color_name_unique UNIQUE (color_name);


--
-- Name: color_palette color_palette_pkey; Type: CONSTRAINT; Schema: config; Owner: -
--

ALTER TABLE ONLY config.color_palette
    ADD CONSTRAINT color_palette_pkey PRIMARY KEY (color_hex);


--
-- Name: images images_pkey; Type: CONSTRAINT; Schema: config; Owner: -
--

ALTER TABLE ONLY config.images
    ADD CONSTRAINT images_pkey PRIMARY KEY (public_id);


--
-- Name: images images_public_id_key; Type: CONSTRAINT; Schema: config; Owner: -
--

ALTER TABLE ONLY config.images
    ADD CONSTRAINT images_public_id_key UNIQUE (public_id);


--
-- Name: media media_media_type_key; Type: CONSTRAINT; Schema: config; Owner: -
--

ALTER TABLE ONLY config.media
    ADD CONSTRAINT media_media_type_key UNIQUE (media_type);


--
-- Name: member_labels member_id_unique; Type: CONSTRAINT; Schema: config; Owner: -
--

ALTER TABLE ONLY config.member_labels
    ADD CONSTRAINT member_id_unique UNIQUE (member_id);


--
-- Name: member_labels member_labels_pkey; Type: CONSTRAINT; Schema: config; Owner: -
--

ALTER TABLE ONLY config.member_labels
    ADD CONSTRAINT member_labels_pkey PRIMARY KEY (submitter_id);


--
-- Name: compilations review_unique; Type: CONSTRAINT; Schema: config; Owner: -
--

ALTER TABLE ONLY config.compilations
    ADD CONSTRAINT review_unique UNIQUE (review_id);


--
-- Name: browser_profiles browser_profiles_pkey; Type: CONSTRAINT; Schema: ingestion; Owner: -
--

ALTER TABLE ONLY ingestion.browser_profiles
    ADD CONSTRAINT browser_profiles_pkey PRIMARY KEY (profile_id);


--
-- Name: browsers browsers_pkey; Type: CONSTRAINT; Schema: ingestion; Owner: -
--

ALTER TABLE ONLY ingestion.browsers
    ADD CONSTRAINT browsers_pkey PRIMARY KEY (browser_id);


--
-- Name: repositories repositories_pkey; Type: CONSTRAINT; Schema: ingestion; Owner: -
--

ALTER TABLE ONLY ingestion.repositories
    ADD CONSTRAINT repositories_pkey PRIMARY KEY (repository_id);


--
-- Name: scrape_sources scrape_sources_pkey; Type: CONSTRAINT; Schema: ingestion; Owner: -
--

ALTER TABLE ONLY ingestion.scrape_sources
    ADD CONSTRAINT scrape_sources_pkey PRIMARY KEY (scrape_id);


--
-- Name: shared_albums shared_album_pkey; Type: CONSTRAINT; Schema: ingestion; Owner: -
--

ALTER TABLE ONLY ingestion.shared_albums
    ADD CONSTRAINT shared_album_pkey PRIMARY KEY (album_id);


--
-- Name: address_moves address_moves_pkey; Type: CONSTRAINT; Schema: messaging; Owner: -
--

ALTER TABLE ONLY messaging.address_moves
    ADD CONSTRAINT address_moves_pkey PRIMARY KEY (move_id);


--
-- Name: addresses address_name_unique; Type: CONSTRAINT; Schema: messaging; Owner: -
--

ALTER TABLE ONLY messaging.addresses
    ADD CONSTRAINT address_name_unique UNIQUE (address_name);


--
-- Name: addresses addresses_pkey; Type: CONSTRAINT; Schema: messaging; Owner: -
--

ALTER TABLE ONLY messaging.addresses
    ADD CONSTRAINT addresses_pkey PRIMARY KEY (address_id);


--
-- Name: calendar_events calendar_events_external_event_id_key; Type: CONSTRAINT; Schema: messaging; Owner: -
--

ALTER TABLE ONLY messaging.calendar_events
    ADD CONSTRAINT calendar_events_external_event_id_key UNIQUE (external_event_id);


--
-- Name: calendar_events calendar_events_pkey; Type: CONSTRAINT; Schema: messaging; Owner: -
--

ALTER TABLE ONLY messaging.calendar_events
    ADD CONSTRAINT calendar_events_pkey PRIMARY KEY (calendar_event_id);


--
-- Name: contacts contacts_pkey; Type: CONSTRAINT; Schema: messaging; Owner: -
--

ALTER TABLE ONLY messaging.contacts
    ADD CONSTRAINT contacts_pkey PRIMARY KEY (person_id);


--
-- Name: no_contacts no_contacts_pkey; Type: CONSTRAINT; Schema: messaging; Owner: -
--

ALTER TABLE ONLY messaging.no_contacts
    ADD CONSTRAINT no_contacts_pkey PRIMARY KEY (no_contact_id);


--
-- Name: templates templates_pkey; Type: CONSTRAINT; Schema: messaging; Owner: -
--

ALTER TABLE ONLY messaging.templates
    ADD CONSTRAINT templates_pkey PRIMARY KEY (template_id);


--
-- Name: founder founder_pkey; Type: CONSTRAINT; Schema: nello; Owner: -
--

ALTER TABLE ONLY nello.founder
    ADD CONSTRAINT founder_pkey PRIMARY KEY (is_singleton);


--
-- Name: backfill backfill_review_id_member_id_key; Type: CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.backfill
    ADD CONSTRAINT backfill_review_id_member_id_key UNIQUE (review_id, member_id);


--
-- Name: files file_combination_unique; Type: CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.files
    ADD CONSTRAINT file_combination_unique UNIQUE NULLS NOT DISTINCT (folder_id, file_name, subfolder_name);


--
-- Name: files files_pkey; Type: CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.files
    ADD CONSTRAINT files_pkey PRIMARY KEY (file_id);


--
-- Name: folder_locations folder_locations_pkey; Type: CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.folder_locations
    ADD CONSTRAINT folder_locations_pkey PRIMARY KEY (folder_location_id);


--
-- Name: folder_locations folder_locations_repository_id_repository_item_id_key; Type: CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.folder_locations
    ADD CONSTRAINT folder_locations_repository_id_repository_item_id_key UNIQUE (repository_id, repository_item_id);


--
-- Name: folders folders_name_year_uniq; Type: CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.folders
    ADD CONSTRAINT folders_name_year_uniq UNIQUE NULLS NOT DISTINCT (project_year, media_type, folder_name);


--
-- Name: folders folders_pkey; Type: CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.folders
    ADD CONSTRAINT folders_pkey PRIMARY KEY (folder_id);


--
-- Name: backfill review_member_unique; Type: CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.backfill
    ADD CONSTRAINT review_member_unique UNIQUE (review_id, member_id);


--
-- Name: shares shares_folder_location_id_share_url_key; Type: CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.shares
    ADD CONSTRAINT shares_folder_location_id_share_url_key UNIQUE (folder_location_id, share_url);


--
-- Name: shares shares_pkey; Type: CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.shares
    ADD CONSTRAINT shares_pkey PRIMARY KEY (share_id);


--
-- Name: sources sources_pkey; Type: CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.sources
    ADD CONSTRAINT sources_pkey PRIMARY KEY (source_id);


--
-- Name: sources sources_source_name_key; Type: CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.sources
    ADD CONSTRAINT sources_source_name_key UNIQUE (source_name);


--
-- Name: animals animals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.animals
    ADD CONSTRAINT animals_pkey PRIMARY KEY (animal_id);


--
-- Name: parents child_parent_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parents
    ADD CONSTRAINT child_parent_unique UNIQUE NULLS NOT DISTINCT (child_id, parent_id);


--
-- Name: persons persons_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.persons
    ADD CONSTRAINT persons_pkey PRIMARY KEY (person_id);


--
-- Name: union_members unions_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.union_members
    ADD CONSTRAINT unions_members_pkey PRIMARY KEY (person_id, union_id);


--
-- Name: unions unions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.unions
    ADD CONSTRAINT unions_pkey PRIMARY KEY (union_id);


--
-- Name: appearances appearances_review_id_member_id_start_time_end_time_key; Type: CONSTRAINT; Schema: publishing; Owner: -
--

ALTER TABLE ONLY publishing.appearances
    ADD CONSTRAINT appearances_review_id_member_id_start_time_end_time_key UNIQUE (review_id, member_id, start_time, end_time);


--
-- Name: chapters chapters_review_id_start_time_key; Type: CONSTRAINT; Schema: publishing; Owner: -
--

ALTER TABLE ONLY publishing.chapters
    ADD CONSTRAINT chapters_review_id_start_time_key UNIQUE (review_id, start_time);


--
-- Name: music music_pkey; Type: CONSTRAINT; Schema: publishing; Owner: -
--

ALTER TABLE ONLY publishing.music
    ADD CONSTRAINT music_pkey PRIMARY KEY (track_id);


--
-- Name: reviews reviews_pkey; Type: CONSTRAINT; Schema: publishing; Owner: -
--

ALTER TABLE ONLY publishing.reviews
    ADD CONSTRAINT reviews_pkey PRIMARY KEY (review_id);


--
-- Name: identities identities_pkey; Type: CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.identities
    ADD CONSTRAINT identities_pkey PRIMARY KEY (user_id);


--
-- Name: identity_roles indentity_roles_user_id_role_id_key; Type: CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.identity_roles
    ADD CONSTRAINT indentity_roles_user_id_role_id_key UNIQUE (user_id, role_id);


--
-- Name: pre_approvals pre_approvals_pkey; Type: CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.pre_approvals
    ADD CONSTRAINT pre_approvals_pkey PRIMARY KEY (email_address);


--
-- Name: pre_approvals pre_approvals_role_id_key; Type: CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.pre_approvals
    ADD CONSTRAINT pre_approvals_role_id_key UNIQUE (role_id);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (role_id);


--
-- Name: roles roles_role_name_key; Type: CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.roles
    ADD CONSTRAINT roles_role_name_key UNIQUE (role_name);


--
-- Name: identities unique_issuer_subject; Type: CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.identities
    ADD CONSTRAINT unique_issuer_subject UNIQUE (issuer_name, subject_id);


--
-- Name: calendar_events_marriage_id_key; Type: INDEX; Schema: messaging; Owner: -
--

CREATE UNIQUE INDEX calendar_events_marriage_id_key ON messaging.calendar_events USING btree (union_id) WHERE (union_id IS NOT NULL);


--
-- Name: calendar_events_person_id_key; Type: INDEX; Schema: messaging; Owner: -
--

CREATE UNIQUE INDEX calendar_events_person_id_key ON messaging.calendar_events USING btree (person_id) WHERE (person_id IS NOT NULL);


--
-- Name: files_folder_id_idx; Type: INDEX; Schema: project; Owner: -
--

CREATE INDEX files_folder_id_idx ON project.files USING btree (folder_id);


--
-- Name: folder_locations_folder_id_repository_id_idx; Type: INDEX; Schema: project; Owner: -
--

CREATE INDEX folder_locations_folder_id_repository_id_idx ON project.folder_locations USING btree (folder_id, repository_id);


--
-- Name: folder_locations_one_canonical; Type: INDEX; Schema: project; Owner: -
--

CREATE UNIQUE INDEX folder_locations_one_canonical ON project.folder_locations USING btree (folder_id) WHERE is_canonical;


--
-- Name: folders_project_year_person_id_idx; Type: INDEX; Schema: project; Owner: -
--

CREATE INDEX folders_project_year_person_id_idx ON project.folders USING btree (project_year, person_id) WHERE (person_id IS NOT NULL);


--
-- Name: apexes _RETURN; Type: RULE; Schema: tree; Owner: -
--

CREATE OR REPLACE VIEW tree.apexes AS
 WITH orphan_single_parents AS (
         SELECT DISTINCT p.parent_id AS member_id
           FROM (public.parents p
             LEFT JOIN public.parents q ON ((p.parent_id = q.child_id)))
          WHERE (q.parent_id IS NULL)
        EXCEPT
         SELECT partners.person_id
           FROM tree.partners
        ), inlaws AS (
         SELECT partners.person_id,
            parents.parent_id,
            partners.union_id AS marriage_id
           FROM (tree.partners
             LEFT JOIN public.parents ON ((partners.person_id = parents.child_id)))
        ), orphan_married_parents AS (
         SELECT inlaws.marriage_id
           FROM inlaws
          GROUP BY inlaws.marriage_id
         HAVING (count(inlaws.parent_id) = 0)
        )
 SELECT orphan_married_parents.marriage_id AS node_id,
    partners.person_id AS member_id
   FROM (orphan_married_parents
     JOIN tree.partners partners(person_id, spouse_id, marriage_id, union_type) USING (marriage_id))
UNION
 SELECT orphan_single_parents.member_id AS node_id,
    orphan_single_parents.member_id
   FROM orphan_single_parents;


--
-- Name: friends _RETURN; Type: RULE; Schema: tree; Owner: -
--

CREATE OR REPLACE VIEW tree.friends AS
 WITH valid_friendlies AS (
         SELECT unions.union_id,
            unions.union_type
           FROM (public.unions
             JOIN public.union_members USING (union_id))
          WHERE (unions.union_type = ANY (ARRAY['friends'::text]))
          GROUP BY unions.union_id
         HAVING (count(unions.union_id) = 2)
        )
 SELECT u1.person_id,
    u2.person_id AS spouse_id,
    u1.union_id,
    valid_friendlies.union_type
   FROM ((public.union_members u1
     JOIN valid_friendlies USING (union_id))
     JOIN public.union_members u2 USING (union_id))
  WHERE (u1.person_id <> u2.person_id);


--
-- Name: nodes _RETURN; Type: RULE; Schema: tree; Owner: -
--

CREATE OR REPLACE VIEW tree.nodes AS
 WITH nodules AS (
         SELECT parents.child_id AS member_id,
            parents.parent_id AS head_id
           FROM public.parents
        UNION
         SELECT pets.pet_id AS member_id,
            pets.owner_id AS head_id
           FROM public.pets
        )
 SELECT DISTINCT ON (nodules.member_id) nodules.member_id,
    COALESCE(partners.union_id, nodules.head_id) AS node_id
   FROM (nodules
     LEFT JOIN tree.partners ON ((nodules.head_id = partners.person_id)));


--
-- Name: partners _RETURN; Type: RULE; Schema: tree; Owner: -
--

CREATE OR REPLACE VIEW tree.partners AS
 WITH valid_marriages AS (
         SELECT unions.union_id,
            unions.union_type
           FROM (public.unions
             JOIN public.union_members USING (union_id))
          WHERE (unions.union_type = ANY (ARRAY['marriage'::text, 'civil'::text]))
          GROUP BY unions.union_id
         HAVING (count(unions.union_id) = 2)
        )
 SELECT u1.person_id,
    u2.person_id AS spouse_id,
    u1.union_id,
    valid_marriages.union_type
   FROM ((public.union_members u1
     JOIN valid_marriages USING (union_id))
     JOIN public.union_members u2 USING (union_id))
  WHERE (u1.person_id <> u2.person_id);


--
-- Name: union_members enforce_union_member_limit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE CONSTRAINT TRIGGER enforce_union_member_limit AFTER INSERT OR UPDATE ON public.union_members DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_union_member_limit();


--
-- Name: adobe_labels adobe_labels_color_name_fkey; Type: FK CONSTRAINT; Schema: config; Owner: -
--

ALTER TABLE ONLY config.adobe_labels
    ADD CONSTRAINT adobe_labels_color_name_fkey FOREIGN KEY (color_name) REFERENCES config.color_palette(color_name);


--
-- Name: compilations compilations_2_review_id_fkey; Type: FK CONSTRAINT; Schema: config; Owner: -
--

ALTER TABLE ONLY config.compilations
    ADD CONSTRAINT compilations_2_review_id_fkey FOREIGN KEY (review_id) REFERENCES publishing.reviews(review_id);


--
-- Name: member_labels member_labels_animal_id_fkey; Type: FK CONSTRAINT; Schema: config; Owner: -
--

ALTER TABLE ONLY config.member_labels
    ADD CONSTRAINT member_labels_animal_id_fkey FOREIGN KEY (animal_id) REFERENCES public.animals(animal_id);


--
-- Name: member_labels member_labels_label_id_fkey; Type: FK CONSTRAINT; Schema: config; Owner: -
--

ALTER TABLE ONLY config.member_labels
    ADD CONSTRAINT member_labels_label_id_fkey FOREIGN KEY (label_id) REFERENCES config.adobe_labels(label_id);


--
-- Name: member_labels member_labels_person_id_fkey; Type: FK CONSTRAINT; Schema: config; Owner: -
--

ALTER TABLE ONLY config.member_labels
    ADD CONSTRAINT member_labels_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.persons(person_id);


--
-- Name: member_labels member_labels_source_id_fkey; Type: FK CONSTRAINT; Schema: config; Owner: -
--

ALTER TABLE ONLY config.member_labels
    ADD CONSTRAINT member_labels_source_id_fkey FOREIGN KEY (source_id) REFERENCES project.sources(source_id);


--
-- Name: browser_profiles browser_profiles_browser_id_fkey; Type: FK CONSTRAINT; Schema: ingestion; Owner: -
--

ALTER TABLE ONLY ingestion.browser_profiles
    ADD CONSTRAINT browser_profiles_browser_id_fkey FOREIGN KEY (browser_id) REFERENCES ingestion.browsers(browser_id);


--
-- Name: shared_albums shared_albums_folder_id_fkey; Type: FK CONSTRAINT; Schema: ingestion; Owner: -
--

ALTER TABLE ONLY ingestion.shared_albums
    ADD CONSTRAINT shared_albums_folder_id_fkey FOREIGN KEY (folder_id) REFERENCES project.folders(folder_id);


--
-- Name: shared_albums shared_albums_profile_id_fkey; Type: FK CONSTRAINT; Schema: ingestion; Owner: -
--

ALTER TABLE ONLY ingestion.shared_albums
    ADD CONSTRAINT shared_albums_profile_id_fkey FOREIGN KEY (profile_id) REFERENCES ingestion.browser_profiles(profile_id);


--
-- Name: address_moves address_moves_address_id_fkey; Type: FK CONSTRAINT; Schema: messaging; Owner: -
--

ALTER TABLE ONLY messaging.address_moves
    ADD CONSTRAINT address_moves_address_id_fkey FOREIGN KEY (address_id) REFERENCES messaging.addresses(address_id);


--
-- Name: address_moves address_moves_person_id_fkey; Type: FK CONSTRAINT; Schema: messaging; Owner: -
--

ALTER TABLE ONLY messaging.address_moves
    ADD CONSTRAINT address_moves_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.persons(person_id);


--
-- Name: calendar_events calendar_events_marriage_id_fkey; Type: FK CONSTRAINT; Schema: messaging; Owner: -
--

ALTER TABLE ONLY messaging.calendar_events
    ADD CONSTRAINT calendar_events_marriage_id_fkey FOREIGN KEY (union_id) REFERENCES public.unions(union_id);


--
-- Name: calendar_events calendar_events_person_id_fkey; Type: FK CONSTRAINT; Schema: messaging; Owner: -
--

ALTER TABLE ONLY messaging.calendar_events
    ADD CONSTRAINT calendar_events_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.persons(person_id);


--
-- Name: contacts contacts_person_id_fkey; Type: FK CONSTRAINT; Schema: messaging; Owner: -
--

ALTER TABLE ONLY messaging.contacts
    ADD CONSTRAINT contacts_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.persons(person_id);


--
-- Name: no_contacts no_contacts_person_id_fkey; Type: FK CONSTRAINT; Schema: messaging; Owner: -
--

ALTER TABLE ONLY messaging.no_contacts
    ADD CONSTRAINT no_contacts_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.persons(person_id);


--
-- Name: founder founder_founder_id_fkey; Type: FK CONSTRAINT; Schema: nello; Owner: -
--

ALTER TABLE ONLY nello.founder
    ADD CONSTRAINT founder_founder_id_fkey FOREIGN KEY (founder_id) REFERENCES public.persons(person_id);


--
-- Name: backfill backfill_review_id_fkey; Type: FK CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.backfill
    ADD CONSTRAINT backfill_review_id_fkey FOREIGN KEY (review_id) REFERENCES publishing.reviews(review_id);


--
-- Name: files files_folder_id_fkey; Type: FK CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.files
    ADD CONSTRAINT files_folder_id_fkey FOREIGN KEY (folder_id) REFERENCES project.folders(folder_id) ON DELETE CASCADE;


--
-- Name: folder_locations folder_locations_folder_id_fkey; Type: FK CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.folder_locations
    ADD CONSTRAINT folder_locations_folder_id_fkey FOREIGN KEY (folder_id) REFERENCES project.folders(folder_id);


--
-- Name: folder_locations folder_locations_repository_id_fkey; Type: FK CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.folder_locations
    ADD CONSTRAINT folder_locations_repository_id_fkey FOREIGN KEY (repository_id) REFERENCES ingestion.repositories(repository_id);


--
-- Name: folders folders_animal_id_fkey; Type: FK CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.folders
    ADD CONSTRAINT folders_animal_id_fkey FOREIGN KEY (animal_id) REFERENCES public.animals(animal_id) ON DELETE SET NULL;


--
-- Name: folders folders_media_type_fkey; Type: FK CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.folders
    ADD CONSTRAINT folders_media_type_fkey FOREIGN KEY (media_type) REFERENCES config.media(media_type);


--
-- Name: folders folders_person_id_fkey; Type: FK CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.folders
    ADD CONSTRAINT folders_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.persons(person_id) ON DELETE SET NULL;


--
-- Name: folders folders_source_id_fkey; Type: FK CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.folders
    ADD CONSTRAINT folders_source_id_fkey FOREIGN KEY (source_id) REFERENCES project.sources(source_id);


--
-- Name: shares shares_folder_location_id_fkey; Type: FK CONSTRAINT; Schema: project; Owner: -
--

ALTER TABLE ONLY project.shares
    ADD CONSTRAINT shares_folder_location_id_fkey FOREIGN KEY (folder_location_id) REFERENCES project.folder_locations(folder_location_id) ON DELETE CASCADE;


--
-- Name: unions unions_last_name_person_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.unions
    ADD CONSTRAINT unions_last_name_person_id_fkey FOREIGN KEY (last_name_person_id) REFERENCES public.persons(person_id);


--
-- Name: union_members unions_members_person_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.union_members
    ADD CONSTRAINT unions_members_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.persons(person_id);


--
-- Name: union_members unions_members_union_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.union_members
    ADD CONSTRAINT unions_members_union_id_fkey FOREIGN KEY (union_id) REFERENCES public.unions(union_id);


--
-- Name: appearances appearances_review_id_fkey; Type: FK CONSTRAINT; Schema: publishing; Owner: -
--

ALTER TABLE ONLY publishing.appearances
    ADD CONSTRAINT appearances_review_id_fkey FOREIGN KEY (review_id) REFERENCES publishing.reviews(review_id);


--
-- Name: chapters chapters_review_id_fkey; Type: FK CONSTRAINT; Schema: publishing; Owner: -
--

ALTER TABLE ONLY publishing.chapters
    ADD CONSTRAINT chapters_review_id_fkey FOREIGN KEY (review_id) REFERENCES publishing.reviews(review_id);


--
-- Name: music music_review_id_fkey; Type: FK CONSTRAINT; Schema: publishing; Owner: -
--

ALTER TABLE ONLY publishing.music
    ADD CONSTRAINT music_review_id_fkey FOREIGN KEY (review_id) REFERENCES publishing.reviews(review_id);


--
-- Name: identities identities_person_id_fkey; Type: FK CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.identities
    ADD CONSTRAINT identities_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.persons(person_id);


--
-- Name: identity_roles indentity_roles_role_id_fkey; Type: FK CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.identity_roles
    ADD CONSTRAINT indentity_roles_role_id_fkey FOREIGN KEY (role_id) REFERENCES users.roles(role_id);


--
-- Name: identity_roles indentity_roles_user_id_fkey; Type: FK CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.identity_roles
    ADD CONSTRAINT indentity_roles_user_id_fkey FOREIGN KEY (user_id) REFERENCES users.identities(user_id) ON DELETE CASCADE;


--
-- Name: pre_approvals pre_approvals_role_id_fkey; Type: FK CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.pre_approvals
    ADD CONSTRAINT pre_approvals_role_id_fkey FOREIGN KEY (role_id) REFERENCES users.roles(role_id);


--
-- PostgreSQL database dump complete
--
