-- Traverse direct parent, pet-owner, and partner relationships instead of
-- inferring relationships from clans. Every dashboard member is returned once;
-- unrelated or not-yet-present members have a NULL generation. Parent/owner
-- sets form deterministic node keys, and downward traversal appends each
-- dependent's sibling order to an integer-array lineage. Upward traversal
-- appends opening-branch and parent positions to an ancestry array.
--
-- Date handling uses the latest possible date for month/year precision. A
-- missing date with no precision is treated as unknown and therefore active;
-- a missing date marked future is not active at any finite cutoff. Death does
-- not remove a relationship edge; callers may filter deceased members after
-- traversal without disconnecting their living relatives.
--
-- Rollback:
--   DROP FUNCTION dashboard.family_members(uuid, date, text, boolean);

DROP FUNCTION IF EXISTS dashboard.family_members(uuid, date, text, boolean);

CREATE FUNCTION dashboard.family_members(
    p_start_member_id uuid,
    p_cut_date date DEFAULT CURRENT_DATE,
    p_traversal_mode text DEFAULT 'up_down',
    p_include_partner_branches boolean DEFAULT true
)
RETURNS TABLE (
    member_id uuid,
    generation integer,
    traversal_depth integer,
    discovered_from uuid,
    discovery_direction text,
    relation_type text,
    in_law boolean,
    parent_node_key text,
    parent_node_type text,
    parent_node_head_ids uuid[],
    headed_node_keys text[],
    sibling_order integer,
    lineage integer[],
    ancestry integer[]
)
LANGUAGE plpgsql
STABLE
AS $function$
DECLARE
    v_cut_date date := COALESCE(p_cut_date, CURRENT_DATE);
BEGIN
    IF p_start_member_id IS NULL THEN
        RAISE EXCEPTION 'A starting dashboard member is required.';
    END IF;

    IF p_traversal_mode NOT IN ('up', 'down', 'up_down', 'bidirectional') THEN
        RAISE EXCEPTION
            'Unsupported traversal mode: %. Expected up, down, up_down, or bidirectional.',
            p_traversal_mode;
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM dashboard.member_information AS information
         WHERE information.member_id = p_start_member_id
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
    node_head_sets AS (
        SELECT
            link.dependent_id,
            link.dependent_type,
            array_agg(DISTINCT link.head_id ORDER BY link.head_id) AS head_ids,
            max(link.sort_date) AS sort_date
          FROM structural_links AS link
         GROUP BY link.dependent_id, link.dependent_type
    ),
    classified_nodes AS (
        SELECT
            head_set.dependent_id AS member_id,
            'node:v1:heads:' || array_to_string(head_set.head_ids, ':') AS node_key,
            CASE cardinality(head_set.head_ids)
                WHEN 1 THEN 'solo'
                WHEN 2 THEN 'pair'
                ELSE 'multiple'
            END AS node_type,
            head_set.head_ids,
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
                                       array_position(source_node.head_ids, edge.target_id),
                                       0
                                   )
                               ]
                           ELSE ARRAY[
                               COALESCE(
                                   array_position(source_node.head_ids, edge.target_id),
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
      FROM dashboard.member_information AS information
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
$function$;

COMMENT ON FUNCTION dashboard.family_members(uuid, date, text, boolean) IS
'Calculates generations, family-tree node classifications, sibling order, descendant lineage, and branch-aware ancestry from dated parent, pet-owner, and partner edges. Modes are up, down, up_down, and bidirectional; unrelated dashboard members have NULL generation.';
