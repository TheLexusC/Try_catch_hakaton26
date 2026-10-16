import math
import pytest
from backend.graph import build_graph, dijkstra, restore_path, nearest_target
from backend.data import MAP, initial_state, apply_action
from backend.metrics import calculate_metrics


def test_dijkstra_indirect_shortest():
    d,p=dijkstra({'a':{'b':10,'c':2},'b':{'a':10,'c':3},'c':{'a':2,'b':3}},'a')
    assert d['b']==5 and restore_path(p,'a','b')==['a','c','b']


def test_disconnected_and_empty_targets():
    d,p=dijkstra({'a':{},'b':{}},'a')
    assert math.isinf(d['b'])
    assert nearest_target(d,p,'a',['b'])==(None,[])
    assert nearest_target(d,p,'a',[])==(None,[])
    assert nearest_target(d,p,'a',['a'])==(0,['a'])


def test_parallel_edges_and_closure():
    nodes=[{'id':'a'},{'id':'b'}]
    edges=[{'id':'short','a':'a','b':'b','length':4},{'id':'long','a':'a','b':'b','length':9}]
    assert build_graph(nodes,edges)['a']['b']==4
    assert build_graph(nodes,edges,['short'])['a']['b']==9
    assert build_graph(nodes,edges,['short','long'])['a']=={}


def test_negative_weight():
    with pytest.raises(ValueError):dijkstra({'a':{'b':-1},'b':{}},'a')


def test_osm_graph_connected_and_valid():
    ids={n['id'] for n in MAP['nodes']}
    assert len(ids)>=10 and len(MAP['homes'])==5
    assert all(e['a'] in ids and e['b'] in ids and e['length']>0 for e in MAP['edges'])
    d,_=dijkstra(build_graph(MAP['nodes'],MAP['edges']),MAP['homes'][0]['node'])
    assert all(math.isfinite(v) for v in d.values())
    assert any(b['address']=='улица Курчатова, 17' for b in MAP['buildings'])
    assert MAP['source']['license']=='ODbL 1.0'


def test_isolated_home():
    s=initial_state();h=MAP['homes'][0]
    s['closed_edges']=[e['id'] for e in MAP['edges'] if h['node'] in (e['a'],e['b'])]
    m=calculate_metrics(s)
    assert m['rows'][0]['stop_distance'] is None and not m['rows'][0]['park_access']
    assert m['unreachable_homes']==1 and m['total_residents']==900
    assert m['average_stop']==round(sum(r['stop_distance'] for r in m['rows'][1:])/4,1)


def test_no_targets():
    s=initial_state();s['facilities']=[];m=calculate_metrics(s)
    assert m['average_stop'] is None and m['unreachable_homes']==5 and m['park_percent']==0


def test_pure_park_addition():
    s=initial_state();after=apply_action(s,{'type':'add_park','target_id':MAP['homes'][0]['node']})
    assert len(after['facilities'])==len(s['facilities'])+1
    assert calculate_metrics(after)['rows'][0]['park_distance']==0
    assert after['version']==s['version']


def test_round_trip():
    s=initial_state();e=MAP['edges'][0]['id']
    closed=apply_action(s,{'type':'close_edge','target_id':e})
    opened=apply_action(closed,{'type':'open_edge','target_id':e})
    assert calculate_metrics(opened)==calculate_metrics(s)


def test_exact_radius(monkeypatch):
    import backend.metrics as module
    tiny={'nodes':[{'id':'h'},{'id':'p'}],'edges':[{'id':'e','a':'h','b':'p','length':500.04}], 'homes':[{'id':'home','node':'h','residents':10}]}
    monkeypatch.setattr(module,'MAP',tiny)
    result=module.calculate_metrics({'closed_edges':[],'facilities':[{'node':'p','kind':'park'}]})
    assert result['rows'][0]['park_distance']==500.0 and result['park_percent']==0
