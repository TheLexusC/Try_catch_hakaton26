"""Attach proposed objects to points along paths, not just their distant endpoints."""
from shapely.geometry import LineString,Point
from shapely.strtree import STRtree
from .geo import project

def snap_proposals(state,nodes,graph,anchors):
    proposed=[o for o in state['objects'] if o.get('source')=='proposal']
    if not proposed:return set()
    edges=[];lines=[]
    for edge in sorted(state['edges'],key=lambda e:e['id']):
        if edge['closed']:continue
        if edge.get('geom'):
            coords=[project(*p[:2]) for p in edge['geom']['coordinates']]
        else:
            a,b=nodes[edge['a']],nodes[edge['b']];coords=[(a['x'],a['y']),(b['x'],b['y'])]
        # The geometry may be stored in either orientation.
        a=nodes[edge['a']]
        if (coords[0][0]-a['x'])**2+(coords[0][1]-a['y'])**2>(coords[-1][0]-a['x'])**2+(coords[-1][1]-a['y'])**2:coords=coords[::-1]
        line=LineString(coords)
        if line.length>0:edges.append(edge);lines.append(line)
    if not lines:return set()
    tree=STRtree(lines);groups={};virtual=set()
    for obj in proposed:
        point=Point(obj['x'],obj['y']);idx=int(tree.nearest(point));line=lines[idx]
        distance=line.project(point);position=line.interpolate(distance);key='_snap_'+obj['id']
        nodes[key]={'id':key,'x':position.x,'y':position.y};graph[key]={};virtual.add(key)
        anchors[obj['id']]=(key,point.distance(position))
        groups.setdefault(idx,[]).append((distance/line.length,key))
    for idx,items in groups.items():
        edge=edges[idx];a,b=edge['a'],edge['b'];length=graph[a].get(b,edge.get('length') or lines[idx].length)
        graph[a].pop(b,None);graph[b].pop(a,None)
        chain=[(0,a),*sorted(items),(1,b)]
        for (p,n),(q,m) in zip(chain,chain[1:]):graph[n][m]=graph[m][n]=max(0,(q-p)*length)
    return virtual
