"""Fit proposed footprints to the district, streets, water and existing buildings."""
from math import atan2,degrees,hypot
from shapely.geometry import Polygon,LineString,shape,mapping,box,Point
from shapely.affinity import rotate
from shapely.ops import transform,unary_union
from .geo import project,unproject,X_SCALE,ORIGIN_LON,ORIGIN_LAT,NodeIndex

def local_geometry(geom):
    return transform(lambda x,y,z=None:((x-ORIGIN_LON)*X_SCALE,(y-ORIGIN_LAT)*111320),shape(geom))

def fit_layout(state,houses,boundary,roads,context):
    district=Polygon([(p['x'],p['y']) for p in boundary]) if boundary else box(0,0,20000,20000)
    if not district.is_valid or district.area<25:raise ValueError('Нужна корректная граница района без самопересечений')
    fitted=[]
    for home in houses:
        x,y,w,h=home['x'],home['y'],home['width'],home['height'];near=box(x-300,y-300,x+300,y+300)
        obstacles=[];directions=[]
        for obj in state['objects']:
            if obj.get('geom') and obj['kind'] not in {'park','greenery'} and abs(obj['x']-x)<600 and abs(obj['y']-y)<600:
                obstacles.append(local_geometry(obj['geom']).buffer(2))
        for obj in fitted:obstacles.append(Polygon([(p['x'],p['y']) for p in obj['points']]).buffer(2))
        lines=[]
        for feature in context:
            geom=feature['geometry'];kind=feature['kind']
            if not geom:continue
            coords=geom.get('coordinates',[])
            if geom['type']=='LineString' and kind=='road':
                pts=[project(*p[:2]) for p in coords]
                if pts and max(p[0] for p in pts)>=x-300 and min(p[0] for p in pts)<=x+300 and max(p[1] for p in pts)>=y-300 and min(p[1] for p in pts)<=y+300:lines.append(LineString(pts))
            elif kind=='water':
                water=local_geometry(geom)
                if water.intersects(near):obstacles.append(water.buffer(2))
        node_index=NodeIndex(state['nodes']);lookup={n['id']:n for n in state['nodes']}
        for road in roads:
            if len(road)<2:raise ValueError('Для дорожки нужно минимум две точки')
            start=lookup[node_index.nearest(road[0]['x'],road[0]['y'])[0]];end=lookup[node_index.nearest(road[-1]['x'],road[-1]['y'])[0]]
            lines.append(LineString([(p['x'],p['y']) for p in [start,*road,end]]))
        # Include approved project paths as well as the OSM street context.
        for edge in state['edges']:
            if '_e' in edge['id'] and edge.get('geom'):
                line=local_geometry(edge['geom'])
                if line.intersects(near):lines.append(line)
        for line in lines:
            if not line.intersects(near):continue
            obstacles.append(line.buffer(6))
            coords=list(line.coords)
            for a,b in zip(coords,coords[1:]):
                segment=LineString([a,b]);directions.append((segment.distance(Point(x,y)),degrees(atan2(b[1]-a[1],b[0]-a[0]))))
        forbidden=unary_union(obstacles) if obstacles else Polygon()
        base=box(x-w/2,y-h/2,x+w/2,y+h/2)
        preferred=min(directions)[1] if directions else 0
        best=None
        if home.get('points'):
            previous=Polygon([(p['x'],p['y']) for p in home['points']])
            if previous.is_valid and previous.area>=25 and district.buffer(.001).covers(previous) and previous.intersection(forbidden).area<.01:
                best=(previous.area,previous,home.get('rotation') or 0)
        preserved=best is not None
        for angle in [preferred,preferred+90,*range(0,180,15)]:
            if preserved:break
            candidate=rotate(base,angle,origin=(x,y)).intersection(district).difference(forbidden)
            parts=list(candidate.geoms) if candidate.geom_type in {'MultiPolygon','GeometryCollection'} else [candidate]
            for part in parts:
                if part.geom_type!='Polygon' or part.area<25:continue
                # Preserve holes instead of filling excluded roads/buildings back in.
                if part.interiors:continue
                score=part.area-.02*part.distance(Point(x,y))
                if best is None or score>best[0]+.01:best=(score,part,angle)
            if best and best[1].area>=w*h*.995:break
        if best is None or best[1].area<w*h*.2:raise ValueError(f"{home['name']}: мало свободного места. Уменьшите дом или выберите другую точку.")
        poly=best[1].simplify(.02,preserve_topology=True);center=poly.centroid
        if not poly.covers(center):center=poly.representative_point()
        points=[dict(x=round(a,4),y=round(b,4)) for a,b in list(poly.exterior.coords)[:-1]]
        if len(points)>60:raise ValueError('Слишком сложный контур. Выберите другое место.')
        fitted.append(dict(home,x=center.x,y=center.y,points=points,rotation=round(best[2]%180,1),area_m2=round(poly.area,1),trimmed=poly.area<w*h*.99,source='proposal',kind='home',geom={'type':'Polygon','coordinates':[[unproject(p['x'],p['y']) for p in [*points,points[0]]]]}))
    return fitted

def validate_footprint(geom,state):
    poly=local_geometry(geom)
    if not poly.is_valid or poly.area<24.9:raise ValueError('Некорректный контур дома')
    hull=list(poly.convex_hull.exterior.coords)[:-1];bounds=[]
    for a,b in zip(hull,hull[1:]+hull[:1]):
        length=hypot(b[0]-a[0],b[1]-a[1])
        if length<1e-8:continue
        ux,uy=(b[0]-a[0])/length,(b[1]-a[1])/length
        along=[x*ux+y*uy for x,y in hull];across=[-x*uy+y*ux for x,y in hull]
        w,h=max(along)-min(along),max(across)-min(across);bounds.append((w*h,w,h))
    if not bounds or max(min(bounds)[1:])>200.1:raise ValueError('Максимальные размеры дома — 200 × 200 м')
    for obj in state['objects']:
        if obj.get('geom') and obj['kind'] not in {'park','greenery'} and abs(obj['x']-poly.centroid.x)<600 and abs(obj['y']-poly.centroid.y)<600:
            if poly.intersection(local_geometry(obj['geom']).buffer(1.9)).area>.1:raise ValueError('Контур дома пересекает другое здание')
    for edge in state['edges']:
        if '_e' in edge['id'] and edge.get('geom') and poly.intersection(local_geometry(edge['geom']).buffer(5.9)).area>.1:raise ValueError('Контур дома пересекает проектную дорожку')
