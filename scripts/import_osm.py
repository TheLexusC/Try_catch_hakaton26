"""Convert OSM XML extracts into one compact, compressed PostgreSQL seed.
Usage: python scripts/import_osm.py /path/to/extracts --output db/obninsk.osm.json.gz
No contributor accounts or contact details are copied into the application.
"""
import argparse,gzip,json,sys,xml.etree.ElementTree as ET
from collections import defaultdict
from math import hypot
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.geo import project,NodeIndex

def tags(element):return {v.get('k'):v.get('v') for v in element.findall('tag')}
def build(directory):
    raw_nodes,ways,relations={},{},{}
    for file in sorted(Path(directory).glob('*.osm')):
        root=ET.parse(file).getroot()
        for n in root.findall('node'):raw_nodes[n.get('id')]={'lon':float(n.get('lon')),'lat':float(n.get('lat')),'tags':tags(n)}
        for w in root.findall('way'):ways[w.get('id')]={'refs':[v.get('ref') for v in w.findall('nd')],'tags':tags(w)}
        for r in root.findall('relation'):
            t=tags(r)
            if t.get('building'):relations[r.get('id')]={'tags':t,'members':[(m.get('ref'),m.get('role')) for m in r.findall('member') if m.get('type')=='way']}
    def coords(refs):return [[round(raw_nodes[n]['lon'],7),round(raw_nodes[n]['lat'],7)] for n in refs if n in raw_nodes]
    def rings(parts):
        parts=[p[:] for p in parts];result=[]
        while parts:
            chain=parts.pop()
            while chain and chain[0]!=chain[-1]:
                found=False
                for i,part in enumerate(parts):
                    if chain[-1] in (part[0],part[-1]):
                        if part[-1]==chain[-1]:part=part[::-1]
                        chain+=part[1:];parts.pop(i);found=True;break
                if not found:break
            if len(chain)>=4 and chain[0]==chain[-1]:result.append(coords(chain))
        return result
    footprints=[];relation_ways=set()
    for rid,r in relations.items():
        outers=rings([ways[wid]['refs'] for wid,role in r['members'] if wid in ways and role!='inner'])
        inners=rings([ways[wid]['refs'] for wid,role in r['members'] if wid in ways and role=='inner'])
        if outers:
            geometry={'type':'Polygon','coordinates':[outers[0],*inners]} if len(outers)==1 else {'type':'MultiPolygon','coordinates':[[outer] for outer in outers]}
            footprints.append(('r'+rid,r['tags'],geometry));relation_ways.update(w for w,_ in r['members'])
    graph=defaultdict(dict);context=[];parks=[]
    allowed={'footway','path','pedestrian','steps','living_street','service','residential','unclassified','track'}
    for wid,w in ways.items():
        t=w['tags'];refs=[n for n in w['refs'] if n in raw_nodes];geo=coords(refs)
        if len(geo)<2:continue
        if t.get('building') and wid not in relation_ways and refs[0]==refs[-1]:footprints.append(('b'+wid,t,{'type':'Polygon','coordinates':[geo]}))
        if t.get('highway'):
            context.append({'id':'road'+wid,'kind':'road','name':t.get('name',''),'geometry':{'type':'LineString','coordinates':geo}})
        elif refs[0]==refs[-1] and (t.get('leisure')=='park' or t.get('landuse') in {'forest','grass','meadow','recreation_ground'} or t.get('natural') in {'water','wood'}):
            context.append({'id':'land'+wid,'kind':'water' if t.get('natural')=='water' else 'green','name':t.get('name',''),'geometry':{'type':'Polygon','coordinates':[geo]}})
        if t.get('leisure')=='park' and refs[0]==refs[-1]:parks.append((wid,t,geo))
        if t.get('highway') not in allowed or t.get('access') in {'private','no'} or t.get('foot')=='no':continue
        for a,b in zip(refs,refs[1:]):
            pa=project(raw_nodes[a]['lon'],raw_nodes[a]['lat']);pb=project(raw_nodes[b]['lon'],raw_nodes[b]['lat']);length=hypot(pa[0]-pb[0],pa[1]-pb[1])
            if a!=b and length>.1 and all(36.56<=raw_nodes[n]['lon']<=36.68 and 55.065<=raw_nodes[n]['lat']<=55.155 for n in (a,b)):graph[a][b]=graph[b][a]=length
    # Keep junctions, plus shape points at roughly 60 m. Polylines preserve bends.
    junctions={n for n in graph if len(graph[n])!=2};visited=set();edges=[];kept=set()
    for start in sorted(graph):
        if start not in junctions and any(frozenset((start,n)) in visited for n in graph[start]):continue
        if start not in junctions and any(n in junctions for n in graph[start]):continue
        for nxt in list(graph[start]):
            if frozenset((start,nxt)) in visited:continue
            current,previous=nxt,start;path=[start];length=0;anchor=start
            while True:
                visited.add(frozenset((previous,current)));length+=graph[previous][current];path.append(current)
                if current in junctions or length>=60 or current==start:
                    if anchor!=current:
                        a,b=sorted(('n'+anchor,'n'+current));edges.append(dict(id='osme'+str(len(edges)+1),a=a,b=b,length=round(length,2),geom={'type':'LineString','coordinates':coords(path)},closed=False,capacity=500,load=0));kept.update((anchor,current))
                    anchor=current;path=[current];length=0
                if current in junctions or current==start:break
                candidates=[n for n in graph[current] if n!=previous and frozenset((current,n)) not in visited]
                if not candidates:break
                previous,current=current,candidates[0]
    # Different OSM ways may represent parallel routes; retain the shortest.
    unique={}
    for e in edges:
        pair=(e['a'],e['b'])
        if pair not in unique or e['length']<unique[pair]['length']:unique[pair]=e
    edges=list(unique.values());used={e[k][1:] for e in edges for k in ('a','b')};nodes=[]
    for nid in sorted(used):
        x,y=project(raw_nodes[nid]['lon'],raw_nodes[nid]['lat']);nodes.append(dict(id='n'+nid,name='Узел '+nid,x=x,y=y))
    index=NodeIndex(nodes);objects=[]
    def add_object(oid,name,kind,lon,lat,geom=None,residents=0):
        x,y=project(lon,lat)
        if not (36.56<=lon<=36.68 and 55.065<=lat<=55.155):return
        anchor,approach=index.nearest(x,y)
        objects.append(dict(id=oid,name=name[:80],kind=kind,x=x,y=y,residents=residents,capacity=max(1,residents) if kind=='home' else 100,load=residents if kind=='home' else 0,geom=geom,source='osm',node_id=anchor,approach=round(approach,2)))
    homes={'apartments','residential','house','detached','semidetached_house','terrace','dormitory','bungalow'}
    for oid,t,geom in footprints:
        ring=geom['coordinates'][0] if geom['type']=='Polygon' else geom['coordinates'][0][0];pts=ring[:-1];lon=sum(p[0] for p in pts)/len(pts);lat=sum(p[1] for p in pts)/len(pts)
        amenity=t.get('amenity',t.get('building'))
        kind='home' if t.get('building') in homes else 'school' if amenity in {'school','kindergarten','college','university'} else 'clinic' if amenity in {'hospital','clinic','doctors'} else 'shop' if t.get('shop') or t.get('building')=='retail' else 'building'
        address=', '.join(filter(None,[t.get('addr:street'),t.get('addr:housenumber')]))
        name=address or t.get('name') or ('Жилой дом' if kind=='home' else 'Здание')+' · '+oid
        xy=[project(*p) for p in ring];area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(xy,xy[1:])))/2
        try:levels=max(1,min(40,float(t.get('building:levels',1))));flats=float(t.get('building:flats',0))
        except ValueError:levels,flats=1,0
        residents=max(1,int(flats*2.2 if flats else area*levels/35)) if kind=='home' else 0
        add_object(oid,name,kind,lon,lat,geom,residents)
    for nid,n in raw_nodes.items():
        if n['tags'].get('highway')=='bus_stop':add_object('s'+nid,n['tags'].get('name','Остановка'),'stop',n['lon'],n['lat'])
    for wid,t,ring in parks:
        pts=ring[:-1];add_object('p'+wid,t.get('name','Зелёная зона'),'park',sum(p[0] for p in pts)/len(pts),sum(p[1] for p in pts)/len(pts),{'type':'Polygon','coordinates':[ring]})
    return dict(version=0,nodes=nodes,edges=edges,objects=objects,context=context,source={'name':'© OpenStreetMap contributors','url':'https://www.openstreetmap.org/copyright','license':'ODbL 1.0','bbox':[36.56,55.065,36.68,55.155],'date':'2026-10-16','building_count':sum(o['geom'] is not None and o['kind']!='park' for o in objects)})

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory');parser.add_argument('--output',default='db/obninsk.osm.json.gz');a=parser.parse_args()
    result=build(a.directory)
    with gzip.open(a.output,'wt',encoding='utf8',compresslevel=9) as file:json.dump(result,file,ensure_ascii=False,separators=(',',':'))
    print({k:len(result[k]) for k in ['nodes','edges','objects','context']},'buildings',result['source']['building_count'])
