"""Weighted, undirected pedestrian graph. No third-party routing service."""
from heapq import heappop, heappush
from math import inf


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
