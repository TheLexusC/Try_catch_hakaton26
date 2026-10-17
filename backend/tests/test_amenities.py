from shapely.geometry import shape,Point
from backend.geo import project,unproject
from backend.seed import seed_state
from scripts.import_amenities import build,classify


def test_snapshot_markers_are_inside_their_shapes_and_population_is_unchanged():
    state=seed_state();objects=[o for o in state['objects'] if o['kind'] in {'parking','greenery'}]
    assert sum(o['kind']=='parking' for o in objects)==533
    assert sum(o['kind']=='greenery' for o in objects)==520
    assert sum(o['residents'] for o in state['objects'] if o['kind']=='home')==133000
    assert len({o['id'] for o in state['objects']})==len(state['objects'])
    nodes={n['id'] for n in state['nodes']}
    for obj in objects:
        assert obj['node_id'] in nodes
        if obj['geom']:
            # Stored model coordinates are rounded to centimetres.
            assert shape(obj['geom']).buffer(.000001).covers(Point(*unproject(obj['x'],obj['y'])))


def test_import_deduplicates_tiles_and_point_inside_parking_area(tmp_path):
    xml='''<osm>
      <node id="1" lon="36.60" lat="55.10"/><node id="2" lon="36.602" lat="55.10"/>
      <node id="3" lon="36.602" lat="55.102"/><node id="4" lon="36.60" lat="55.102"/>
      <node id="5" lon="36.601" lat="55.101"><tag k="amenity" v="parking"/></node>
      <node id="6" lon="36.61" lat="55.11"><tag k="amenity" v="parking"/></node>
      <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/><tag k="amenity" v="parking"/></way>
    </osm>'''
    (tmp_path/'first.osm').write_text(xml);(tmp_path/'overlap.osm').write_text(xml)
    x,y=project(36.60,55.10);data=build(tmp_path,[dict(id='n1',x=x,y=y)])
    assert len(data['objects'])==2
    assert {o['id'] for o in data['objects']}=={'osm_parking_w10','osm_parking_n6'}
    assert all(o['kind']=='parking' for o in data['objects'])
    assert classify({'leisure':'park','landuse':'grass'}) is None
    assert classify({'landuse':'grass'})=='greenery'


def test_multipolygon_hole_marker_stays_inside_zone(tmp_path):
    coords=[(36.60,55.10),(36.604,55.10),(36.604,55.104),(36.60,55.104),
            (36.601,55.101),(36.603,55.101),(36.603,55.103),(36.601,55.103)]
    xml='<osm>'+''.join(f'<node id="{i}" lon="{x}" lat="{y}"/>' for i,(x,y) in enumerate(coords,1))
    for wid,refs in [('1',[1,2,3,4,1]),('2',[5,6,7,8,5])]:
        xml+=f'<way id="{wid}">'+''.join(f'<nd ref="{n}"/>' for n in refs)+'</way>'
    xml+='''<relation id="20"><member type="way" ref="1" role="outer"/><member type="way" ref="2" role="inner"/><tag k="type" v="multipolygon"/><tag k="natural" v="wood"/></relation></osm>'''
    (tmp_path/'area.osm').write_text(xml)
    x,y=project(36.60,55.10);obj=build(tmp_path,[dict(id='n',x=x,y=y)])['objects'][0]
    area=shape(obj['geom']);assert len(area.interiors)==1
    assert area.covers(Point(*unproject(obj['x'],obj['y'])))
