-- PostgreSQL 16+. Geometry is stored once as coordinates, not repeated polygons.
CREATE TABLE IF NOT EXISTS districts (
    id text PRIMARY KEY, name text NOT NULL, version integer NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS nodes (
    id text PRIMARY KEY, district_id text NOT NULL REFERENCES districts(id),
    name text NOT NULL, x double precision NOT NULL, y double precision NOT NULL,
    UNIQUE(id, district_id), CHECK(x BETWEEN 0 AND 1200 AND y BETWEEN 0 AND 900)
);
CREATE TABLE IF NOT EXISTS edges (
    id text PRIMARY KEY, district_id text NOT NULL REFERENCES districts(id),
    a text NOT NULL, b text NOT NULL, closed boolean NOT NULL DEFAULT false,
    capacity integer NOT NULL DEFAULT 500 CHECK(capacity>0),
    load integer NOT NULL DEFAULT 0 CHECK(load>=0),
    FOREIGN KEY(a,district_id) REFERENCES nodes(id,district_id),
    FOREIGN KEY(b,district_id) REFERENCES nodes(id,district_id), CHECK(a<>b),
    UNIQUE(district_id,a,b)
);
CREATE UNIQUE INDEX IF NOT EXISTS edges_undirected ON edges(district_id,LEAST(a,b),GREATEST(a,b));
CREATE TABLE IF NOT EXISTS objects (
    id text PRIMARY KEY, district_id text NOT NULL REFERENCES districts(id),
    name text NOT NULL, kind text NOT NULL CHECK(kind IN ('home','stop','park','school','clinic','shop')),
    x double precision NOT NULL, y double precision NOT NULL,
    residents integer NOT NULL DEFAULT 0 CHECK(residents>=0),
    capacity integer NOT NULL DEFAULT 100 CHECK(capacity>0),
    load integer NOT NULL DEFAULT 0 CHECK(load>=0),
    CHECK(x BETWEEN 0 AND 1200 AND y BETWEEN 0 AND 900),
    CHECK(kind='home' OR residents=0)
);
CREATE INDEX IF NOT EXISTS objects_district_kind ON objects(district_id,kind);
CREATE TABLE IF NOT EXISTS users (
    id text PRIMARY KEY, email text NOT NULL UNIQUE, name text NOT NULL,
    password_hash text NOT NULL, role text NOT NULL DEFAULT 'user' CHECK(role IN ('user','moderator')),
    created_at text NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash text PRIMARY KEY, user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token text NOT NULL, expires_at double precision NOT NULL
);
CREATE TABLE IF NOT EXISTS proposals (
    id text PRIMARY KEY, district_id text NOT NULL REFERENCES districts(id),
    author_id text NOT NULL REFERENCES users(id), action jsonb NOT NULL, reason text NOT NULL,
    base_version integer NOT NULL, status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
    created_at text NOT NULL, closed_at text, reviewer_id text REFERENCES users(id),
    comment text, applied_version integer,
    CHECK((status='pending' AND closed_at IS NULL) OR
          (status<>'pending' AND closed_at IS NOT NULL AND reviewer_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS proposals_author ON proposals(author_id);
CREATE UNIQUE INDEX IF NOT EXISTS proposals_duplicate ON proposals(author_id,district_id,action) WHERE status='pending';
CREATE TABLE IF NOT EXISTS auth_attempts (key text NOT NULL, attempted_at double precision NOT NULL);
CREATE INDEX IF NOT EXISTS attempts_key_time ON auth_attempts(key,attempted_at);

-- City geometry migration; one compact GeoJSON value per building or road.
ALTER TABLE nodes DROP CONSTRAINT IF EXISTS nodes_check;
ALTER TABLE nodes ADD CONSTRAINT nodes_check CHECK(x BETWEEN 0 AND 20000 AND y BETWEEN 0 AND 20000);
ALTER TABLE objects DROP CONSTRAINT IF EXISTS objects_check;
ALTER TABLE objects ADD CONSTRAINT objects_check CHECK(x BETWEEN 0 AND 20000 AND y BETWEEN 0 AND 20000);
ALTER TABLE objects DROP CONSTRAINT IF EXISTS objects_kind_check;
ALTER TABLE objects ADD CONSTRAINT objects_kind_check CHECK(kind IN ('home','building','stop','park','school','clinic','shop'));
ALTER TABLE objects ADD COLUMN IF NOT EXISTS geom jsonb;
ALTER TABLE objects ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'proposal';
ALTER TABLE objects ADD COLUMN IF NOT EXISTS node_id text;
ALTER TABLE objects ADD COLUMN IF NOT EXISTS approach double precision;
ALTER TABLE edges ADD COLUMN IF NOT EXISTS geom jsonb;
ALTER TABLE edges ADD COLUMN IF NOT EXISTS length double precision;
CREATE TABLE IF NOT EXISTS map_context (
    district_id text NOT NULL REFERENCES districts(id), id text NOT NULL,
    kind text NOT NULL, name text NOT NULL, geometry jsonb NOT NULL,
    PRIMARY KEY(district_id,id)
);
ALTER TABLE proposals ADD COLUMN IF NOT EXISTS target_name text;
CREATE TABLE IF NOT EXISTS demolitions (
    district_id text NOT NULL REFERENCES districts(id), id text NOT NULL,
    name text NOT NULL, geom jsonb NOT NULL, PRIMARY KEY(district_id,id)
);
