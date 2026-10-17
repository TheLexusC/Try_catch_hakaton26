"""Compressed OSM snapshot, imported once; live state is always PostgreSQL."""
import gzip,json
from math import floor
from pathlib import Path
DISTRICT='obninsk-city-osm'

def seed_state():
    with gzip.open(Path(__file__).resolve().parents[1]/'db/obninsk.osm.json.gz','rt',encoding='utf8') as file:
        state=json.load(file)
    homes=[o for o in state['objects'] if o['kind']=='home'];total=sum(o['residents'] for o in homes)
    if total:
        weighted=[(h,h['residents']*133000/total) for h in homes]
        remaining=133000-sum(floor(value) for _,value in weighted)
        extras={h['id'] for h,value in sorted(weighted,key=lambda item:(-(item[1]-floor(item[1])),item[0]['id']))[:remaining]}
        for home,value in weighted:home['residents']=floor(value)+(home['id'] in extras)
    return state
