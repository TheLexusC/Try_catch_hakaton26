"""Weighted, undirected pedestrian graph. No third-party routing service."""
from heapq import heappop, heappush
from math import inf


def build_graph(nodes, edges, closed=()):
    graph = {node['id']: {} for node in nodes}
    for edge in edges:
        if edge['length'] < 0:
            raise ValueError('Дейкстра требует неотрицательные веса')
        if edge['id'] in closed:
            continue
        a, b, weight = edge['a'], edge['b'], edge['length']
        # Parallel paths are allowed; retain the shortest traversable one.
        graph[a][b] = min(weight, graph[a].get(b, inf))
        graph[b][a] = min(weight, graph[b].get(a, inf))
    return graph


def dijkstra(graph, start):
    if start not in graph:
        raise ValueError('Неизвестный стартовый узел')
    distances = {node: inf for node in graph}
    previous = {node: None for node in graph}
    distances[start] = 0
    queue = [(0, start)]
    while queue:
        distance, node = heappop(queue)
        if distance != distances[node]:
            continue
        for neighbor, weight in graph[node].items():
            if weight < 0:
                raise ValueError('Отрицательный вес')
            candidate = distance + weight
            if candidate < distances[neighbor]:
                distances[neighbor] = candidate
                previous[neighbor] = node
                heappush(queue, (candidate, neighbor))
    return distances, previous


def restore_path(previous, start, finish):
    path, node = [], finish
    while node is not None:
        path.append(node)
        if node == start:
            return path[::-1]
        node = previous.get(node)
    return []


def nearest_target(distances, previous, start, targets):
    valid = [target for target in targets if distances.get(target, inf) != inf]
    if not valid:
        return None, []
    target = min(valid, key=lambda node: (distances[node], node))
    return round(distances[target], 1), restore_path(previous, start, target)
