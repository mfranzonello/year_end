-- Add flattened-timeline display units and ordering to the reusable family
-- traversal. This wrapper classifies presentation units after recursion.
--
-- Impact: requires family_members to return UUID node keys and uuid-ossp.
-- Rollback: DROP FUNCTION dashboard.family_members_display(uuid,date,text,boolean);

CREATE OR REPLACE FUNCTION dashboard.family_members_display(
    p_start_member_id uuid,
    p_cut_date date DEFAULT CURRENT_DATE,
    p_traversal_mode text DEFAULT 'down',
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
    parent_node_key uuid,
    parent_node_type text,
    parent_node_head_ids uuid[],
    headed_node_keys uuid[],
    sibling_order integer,
    lineage integer[],
    ancestry integer[],
    display_unit_key uuid,
    display_unit_lineage integer[],
    display_unit_depth integer,
    display_role text,
    display_order integer
)
LANGUAGE sql
STABLE
AS $function$
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
          p_include_partner_branches
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
        family.member_id,
        headed_node.node_key,
        1 AS unit_priority,
        NULL::date AS effective_date
      FROM family
      CROSS JOIN LATERAL unnest(family.headed_node_keys) AS headed_node(node_key)
     WHERE family.generation IS NOT NULL
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
assigned_units AS (
    SELECT
        family.*,
        own_unit.unit_key AS own_unit_key,
        COALESCE(
            own_unit.unit_key,
            family.parent_node_key,
            public.uuid_generate_v5(
                '6ba7b811-9dad-11d1-80b4-00c04fd430c8'::uuid,
                'dashboard.family-node:v1:heads:' || family.member_id::text
            )
        ) AS unit_key,
        information.member_type,
        information.birth_date,
        information.entry_date
      FROM family
      JOIN dashboard.member_information AS information
        ON information.member_id = family.member_id
      LEFT JOIN selected_own_units AS own_unit
        ON own_unit.member_id = family.member_id
     WHERE family.generation IS NOT NULL
),
unit_anchors AS (
    SELECT DISTINCT ON (assigned.unit_key)
        assigned.unit_key,
        CASE
            WHEN assigned.own_unit_key = assigned.unit_key THEN assigned.lineage
            WHEN cardinality(assigned.lineage) > 0
                THEN assigned.lineage[1:cardinality(assigned.lineage) - 1]
            ELSE ARRAY[]::integer[]
        END AS unit_lineage
      FROM assigned_units AS assigned
     ORDER BY
        assigned.unit_key,
        CASE WHEN assigned.own_unit_key = assigned.unit_key THEN 0 ELSE 1 END,
        assigned.in_law,
        cardinality(assigned.lineage),
        assigned.member_id
),
display_members AS (
    SELECT
        assigned.*,
        anchor.unit_lineage,
        CASE
            WHEN assigned.member_type = 'animal' THEN 'animal'
            WHEN assigned.own_unit_key = assigned.unit_key AND assigned.in_law
                THEN 'partner'
            WHEN assigned.own_unit_key = assigned.unit_key THEN 'head'
            ELSE 'dependent'
        END AS unit_role
      FROM assigned_units AS assigned
      JOIN unit_anchors AS anchor
        ON anchor.unit_key = assigned.unit_key
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
    display.unit_lineage AS display_unit_lineage,
    cardinality(display.unit_lineage)::integer AS display_unit_depth,
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
    cardinality(display.unit_lineage),
    display.unit_lineage,
    display_order;
$function$;

COMMENT ON FUNCTION dashboard.family_members_display(uuid, date, text, boolean) IS
'Adds UUIDv5 display-unit identity, breadth-first unit paths, roles, and within-unit ordering to dashboard.family_members for the flattened timeline.';
