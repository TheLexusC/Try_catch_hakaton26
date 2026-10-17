from shapely.geometry import Polygon,LineString,Point
from backend.layout import fit_layout,local_geometry
from backend.geo import unproject

def test_fit_keeps_multiple_homes_and_avoids_roads_and_boundary():
    state={'objects':[],'edges':[],'nodes':[{'id':'n','x':150,'y':0}]}
    context=[{'kind':'road','geometry':{'type':'LineString','coordinates':[unproject(150,0),unproject(150,300)]}}]
    boundary=[dict(x=x,y=y) for x,y in [(0,0),(300,0),(300,300),(0,300)]]
    houses=[dict(id='h1',name='Дом 1',x=150,y=70,width=100,height=80,residents=100),dict(id='h2',name='Дом 2',x=230,y=230,width=100,height=80,residents=100)]
    result=fit_layout(state,houses,boundary,[],context)
    assert [h['id'] for h in result]==['h1','h2']
    for h in result:
        geom=local_geometry(h['geom'])
        assert geom.area>=25 and Polygon([(p['x'],p['y']) for p in boundary]).buffer(.001).covers(geom)
        assert geom.intersection(LineString([(150,0),(150,300)]).buffer(5.999)).area<.01
        assert geom.buffer(.001).covers(Point(h['x'],h['y']))
    assert result[0]['trimmed']
    assert local_geometry(result[0]['geom']).intersection(local_geometry(result[1]['geom'])).area==0


def test_previous_footprints_are_preserved_when_another_home_is_added():
    state={'objects':[],'edges':[],'nodes':[{'id':'n','x':0,'y':0}]}
    boundary=[dict(x=x,y=y) for x,y in [(0,0),(500,0),(500,500),(0,500)]]
    first=dict(id='h1',name='Дом 1',x=100,y=100,width=100,height=80,residents=100)
    original=fit_layout(state,[first],boundary,[],[])[0]
    second=dict(id='h2',name='Дом 2',x=300,y=300,width=100,height=80,residents=100)
    result=fit_layout(state,[original,second],boundary,[],[])
    assert len(result)==2 and result[0]['geom']==original['geom']
