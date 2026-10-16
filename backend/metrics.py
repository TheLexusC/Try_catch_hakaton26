"""Расчёт показателей района.

Считаем на сервере, для фиксированного радиуса 500 м, чтобы сценарии
«до» и «после» можно было сравнивать между собой.
"""
from .data import MAP
from .graph import build_graph, dijkstra, nearest_target

PARK_RADIUS = 500  # метров по дорожкам


def facility_nodes(state, kind):
    """Узлы, в которых стоят объекты нужного типа (stop или park)."""
    return [f['node'] for f in state['facilities'] if f['kind'] == kind]


def home_row(graph, home, stops, parks, radius):
    """Считает путь от одного дома до ближайшей остановки и ближайшего парка."""
    distances, previous = dijkstra(graph, home['node'])

    stop_distance, stop_path = nearest_target(distances, previous, home['node'], stops)
    park_distance, park_path = nearest_target(distances, previous, home['node'], parks)

    # Сравниваем с радиусом точное расстояние, без округления.
    park_access = bool(park_path) and distances[park_path[-1]] <= radius

    return {
        **home,
        'stop_distance': stop_distance,
        'park_distance': park_distance,
        'stop_path': stop_path,
        'park_path': park_path,
        'park_access': park_access,
    }


def calculate_metrics(state, radius=PARK_RADIUS):
    graph = build_graph(MAP['nodes'], MAP['edges'], state['closed_edges'])
    stops = facility_nodes(state, 'stop')
    parks = facility_nodes(state, 'park')

    rows = [home_row(graph, home, stops, parks, radius) for home in MAP['homes']]

    # Среднее до остановки считаем только по домам, откуда она достижима.
    stop_distances = [r['stop_distance'] for r in rows if r['stop_distance'] is not None]
    if stop_distances:
        average_stop = round(sum(stop_distances) / len(stop_distances), 1)
    else:
        average_stop = None

    total = sum(r['residents'] for r in rows)
    accessible = sum(r['residents'] for r in rows if r['park_access'])

    return {
        'average_stop': average_stop,
        'park_percent': round(100 * accessible / total, 1),
        'accessible_residents': accessible,
        'total_residents': total,
        'unreachable_homes': len(rows) - len(stop_distances),
        'radius': radius,
        'rows': rows,
    }
