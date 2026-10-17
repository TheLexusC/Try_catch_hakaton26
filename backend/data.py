"""Live city geometry, accounts and moderated changes in PostgreSQL."""
import os,sqlite3
from contextlib import contextmanager
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from dotenv import load_dotenv
from .seed import DISTRICT,seed_state
from .geo import NodeIndex, unproject
from math import hypot
ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')
DATABASE=os.getenv('DATABASE_URL','postgresql://obninsk:obninsk_local@127.0.0.1:55432/obninsk2040')
METADATA=dict(name='Обнинск · OpenStreetMap',width=20000,height=20000,
    source={'name':'© OpenStreetMap contributors','url':'https://www.openstreetmap.org/copyright','license':'ODbL 1.0','date':'2026-10-16'},
    notes='Реальные контуры и расположение объектов OpenStreetMap в охвате 36.56–36.68°E, 55.065–55.155°N. Полнота зависит от OSM; охват включает прилегающие территории. Население оценено по площади, этажности и числу квартир, не является официальной статистикой. Нагрузка не измерена: ноль означает отсутствие загруженных данных. Подходы к сети расчётные; закрытые территории исключены из маршрутизации.')

@contextmanager
def connect(dsn=DATABASE):
    with psycopg.connect(dsn,row_factory=dict_row,connect_timeout=5) as db:yield db


def initialize(dsn=DATABASE):
    with connect(dsn) as db:
        db.execute('SELECT pg_advisory_xact_lock(204026)')
        db.execute((ROOT/'db/schema.sql').read_text())
        inserted=db.execute('INSERT INTO districts(id,name) VALUES(%s,%s) ON CONFLICT DO NOTHING RETURNING id',(DISTRICT,METADATA['name'])).fetchone()
        if inserted:
            write_state(db,seed_state())
            if dsn==DATABASE:migrate_legacy_users(db)


def migrate_legacy_users(db):
    legacy=ROOT/'backend/instance/city.sqlite3'
    if legacy.exists():
        with sqlite3.connect(legacy.as_uri()+'?mode=ro',uri=True) as old:rows=old.execute('SELECT id,email,name,password_hash,role,created_at FROM users').fetchall()
        with db.cursor() as cursor:cursor.executemany('INSERT INTO users(id,email,name,password_hash,role,created_at) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',rows)


def read_state(db,write=False):
    row=db.execute('SELECT version,demolition_limit FROM districts WHERE id=%s FOR '+('UPDATE' if write else 'SHARE'),(DISTRICT,)).fetchone()
    state={'version':row['version'],'demolition_policy':{'limit':row['demolition_limit']}}
    for table in ('nodes','edges','objects'):
        state[table]=[dict(r) for r in db.execute(f'SELECT * FROM {table} WHERE district_id=%s ORDER BY id',(DISTRICT,)).fetchall()]
        for item in state[table]:item.pop('district_id')
    state['areas']=[{k:v for k,v in dict(r).items() if k!='district_id'} for r in db.execute('SELECT * FROM planning_areas WHERE district_id=%s ORDER BY id',(DISTRICT,)).fetchall()]
    state['demolished']=[dict(r) for r in db.execute('SELECT id,name,geom FROM demolitions WHERE district_id=%s',(DISTRICT,)).fetchall()]
    return state


def write_state(db,state):
    """Bulk seed only; approvals update a single record, never rebuild the city."""
    for table in ('planning_areas','edges','objects','nodes','map_context','demolitions'):db.execute(f'DELETE FROM {table} WHERE district_id=%s',(DISTRICT,))
    columns={'nodes':('id','name','x','y'),'edges':('id','a','b','closed','capacity','load','geom','length'),
             'objects':('id','name','kind','x','y','residents','capacity','load','geom','source','node_id','approach'),
             'map_context':('id','kind','name','geometry')}
    for table,fields in columns.items():
        rows=state.get('context' if table=='map_context' else table,[])
        with db.cursor().copy(f'COPY {table}(district_id,{",".join(fields)}) FROM STDIN') as copy:
            for row in rows:
                copy.write_row((DISTRICT,*(Jsonb(row.get(k)) if k in {'geom','geometry'} and row.get(k) is not None else row.get(k) for k in fields)))
    db.execute('UPDATE districts SET version=%s WHERE id=%s',(state['version'],DISTRICT))


def save_change(db,state,action):
    entity,op,target=action['entity'],action['operation'],action['id']
    if entity=='road':
        existing={r['id'] for r in db.execute('SELECT id FROM nodes WHERE district_id=%s',(DISTRICT,)).fetchall()}
        for node in state['nodes']:
            if node['id'].startswith(target+'_n') and node['id'] not in existing:
                db.execute('INSERT INTO nodes(id,district_id,name,x,y) VALUES(%s,%s,%s,%s,%s)',(node['id'],DISTRICT,node['name'],node['x'],node['y']))
        for edge in state['edges']:
            if edge['id'].startswith(target+'_e'):
                db.execute('INSERT INTO edges(id,district_id,a,b,closed,capacity,load,geom,length) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(edge['id'],DISTRICT,edge['a'],edge['b'],False,500,0,Jsonb(edge['geom']),edge['length']))
        db.execute('UPDATE districts SET version=%s WHERE id=%s',(state['version'],DISTRICT));return
    if entity=='area':
        area=next(a for a in state['areas'] if a['id']==target)
        fields=('id','name','x','y','width','height','geom')
        db.execute(f'INSERT INTO planning_areas(district_id,{",".join(fields)}) VALUES({",".join(["%s"]*8)})',(DISTRICT,*(Jsonb(area[k]) if k=='geom' else area[k] for k in fields)))
        db.execute('UPDATE districts SET version=%s WHERE id=%s',(state['version'],DISTRICT));return
    table='objects' if entity=='object' else 'edges'
    if op=='delete':
        deleted=next((o for o in state.get('demolished',[]) if o['id']==target),None)
        if deleted:db.execute('INSERT INTO demolitions(district_id,id,name,geom) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',(DISTRICT,target,deleted['name'],Jsonb(deleted['geom'])))
        db.execute(f'DELETE FROM {table} WHERE id=%s AND district_id=%s',(target,DISTRICT))
    elif entity=='object' and op=='update':
        obj=next(o for o in state['objects'] if o['id']==target)
        db.execute('UPDATE objects SET x=%s,y=%s,geom=NULL,node_id=%s,approach=%s WHERE id=%s AND district_id=%s',(obj['x'],obj['y'],obj['node_id'],obj['approach'],target,DISTRICT))
    elif entity=='edge':
        db.execute('UPDATE edges SET closed=%s WHERE id=%s AND district_id=%s',(action['values']['closed'],target,DISTRICT))
    else:
        obj=next(o for o in state['objects'] if o['id']==target)
        fields=('id','name','kind','x','y','residents','capacity','load','source','node_id','approach','geom')
        db.execute(f'INSERT INTO objects(district_id,{",".join(fields)}) VALUES({",".join(["%s"]*(len(fields)+1))})',(DISTRICT,*(Jsonb(obj[k]) if k=='geom' and obj[k] is not None else obj[k] for k in fields)))
    db.execute('UPDATE districts SET version=%s WHERE id=%s',(state['version'],DISTRICT))


def apply_action(state,action):
    """Resident proposals only. A moderator reviews but gets no building-edit bypass."""
    entity,op,target=action['entity'],action['operation'],action['id'];values={k:v for k,v in action.get('values',{}).items() if v is not None}
    result={**state,'objects':state['objects'][:],'edges':state['edges'][:]}
    if entity=='object' and op=='delete':
        if values:raise ValueError('Для заявки на снос не передавайте новые параметры')
        if not any(o['id']==target for o in state['objects']):raise ValueError('Нельзя предложить снос несуществующего объекта')
        deleted=next(o for o in state['objects'] if o['id']==target)
        if deleted.get('geom') and deleted['kind']!='park':result['demolished']=[*state.get('demolished',[]),{k:deleted[k] for k in ('id','name','geom')}]
        result['objects']=[o for o in state['objects'] if o['id']!=target]
    elif entity=='object' and op=='update':
        obj=next((o for o in state['objects'] if o['id']==target),None)
        if obj is None:raise ValueError('Остановка не существует')
        if obj['kind']!='stop':raise PermissionError('Перенос доступен только для остановок')
        if set(values)!={'x','y'}:raise PermissionError('При переносе остановки можно менять только её расположение')
        if not (0<=values['x']<=20000 and 0<=values['y']<=20000):raise ValueError('Координаты вне модели города')
        if abs(obj['x']-values['x'])<1 and abs(obj['y']-values['y'])<1:raise ValueError('Выберите новое место для остановки')
        if any(o['id']!=target and o['kind']=='stop' and abs(o['x']-values['x'])<1 and abs(o['y']-values['y'])<1 for o in state['objects']):raise ValueError('В этом месте уже есть остановка')
        anchor,approach=NodeIndex(state['nodes']).nearest(values['x'],values['y'])
        result['objects']=[dict(o,**values,geom=None,node_id=anchor,approach=round(approach,2)) if o['id']==target else o for o in state['objects']]
    elif entity=='area' and op=='add':
        if any(a['id']==target for a in state.get('areas',[])):raise ValueError('Такой район уже существует')
        if 'points' in values:
            if set(values)!={'name','points'}:raise ValueError('Для многоугольника укажите название и вершины')
            points=values['points'];geom=polygon(points)
            xs=[p['x'] for p in points];ys=[p['y'] for p in points]
            area=dict(name=values['name'],x=(min(xs)+max(xs))/2,y=(min(ys)+max(ys))/2,width=max(xs)-min(xs),height=max(ys)-min(ys))
        else:
            if set(values)!={'name','x','y','width','height'}:raise ValueError('Укажите название, центр и размеры района')
            geom=rectangle(values['x'],values['y'],values['width'],values['height']);area=values
        result['areas']=[*state.get('areas',[]),dict(area,id=target,geom=geom)]
    elif entity=='road' and op=='add':
        if set(values)!={'name','points'}:raise ValueError('Укажите название и точки дорожки')
        points=values['points']
        if len(target)>40:raise ValueError('Слишком длинный идентификатор дорожки')
        if any(e['id'].startswith(target+'_e') for e in state['edges']):raise ValueError('Такая дорожка уже существует')
        if any(hypot(a['x']-b['x'],a['y']-b['y'])<1 for a,b in zip(points,points[1:])):raise ValueError('Точки дорожки должны различаться')
        index=NodeIndex(state['nodes']);nodes=[dict(id=f'{target}_n{i}',name=values['name'],**point) for i,point in enumerate(points)]
        result['nodes']=[*state['nodes'],*nodes]
        start=index.nearest(points[0]['x'],points[0]['y'])[0];end=index.nearest(points[-1]['x'],points[-1]['y'])[0]
        lookup={n['id']:n for n in result['nodes']};chain=[start,*[n['id'] for n in nodes],end]
        for i,(a,b) in enumerate(zip(chain,chain[1:])):
            first,last=lookup[a],lookup[b];length=hypot(first['x']-last['x'],first['y']-last['y'])
            result['edges'].append(dict(id=f'{target}_e{i}',a=a,b=b,closed=False,capacity=500,load=0,length=max(.01,round(length,2)),geom={'type':'LineString','coordinates':[unproject(first['x'],first['y']),unproject(last['x'],last['y'])]}))
    elif entity=='object' and op=='add':
        kind=values.get('kind')
        if kind not in {'home','stop','park','school','clinic','shop','parking','greenery'}:raise PermissionError('Недопустимый тип нового объекта')
        allowed={'name','kind','x','y'}|({'width','height','residents','points','rotation'} if kind=='home' else set())
        if set(values)-allowed:raise PermissionError('Нельзя задавать дополнительные параметры существующих объектов')
        if not {'name','kind','x','y'}<=values.keys():raise ValueError('Укажите тип, название и место на карте')
        if kind=='home' and not {'width','height','residents'}<=values.keys():raise ValueError('Для нового дома укажите размеры и число условных жителей')
        if any(o['id']==target for o in state['objects']):raise ValueError('Такой объект уже существует')
        if not (0<=values['x']<=20000 and 0<=values['y']<=20000):raise ValueError('Координаты вне модели города')
        if any(o['kind']==kind and abs(o['x']-values['x'])<1 and abs(o['y']-values['y'])<1 for o in state['objects']):raise ValueError('Такой объект уже есть в этом месте')
        anchor,approach=NodeIndex(state['nodes']).nearest(values['x'],values['y'])
        geom=None
        if kind=='home':
            if not(5<=values['width']<=200 and 5<=values['height']<=200):raise ValueError('Размеры дома — от 5 до 200 м')
            geom=polygon(values['points']) if values.get('points') else rectangle(values['x'],values['y'],values['width'],values['height'])
            if values.get('points'):
                from .layout import validate_footprint
                validate_footprint(geom,state)
        obj={k:values[k] for k in ('name','kind','x','y')};residents=values.get('residents',0)
        result['objects'].append(dict(obj,id=target,residents=residents,capacity=max(100,residents),load=0,geom=geom,source='proposal',node_id=anchor,approach=round(approach,2)))
    elif entity=='edge' and op=='update':
        if set(values)!={'closed'}:raise PermissionError('Для дорожки разрешено только предложить открытие или перекрытие')
        edge=next((e for e in state['edges'] if e['id']==target),None)
        if edge is None:raise ValueError('Дорожка не существует')
        if edge['closed']==values['closed']:raise ValueError('Дорожка уже в этом состоянии')
        result['edges']=[dict(e,closed=values['closed']) if e['id']==target else e for e in state['edges']]
    else:raise PermissionError('Перемещение зданий, редактирование их параметров и изменение узлов недоступны жителям')
    return result


def rectangle(x,y,width,height):
    if not (5<=width<=4000 and 5<=height<=4000):raise ValueError('Размеры должны быть от 5 до 4000 м')
    coords=[(x-width/2,y-height/2),(x+width/2,y-height/2),(x+width/2,y+height/2),(x-width/2,y+height/2)]
    if any(not(0<=a<=20000 and 0<=b<=20000) for a,b in coords):raise ValueError('Контур выходит за пределы модели города')
    return {'type':'Polygon','coordinates':[[unproject(a,b) for a,b in [*coords,coords[0]]]]}


def polygon(points):
    if len(points)<3:raise ValueError('Для района нужно не меньше трёх вершин')
    if len({(p['x'],p['y']) for p in points})!=len(points):raise ValueError('Вершины района не должны повторяться')
    area=abs(sum(a['x']*b['y']-b['x']*a['y'] for a,b in zip(points,points[1:]+points[:1])))/2
    if area<25:raise ValueError('Площадь района должна быть не меньше 25 м²')
    def cross(a,b,c):return (b['x']-a['x'])*(c['y']-a['y'])-(b['y']-a['y'])*(c['x']-a['x'])
    edges=list(zip(points,points[1:]+points[:1]))
    for i,(a,b) in enumerate(edges):
        for j,(c,d) in enumerate(edges):
            if j<=i or j==i+1 or (i==0 and j==len(edges)-1):continue
            if cross(a,b,c)*cross(a,b,d)<=0 and cross(c,d,a)*cross(c,d,b)<=0 and max(min(a['x'],b['x']),min(c['x'],d['x']))<=min(max(a['x'],b['x']),max(c['x'],d['x'])) and max(min(a['y'],b['y']),min(c['y'],d['y']))<=min(max(a['y'],b['y']),max(c['y'],d['y'])):raise ValueError('Граница района пересекает сама себя')
    return {'type':'Polygon','coordinates':[[unproject(p['x'],p['y']) for p in [*points,points[0]]]]}
