"""Compressed OSM snapshot, imported once; live state is always PostgreSQL."""
import gzip,json
from pathlib import Path
DISTRICT='obninsk-city-osm'

def seed_state():
    with gzip.open(Path(__file__).resolve().parents[1]/'db/obninsk.osm.json.gz','rt',encoding='utf8') as file:
        return json.load(file)
