import pytest
from backend.geo import project,unproject
from backend.planning import demolition_cost,demolition_info,footprint_area


def polygon(width,height,holes=None):
    ring=[unproject(3000+x,4000+y) for x,y in [(0,0),(width,0),(width,height),(0,height),(0,0)]]
    return dict(type='Polygon',coordinates=[ring,*(holes or [])])


def test_area_holes_and_multipolygon():
    hole=polygon(20,20)['coordinates'][0]
    assert footprint_area(polygon(100,100,[hole]))==pytest.approx(9600,abs=1)
    a=polygon(100,100)['coordinates'];b=polygon(30,40)['coordinates']
    assert footprint_area(dict(type='MultiPolygon',coordinates=[a,b]))==pytest.approx(11200,abs=1)


def test_price_grows_with_size_population_and_central_location():
    x,y=project(36.616,55.105)
    obj=dict(id='house',kind='home',name='Дом',x=x,y=y,residents=50,geom=polygon(20,30))
    baseline=demolition_cost(obj)['amount']
    assert demolition_cost(dict(obj,residents=100))['amount']>baseline
    assert demolition_cost(dict(obj,geom=polygon(40,60)))['amount']>baseline
    assert demolition_cost(dict(obj,x=x+6000))['amount']<baseline
    assert demolition_info(obj,baseline)['allowed']
    assert not demolition_info(obj,baseline-1)['allowed']
    assert demolition_cost(dict(obj,geom=None))['area_estimated']
