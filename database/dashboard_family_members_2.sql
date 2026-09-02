-- Traverse direct parent, pet-owner, and partner relationships instead of
-- inferring relationships from clans. Every dashboard member is returned once;
-- unrelated or not-yet-present members have a NULL generation.
--
-- Date handling uses the latest possible date for month/year precision. A
-- missing date with no precision is treated as unknown and therefore active;
-- a missing date marked future is not active at any finite cutoff. Death does
-- not remove a relationship edge; callers may filter deceased members after
-- traversal without disconnecting their living relatives.
--
-- Rollback:
--   DROP FUNCTION dashboard.family_members_2(uuid, date, text, boolean);

CREATE OR REPLACE FUNCTION dashboard.family_members_2(
    p_start_member_id uuid,
    p_cut_date date,
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
    in_law boolean
)
LANGUAGE plpgsql
STABLE
AS $function$
BEGIN
    IF p_start_member_id IS NULL THEN
        RAISE EXCEPTION 'A starting dashboard member is required.';
    END IF;

    IF p_cut_date IS NULL THEN
        RAISE EXCEPTION 'A family traversal cutoff date is required.';
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
            END AS entry_date
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
            END AS entry_date
          FROM public.animals AS animal
    ),
    present_members AS (
        SELECT member.member_id, member.member_type
          FROM members AS member
         WHERE member.entry_date <= p_cut_date
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
               END <= p_cut_date
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
               END <= p_cut_date
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
            ARRAY[opening.member_id]::uuid[] AS member_path
          FROM opening_members AS opening
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
            walk.member_path || edge.target_id
          FROM walk
          JOIN edges AS edge
            ON edge.source_id = walk.member_id
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
        ranked.in_law
      FROM dashboard.member_information AS information
      LEFT JOIN ranked
        ON ranked.member_id = information.member_id
       AND ranked.preference = 1
     ORDER BY
        ranked.generation NULLS LAST,
        ranked.traversal_depth NULLS LAST,
        information.member_id;
END;
$function$;

COMMENT ON FUNCTION dashboard.family_members_2(uuid, date, text, boolean) IS
'Calculates generations from dated parent, pet-owner, and partner edges. Modes are up, down, up_down, and bidirectional; unrelated dashboard members have NULL generation.';
