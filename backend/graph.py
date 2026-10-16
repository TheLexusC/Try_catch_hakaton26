import heapq
from math import inf

def dijkstra(graph, start):
    distances = {node: inf for node in graph}
    previous = {node: None for node in graph}

    distances[start] = 0
    queue = [(0, start)]

    while queue:
        dist, node = heapq.heappop(queue)

        if dist > distances[node]:
            continue

        for neighbor, weight in graph[node]:
            new_dist = dist + weight

            if new_dist < distances[neighbor]:
                distances[neighbor] = new_dist
                previous[neighbor] = node

                heapq.heappush(
                    queue, (new_dist, neighbor)
                )

    return distances, previous

def restore_path(previous, start, finish):
    path = []
    current = finish

    while current is not None:
        path.append(current)

        if current == start:
            return path[::-1]

        current = previous[current]

    return []