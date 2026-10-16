"""Two multi-source Dijkstra searches for the whole city, rather than one per house."""
from heapq import heappop,heappush
from math import hypot,inf
from .geo import NodeIndex

PARK_RADIUS = 500  # метров по дорожкам

def calculate_metrics(state,radius=500):
    nodes={n['id']:n for n in state['nodes']};graph={n:{} for n in nodes}
    for e in state['edges']:
        if not e['closed']:
            a,b=e['a'],e['b'];length=e.get('length') or hypot(nodes[a]['x']-nodes[b]['x'],nodes[a]['y']-nodes[b]['y'])
            graph[a][b]=graph[b][a]=length
    spatial=None
    anchors={}
    for obj in state['objects']:
        if obj.get('node_id') in nodes:anchors[obj['id']]=(obj['node_id'],obj.get('approach') or 0)
        else:
            if spatial is None:spatial=NodeIndex(state['nodes'])
            anchors[obj['id']]=spatial.nearest(obj['x'],obj['y'])
    def search(kind):
        distances={};parents={};targets={};queue=[]
        for obj in state['objects']:
            if obj['kind']!=kind:continue
            node,approach=anchors[obj['id']]
            if (approach,obj['id'])<(distances.get(node,inf),targets.get(node,'~')):
                distances[node]=approach;targets[node]=obj['id'];parents[node]=None;heappush(queue,(approach,node,obj['id']))
        while queue:
            distance,node,target=heappop(queue)
            if distance!=distances[node] or targets[node]!=target:continue
            for neighbor,weight in graph[node].items():
                candidate=distance+weight
                if (candidate,target)<(distances.get(neighbor,inf),targets.get(neighbor,'~')):
                    distances[neighbor]=candidate;targets[neighbor]=target;parents[neighbor]=node;heappush(queue,(candidate,neighbor,target))
        return distances,parents,targets
    stop_search,park_search=search('stop'),search('park')
    def route(home,search):
        node,approach=anchors[home['id']];distances,parents,targets=search
        if node not in distances:return None,[],None
        length=approach+distances[node];path=[];target=targets[node]
        while node is not None:path.append(node);node=parents[node]
        return length,path,target
    rows=[]
    for home in (o for o in state['objects'] if o['kind']=='home'):
        stop,sp,st=route(home,stop_search);park,pp,pt=route(home,park_search)
        # Geometry is already in the map response; analytics rows need no polygon copy.
        row={k:v for k,v in home.items() if k!='geom'}
        rows.append(dict(row,stop_distance=round(stop,1) if stop is not None else None,park_distance=round(park,1) if park is not None else None,
                         stop_path=sp,park_path=pp,stop_target=st,park_target=pt,park_access=park is not None and park<=radius))
    reachable=[r['stop_distance'] for r in rows if r['stop_distance'] is not None]
    total=sum(r['residents'] for r in rows);accessible=sum(r['residents'] for r in rows if r['park_access'])
    # Unknown OSM occupancy is not measured load; only populated capacity records contribute.
    facilities=[o for o in state['objects'] if o['kind'] not in {'home','building'}]
    capacity=sum(o['capacity'] for o in facilities);load=sum(o['load'] for o in facilities)
    return dict(average_stop=round(sum(reachable)/len(reachable),1) if reachable else None,park_percent=round(100*accessible/total,1) if total else 0,
                accessible_residents=accessible,total_residents=total,unreachable_homes=len(rows)-len(reachable),home_count=len(rows),
                utilization=round(100*load/capacity,1) if capacity else 0,overloaded=sum(o['load']>o['capacity'] for o in facilities),radius=radius,rows=rows)
