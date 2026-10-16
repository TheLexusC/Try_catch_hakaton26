"""Live city geometry, accounts and moderated changes in PostgreSQL."""
import os,sqlite3
from contextlib import contextmanager
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from dotenv import load_dotenv
from .seed import DISTRICT,seed_state
from .geo import NodeIndex
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
    row=db.execute('SELECT version FROM districts WHERE id=%s FOR '+('UPDATE' if write else 'SHARE'),(DISTRICT,)).fetchone()
    state={'version':row['version']}
    for table in ('nodes','edges','objects'):
        state[table]=[dict(r) for r in db.execute(f'SELECT * FROM {table} WHERE district_id=%s ORDER BY id',(DISTRICT,)).fetchall()]
        for item in state[table]:item.pop('district_id')
    state['demolished']=[dict(r) for r in db.execute('SELECT id,name,geom FROM demolitions WHERE district_id=%s',(DISTRICT,)).fetchall()]
    return state


def write_state(db,state):
    """Bulk seed only; approvals update a single record, never rebuild the city."""
    for table in ('edges','objects','nodes','map_context','demolitions'):db.execute(f'DELETE FROM {table} WHERE district_id=%s',(DISTRICT,))
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
        fields=('id','name','kind','x','y','residents','capacity','load','source','node_id','approach')
        db.execute(f'INSERT INTO objects(district_id,{",".join(fields)}) VALUES({",".join(["%s"]*(len(fields)+1))})',(DISTRICT,*(obj[k] for k in fields)))
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
    elif entity=='object' and op=='add':
        if values.get('kind') not in {'stop','park'}:raise PermissionError('Жители могут предлагать только новые остановки и зелёные зоны')
        if set(values)-{'name','kind','x','y'}:raise PermissionError('Население, нагрузка и вместимость недоступны для изменения жителем')
        if not {'name','kind','x','y'}<=values.keys():raise ValueError('Укажите тип, название и место на карте')
        if any(o['id']==target for o in state['objects']):raise ValueError('Такой объект уже существует')
        if not (0<=values['x']<=20000 and 0<=values['y']<=20000):raise ValueError('Координаты вне модели города')
        if any(o['kind']==values['kind'] and abs(o['x']-values['x'])<1 and abs(o['y']-values['y'])<1 for o in state['objects']):raise ValueError('Такой объект уже есть в этом месте')
        anchor,approach=NodeIndex(state['nodes']).nearest(values['x'],values['y'])
        result['objects'].append(dict(values,id=target,residents=0,capacity=100,load=0,geom=None,source='proposal',node_id=anchor,approach=round(approach,2)))
    elif entity=='edge' and op=='update':
        if set(values)!={'closed'}:raise PermissionError('Для дорожки разрешено только предложить открытие или перекрытие')
        edge=next((e for e in state['edges'] if e['id']==target),None)
        if edge is None:raise ValueError('Дорожка не существует')
        if edge['closed']==values['closed']:raise ValueError('Дорожка уже в этом состоянии')
        result['edges']=[dict(e,closed=values['closed']) if e['id']==target else e for e in state['edges']]
    else:raise PermissionError('Перемещение зданий, редактирование их параметров и изменение узлов недоступны жителям')
    return result
