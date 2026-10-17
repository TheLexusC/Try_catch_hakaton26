import math
import pytest
from backend.graph import dijkstra,restore_path
from backend.demo_seed import seed_state
from backend.data import apply_action
from backend.metrics import calculate_metrics


def test_dijkstra_indirect_shortest():
    d,p=dijkstra({'a':{'b':10,'c':2},'b':{'a':10,'c':3},'c':{'a':2,'b':3}},'a')
    assert d['b']==5 and restore_path(p,'a','b')==['a','c','b']


def test_multisource_agrees_with_independent_per_home_search():
    s=seed_state();m=calculate_metrics(s);nodes={n['id']:n for n in s['nodes']};g={n:{} for n in nodes}
    def distance(a,b):return math.hypot(a['x']-b['x'],a['y']-b['y'])
    anchors={o['id']:min(nodes,key=lambda n:(distance(o,nodes[n]),n)) for o in s['objects']}
    for e in s['edges']:g[e['a']][e['b']]=g[e['b']][e['a']]=distance(nodes[e['a']],nodes[e['b']])
    for row in m['rows']:
        d,_=dijkstra(g,anchors[row['id']])
        for kind in ['stop','park']:
            best=min(distance(row,nodes[anchors[row['id']]])+d[anchors[o['id']]]+distance(o,nodes[anchors[o['id']]]) for o in s['objects'] if o['kind']==kind)
            assert row[kind+'_distance']==round(best,1)


def test_missing_targets_and_population_are_defined():
    s=seed_state();s['objects']=[o for o in s['objects'] if o['kind']=='home'];m=calculate_metrics(s)
    assert m['average_stop'] is None and m['park_percent']==0 and m['unreachable_homes']==5
    s['objects']=[];m=calculate_metrics(s);assert m['home_count']==0 and m['total_residents']==0


@pytest.mark.parametrize('action',[
 dict(entity='object',operation='update',id='h1',values={'x':50}),
 dict(entity='object',operation='add',id='fake',values={'name':'Fake','kind':'home','x':50,'y':50,'capacity':999}),
 dict(entity='node',operation='delete',id='n1',values={}),
 dict(entity='edge',operation='update',id='e1',values={'capacity':100}),
])
def test_immutable_buildings_and_network(action):
    with pytest.raises(PermissionError):apply_action(seed_state(),action)


def test_demolition_requires_existing_target_and_is_pure():
    original=seed_state();changed=apply_action(original,dict(entity='object',operation='delete',id='h1',values={}))
    assert len(changed['objects'])==len(original['objects'])-1
    assert calculate_metrics(changed)['total_residents']==720
    with pytest.raises(ValueError):apply_action(changed,dict(entity='object',operation='delete',id='h1',values={}))


def test_road_closure_and_reopening_restores_metrics():
    s=seed_state();closed=apply_action(s,dict(entity='edge',operation='update',id='e1',values={'closed':True}))
    opened=apply_action(closed,dict(entity='edge',operation='update',id='e1',values={'closed':False}))
    assert calculate_metrics(opened)==calculate_metrics(s)



def test_radius_table_population_weighting_transport_and_provision():
    s=seed_state();m=calculate_metrics(s,200,[100,200,300,1000])
    total=sum(h['residents'] for h in m['rows'])
    for r in m['park_table']:
        covered=sum(h['residents'] for h in m['rows'] if h['park_distance'] is not None and h['park_distance']<=r['radius'])
        assert r['residents']==covered and r['percent']==round(covered/total*100,1)
    assert m['park_percent']==next(r['percent'] for r in m['park_table'] if r['radius']==200)
    transport=sum(h['residents'] for h in m['rows'] if h['stop_distance'] is not None and h['stop_distance']<=500)
    assert m['transport_access']==round(transport/total*100,1)
    for entry in m['provision']:assert entry['per_1000']==round(entry['count']*1000/total,3)
    assert m['facility_provision']==round(sum(p['count'] for p in m['provision'])*1000/total,3)


def test_new_house_and_stop_snap_to_same_path_interior():
    # The old endpoint approach gave 490 + 480 = 970m for homes only 10m away.
    state={'nodes':[dict(id='a',x=0,y=0),dict(id='b',x=1000,y=0)],
           'edges':[dict(id='road',a='a',b='b',closed=False,length=1000)],
           'objects':[dict(id='h',kind='home',name='Дом',x=490,y=5,residents=200,capacity=200,load=0,source='proposal'),
                      dict(id='s',kind='stop',name='Остановка',x=480,y=5,residents=0,capacity=100,load=0,source='proposal')]}
    m=calculate_metrics(state)
    assert m['average_stop']==20 and m['transport_access']==100
    assert m['rows'][0]['stop_route']
    assert not any(n.startswith('_snap_') for n in m['rows'][0]['stop_path'])
