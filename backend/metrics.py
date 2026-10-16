"""Metrics are recalculated on the server for a fixed, comparable 500 m radius."""
from .data import MAP
from .graph import build_graph, dijkstra, nearest_target


def calculate_metrics(state, radius=500):
    graph = build_graph(MAP['nodes'], MAP['edges'], state['closed_edges'])
    stops = [f['node'] for f in state['facilities'] if f['kind'] == 'stop']
    parks = [f['node'] for f in state['facilities'] if f['kind'] == 'park']
    rows = []
    for home in MAP['homes']:
        distances, previous = dijkstra(graph, home['node'])
        stop, stop_path = nearest_target(distances, previous, home['node'], stops)
        park, park_path = nearest_target(distances, previous, home['node'], parks)
        # Use unrounded path distance at the threshold boundary.
        park_access = bool(park_path) and distances[park_path[-1]] <= radius
        rows.append({**home, 'stop_distance': stop, 'park_distance': park,
                     'stop_path': stop_path, 'park_path': park_path, 'park_access': park_access})
    reachable = [r['stop_distance'] for r in rows if r['stop_distance'] is not None]
    total = sum(r['residents'] for r in rows)
    accessible = sum(r['residents'] for r in rows if r['park_access'])
    return {'average_stop': round(sum(reachable)/len(reachable), 1) if reachable else None,
            'park_percent': round(100*accessible/total, 1), 'accessible_residents': accessible,
            'total_residents': total, 'unreachable_homes': len(rows)-len(reachable),
            'radius': radius, 'rows': rows}
