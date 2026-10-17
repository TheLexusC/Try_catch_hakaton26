"""Extract green areas and car parks from OSM XML without replacing the city.
Usage: .venv/bin/python scripts/import_amenities.py /path/to/osm-extracts
Only geometry, public feature names and facility capacity are retained.
"""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from shapely.geometry import LineString, Point, Polygon, box, mapping
from shapely.ops import polygonize, unary_union
from shapely import make_valid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.geo import project, NodeIndex

BBOX=(36.56,55.065,36.68,55.155)
GREEN_LAND={'grass','forest','meadow','recreation_ground','village_green'}

def classify(tags):
    if tags.get('amenity')=='parking':return 'parking'
    # Parks already exist as a separate category; do not count them twice.
    if tags.get('leisure')=='park':return None
    if tags.get('landuse') in GREEN_LAND or tags.get('natural')=='wood' or tags.get('leisure')=='garden':return 'greenery'
    return None

def polygons(geometry):
    if geometry.geom_type=='Polygon':return [geometry]
    return [p for child in getattr(geometry,'geoms',[]) for p in polygons(child)]

def build(directory, nodes):
    raw={};ways={};relations={}
    for path in sorted(Path(directory).glob('*.osm')):
        for element in ET.parse(path).getroot():
            if element.tag not in {'node','way','relation'}:continue
            tags={v.get('k'):v.get('v') for v in element.findall('tag')}
            if element.tag=='node':raw[element.get('id')]=(float(element.get('lon')),float(element.get('lat')),tags)
            elif element.tag=='way':ways[element.get('id')]=([n.get('ref') for n in element.findall('nd')],tags)
            else:relations[element.get('id')]=([(m.get('ref'),m.get('role')) for m in element.findall('member') if m.get('type')=='way'],tags)
    def way_line(wid):
        refs=ways[wid][0]
        if any(n not in raw for n in refs) or len(refs)<2:return None
        return LineString([raw[n][:2] for n in refs])
    features=[];members=set();skipped=0;bounds=box(*BBOX)
    def add(typ,oid,tags,geom):
        nonlocal skipped
        if geom is None:skipped+=1;return
        try:
            geom=make_valid(geom).intersection(bounds)
            parts=polygons(geom)
            if not parts:skipped+=1;return
            geom=unary_union(parts)
            if geom.is_empty:skipped+=1;return
            center=geom.centroid
            if not geom.covers(center):center=geom.representative_point()
            features.append((typ,oid,tags,geom,center))
        except (ValueError,TypeError):skipped+=1
    for rid,(parts,tags) in relations.items():
        if not classify(tags) or tags.get('type')!='multipolygon':continue
        outer=[];inner=[]
        for wid,role in parts:
            line=way_line(wid) if wid in ways else None
            if line is not None:(inner if role=='inner' else outer).append(line)
        shells=list(polygonize(unary_union(outer))) if outer else []
        if not shells:skipped+=1;continue
        geom=unary_union(shells)
        if inner:geom=geom.difference(unary_union(list(polygonize(unary_union(inner)))))
        before=len(features);add('r',rid,tags,geom)
        if len(features)>before:members.update(wid for wid,_ in parts)
    for wid,(refs,tags) in ways.items():
        if wid in members or not classify(tags):continue
        line=way_line(wid)
        add('w',wid,tags,Polygon(line.coords) if line is not None and line.is_ring else None)
    areas=[(classify(tags),geom) for _,_,tags,geom,_ in features]
    for nid,(lon,lat,tags) in raw.items():
        if classify(tags)!='parking' or not bounds.covers(Point(lon,lat)):continue
        p=Point(lon,lat)
        if any(kind=='parking' and g.covers(p) for kind,g in areas):continue
        features.append(('n',nid,tags,None,p))
    index=NodeIndex(nodes);objects=[]
    for typ,oid,tags,geom,center in features:
        kind=classify(tags);x,y=project(center.x,center.y);anchor,distance=index.nearest(x,y)
        label='Парковка' if kind=='parking' else 'Газон' if tags.get('landuse')=='grass' else 'Лесной участок' if tags.get('natural')=='wood' or tags.get('landuse')=='forest' else 'Озеленённая зона'
        name=tags.get('name') or ', '.join(filter(None,[tags.get('addr:street'),tags.get('addr:housenumber')])) or f'{label} · OSM {typ}{oid}'
        capacity=tags.get('capacity','')
        objects.append(dict(id=f'osm_{kind}_{typ}{oid}',name=name[:80],kind=kind,x=x,y=y,residents=0,capacity=max(1,min(100000,int(capacity))) if capacity.isdigit() else 100,load=0,geom=mapping(geom) if geom is not None else None,source='osm',node_id=anchor,approach=round(distance,2)))
    return dict(objects=objects,source=dict(name='OpenStreetMap',license='ODbL 1.0',url='https://www.openstreetmap.org/copyright',bbox=BBOX,snapshot_date='2026-10-16',counts=dict(Counter(o['kind'] for o in objects)),skipped_incomplete=skipped))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory');parser.add_argument('--output',default='db/obninsk.amenities.json.gz');args=parser.parse_args()
    with gzip.open(Path(__file__).resolve().parents[1]/'db/obninsk.osm.json.gz','rt',encoding='utf8') as file:nodes=json.load(file)['nodes']
    result=build(args.directory,nodes)
    with gzip.open(args.output,'wt',encoding='utf8') as file:json.dump(result,file,ensure_ascii=False,separators=(',',':'))
    print(result['source'])
