"""Stop only this project's local cluster; never touches an external database."""
import subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
if not (root/'.runtime/local-postgres').exists():
    raise SystemExit('В проекте нет локального кластера PostgreSQL.')
program=next((root/'.runtime/pg/node_modules/@embedded-postgres').glob('*/native/bin/pg_ctl'))
raise SystemExit(subprocess.call([str(program),'-D',str(root/'.runtime/pgdata'),'-m','fast','-w','stop']))
