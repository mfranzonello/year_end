-- Return every dashboard member with their generation relative to a resolved
-- clan head. Unrelated members remain in the result with a NULL generation.
--
-- Traversal modes:
--   up            ancestors only
--   down          descendants only
--   up_down       independent ancestor and descendant walks
--   bidirectional unrestricted walking that may change direction
--
-- Rollback:
--   DROP FUNCTION dashboard.family_members(uuid, date, text, boolean);

CREATE OR REPLACE FUNCTION dashboard.family_members(
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
    discovery_direction text
)
LANGUAGE plpgsql
STABLE
AS $function$
DECLARE
    v_anchor_clan_id uuid;
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

    SELECT CASE
               WHEN information.clan_date IS NULL
                    OR information.clan_date <= v_cut_date
                   THEN information.clan_id_1
               ELSE information.clan_id_2
           END
      INTO v_anchor_clan_id
      FROM dashboard.member_information AS information
     WHERE information.member_id = p_start_member_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown dashboard member: %', p_start_member_id;
    END IF;

    IF v_anchor_clan_id IS NULL THEN
        RAISE EXCEPTION
            'Dashboard member % has no clan at cutoff date %.',
            p_start_member_id,
            v_cut_date;
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM dashboard.member_information AS information
         WHERE information.clan_id_1 = v_anchor_clan_id
           AND information.is_clan_1_head
           AND (
               information.clan_date IS NULL
               OR information.clan_date <= v_cut_date
           )
    ) THEN
        RAISE EXCEPTION
            'Clan % has no discoverable head at cutoff date %.',
            v_anchor_clan_id,
            v_cut_date;
    END IF;

    RETURN QUERY
    WITH RECURSIVE
    memberships AS (
        -- clan_id_1 is usable only after that clan came into effect.
        SELECT DISTINCT
            information.member_id,
            information.clan_id_1 AS clan_id,
            information.is_clan_1_head AS is_head
          FROM dashboard.member_information AS information
         WHERE information.clan_id_1 IS NOT NULL
           AND (
               information.clan_date IS NULL
               OR information.clan_date <= v_cut_date
           )

        UNION

        -- clan_id_2 records the clan from which a member came. By definition,
        -- that member was not a head of clan_id_2.
        SELECT DISTINCT
            information.member_id,
            information.clan_id_2 AS clan_id,
            false AS is_head
          FROM dashboard.member_information AS information
         WHERE information.clan_id_2 IS NOT NULL
    ),
    heads AS (
        SELECT membership.member_id, membership.clan_id
          FROM memberships AS membership
         WHERE membership.is_head
    ),
    non_heads AS (
        SELECT membership.member_id, membership.clan_id
          FROM memberships AS membership
         WHERE NOT membership.is_head
    ),
    edges AS (
        -- Moving from a clan head to a non-head moves down one generation.
        SELECT DISTINCT
            head.member_id AS source_id,
            non_head.member_id AS target_id,
            1 AS generation_delta,
            'down'::text AS edge_direction
          FROM heads AS head
          JOIN non_heads AS non_head USING (clan_id)
         WHERE head.member_id <> non_head.member_id

        UNION

        -- The reverse edge moves up one generation.
        SELECT DISTINCT
            non_head.member_id AS source_id,
            head.member_id AS target_id,
            -1 AS generation_delta,
            'up'::text AS edge_direction
          FROM non_heads AS non_head
          JOIN heads AS head USING (clan_id)
         WHERE non_head.member_id <> head.member_id

        UNION

        -- Co-heads are partners in the same generation. Omitting these edges
        -- keeps the other partner and their family branches out of the walk.
        SELECT DISTINCT
            head_1.member_id AS source_id,
            head_2.member_id AS target_id,
            0 AS generation_delta,
            'partner'::text AS edge_direction
          FROM heads AS head_1
          JOIN heads AS head_2 USING (clan_id)
         WHERE p_include_partner_branches
           AND head_1.member_id <> head_2.member_id
    ),
    requested_member AS (
        SELECT bool_or(membership.is_head) AS is_anchor_head
          FROM memberships AS membership
         WHERE membership.member_id = p_start_member_id
           AND membership.clan_id = v_anchor_clan_id
    ),
    resolved_founders AS (
        -- A requested head remains the root. Include their co-heads only when
        -- partner branches were requested.
        SELECT head.member_id
          FROM heads AS head
          JOIN requested_member AS requested
            ON requested.is_anchor_head
         WHERE head.clan_id = v_anchor_clan_id
           AND (
               p_include_partner_branches
               OR head.member_id = p_start_member_id
           )

        UNION

        -- A requested non-head resolves to every head of their effective clan.
        SELECT head.member_id
          FROM heads AS head
          JOIN requested_member AS requested
            ON NOT requested.is_anchor_head
         WHERE head.clan_id = v_anchor_clan_id
    ),
    seeds AS (
        SELECT
            founder.member_id,
            0 AS generation,
            0 AS traversal_depth,
            NULL::uuid AS discovered_from,
            CASE
                WHEN p_traversal_mode = 'up_down' THEN mode.direction
                ELSE p_traversal_mode
            END AS walk_direction,
            'seed'::text AS discovery_direction,
            ARRAY[founder.member_id]::uuid[] AS member_path
          FROM resolved_founders AS founder
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
            row_number() OVER (
                PARTITION BY walk.member_id
                ORDER BY
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
        ranked.discovery_direction
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

COMMENT ON FUNCTION dashboard.family_members(uuid, date, text, boolean) IS
'Calculates family generations relative to resolved clan heads. Modes are up, down, up_down, and bidirectional; unrelated dashboard members have NULL generation.';
