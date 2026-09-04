"""Build a duplicate-safe Graphviz graph from database-classified family nodes."""

from collections.abc import Mapping
from datetime import date
from uuid import UUID

from graphviz import Digraph
from pandas import DataFrame, isna


REQUIRED_COLUMNS = {
    'node_id', 'node_type', 'generation', 'x_order', 'parent_head_id',
    'tail_id', 'tail_type', 'union_type', 'union_date',
    'union_date_precision',
}


def build_family_graph(nodes:DataFrame,
                       labels:Mapping[UUID, str]|None=None) -> Digraph:
    """Convert family-graph rows to a strict, top-to-bottom Graphviz graph."""
    missing = REQUIRED_COLUMNS.difference(nodes.columns)
    if missing:
        raise ValueError(f'Missing family graph columns: {sorted(missing)}')

    node_ids = [_node_text(value) for value in nodes['node_id']]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError('Family graph rows contain duplicate node IDs.')

    known_ids = set(node_ids)
    graph = Digraph(
        strict=True,
        graph_attr={'rankdir': 'TB'},
        edge_attr={'dir': 'none'},
    )
    labels = labels or {}

    ordered = nodes.sort_values(
        ['generation', 'x_order', 'node_id'], na_position='last'
    )
    for generation, generation_nodes in ordered.groupby(
            'generation', dropna=False, sort=False):
        rank_name = 'unknown' if isna(generation) else str(generation)
        with graph.subgraph(name=f'rank_{rank_name}') as rank:
            rank.attr(rank='same')
            for row in generation_nodes.itertuples(index=False):
                node_id = _node_text(row.node_id)
                if row.node_type == 'union':
                    rank.node(
                        node_id, label='', shape='point', width='0.08',
                        tooltip=_union_tooltip(row),
                    )
                else:
                    label = labels.get(row.node_id, row.node_type)
                    rank.node(node_id, label=str(label), shape='box')

    edges:set[tuple[str, str]] = set()
    for row in ordered.itertuples(index=False):
        node_id = _node_text(row.node_id)
        if not isna(row.parent_head_id):
            _add_edge(graph, edges, known_ids,
                      _node_text(row.parent_head_id), node_id)
        if not isna(row.tail_id):
            attributes = {} if row.tail_type == 'union' else {
                'style': 'invis', 'weight': '100',
            }
            _add_edge(graph, edges, known_ids, node_id,
                      _node_text(row.tail_id), **attributes)

    return graph


def _add_edge(graph:Digraph, edges:set[tuple[str, str]], known_ids:set[str],
              head:str, tail:str, **attributes:str) -> None:
    """Add one canonical directed edge after validating both endpoints."""
    if head not in known_ids or tail not in known_ids:
        raise ValueError(f'Family graph edge references an unknown node: {head} -> {tail}')
    if head == tail:
        raise ValueError(f'Family graph contains a self-edge for {head}.')
    edge = (head, tail)
    if edge not in edges:
        graph.edge(head, tail, **attributes)
        edges.add(edge)


def _node_text(value:object) -> str:
    """Normalize UUID-like database values for Graphviz identifiers."""
    if value is None or isna(value):
        raise ValueError('Family graph node IDs cannot be NULL.')
    return str(value)


def _union_tooltip(row:object) -> str:
    """Build optional hover text for an official or synthetic union junction."""
    union_type = '' if isna(row.union_type) else str(row.union_type).replace('_', ' ').title()
    if isna(row.union_date):
        return union_type or 'Partnership'
    union_date = row.union_date
    if not isinstance(union_date, date):
        union_date = date.fromisoformat(str(union_date))
    rendered_date = union_date.strftime('%B %d, %Y').replace(' 0', ' ')
    return f'{union_type or "Partnership"}: {rendered_date}'
