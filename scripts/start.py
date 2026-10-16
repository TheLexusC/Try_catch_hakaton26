"""Local launcher: installs project dependencies, starts PostgreSQL and the API."""
import argparse
import hashlib
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
NODE_VERSION = '22.23.3'
PG_VERSION = '17.10.0-beta.17'


def run(args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, cwd=ROOT, **kwargs)


def node_runtime():
    local = RUNTIME / 'node/bin'
    if not (local / 'node').exists():
        system = {'Darwin':'darwin','Linux':'linux'}.get(platform.system())
        arch = 'arm64' if platform.machine() in ('arm64','aarch64') else 'x64'
        if not system:
            raise RuntimeError('Для Windows используйте WSL или установленные Node.js и PostgreSQL по README.')
        name = f'node-v{NODE_VERSION}-{system}-{arch}'
        url = f'https://nodejs.org/dist/v{NODE_VERSION}/'
        archive, checksums = RUNTIME/'node.tar.gz', RUNTIME/'SHASUMS256.txt'
        for file, remote in [(archive,name+'.tar.gz'),(checksums,'SHASUMS256.txt')]:
            run(['curl','--fail','-L','--retry','2',url+remote,'-o',file])
        expected = next(line.split()[0] for line in checksums.read_text().splitlines() if line.endswith(name+'.tar.gz'))
        if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Не совпала контрольная сумма Node.js. Повторите загрузку.')
        with tarfile.open(archive) as data:
            data.extractall(RUNTIME, filter='data')
        (RUNTIME/name).rename(RUNTIME/'node')
        archive.unlink()
    os.environ['PATH'] = str(local)+os.pathsep+os.environ.get('PATH','')
    os.environ['npm_config_cache'] = str(RUNTIME/'npm-cache')
    return local/'npm'


def database(npm):
    from dotenv import dotenv_values
    import psycopg
    from psycopg import sql
    env_file=ROOT/'.env'
    configured=os.environ.get('DATABASE_URL') or dotenv_values(env_file).get('DATABASE_URL')
    marker=RUNTIME/'local-postgres'
    signature=hashlib.sha256(configured.encode()).hexdigest() if configured else None
    # Only the cluster created for this exact local connection is managed here.
    if configured and (not marker.exists() or marker.read_text()!=signature):
        os.environ['DATABASE_URL']=configured
        return
    native = RUNTIME/'pg/node_modules/@embedded-postgres'/f'darwin-{ "arm64" if platform.machine()=="arm64" else "x64" }'/'native/bin'
    if platform.system()!='Darwin':
        if not configured:raise RuntimeError('Укажите DATABASE_URL PostgreSQL в .env; автоматическая локальная установка предназначена для macOS.')
        os.environ['DATABASE_URL']=configured
        return
    if not (native/'postgres').exists():
        run([npm,'install','--prefix',RUNTIME/'pg','--no-audit','--no-fund',f'@embedded-postgres/{native.parent.parent.name}@{PG_VERSION}'])
    if not configured:
        password=secrets.token_urlsafe(24)
        configured=f'postgresql://obninsk:{password}@127.0.0.1:55432/obninsk2040'
        fd=os.open(env_file,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as file:file.write('DATABASE_URL='+configured+'\n')
        marker.write_text(hashlib.sha256(configured.encode()).hexdigest())
    os.environ['DATABASE_URL']=configured
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    connection=conninfo_to_dict(configured)
    cluster=RUNTIME/'pgdata'; socket_dir=RUNTIME/'socket';socket_dir.mkdir(exist_ok=True,mode=0o700)
    if not (cluster/'PG_VERSION').exists():
        password_file=RUNTIME/'init-password'
        password_file.write_text(connection['password']);password_file.chmod(0o600)
        try:
            run([native/'initdb','-D',cluster,'-U','obninsk','--encoding=UTF8','--locale=C','--auth-host=scram-sha-256','--auth-local=scram-sha-256','--pwfile',password_file])
        finally:password_file.unlink(missing_ok=True)
    status=subprocess.run([str(native/'pg_ctl'),'-D',str(cluster),'status'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if status.returncode:
        run([native/'pg_ctl','-D',cluster,'-l',RUNTIME/'postgres.log','-w','start','-o',f'-h 127.0.0.1 -p 55432 -k {socket_dir}'])
    admin=make_conninfo(configured,dbname='postgres')
    with psycopg.connect(admin,autocommit=True,connect_timeout=5) as db:
        if not db.execute('SELECT 1 FROM pg_database WHERE datname=%s',(connection['dbname'],)).fetchone():
            db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(connection['dbname'])))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args();RUNTIME.mkdir(exist_ok=True)
    venv=ROOT/'.venv';python=venv/'bin/python'
    if Path(sys.prefix).resolve()!=venv.resolve():
        if not python.exists():run([sys.executable,'-m','venv',venv])
        os.execv(str(python),[str(python),str(__file__),*sys.argv[1:]])
    requirements=ROOT/'backend/requirements.txt';marker=RUNTIME/'python-requirements.sha256'
    signature=hashlib.sha256(requirements.read_bytes()).hexdigest()
    if not marker.exists() or marker.read_text()!=signature:
        run([python,'-m','pip','install','--timeout','60','-r',requirements]);marker.write_text(signature)
    npm=node_runtime();database(npm)
    frontend=ROOT/'frontend';dist=frontend/'dist/index.html'
    inputs=[*frontend.glob('src/**/*.jsx'),*frontend.glob('src/**/*.js'),*frontend.glob('src/**/*.css'),frontend/'package-lock.json',frontend/'index.html',frontend/'vite.config.js']
    if not dist.exists() or any(p.stat().st_mtime>dist.stat().st_mtime for p in inputs):
        run([npm,'ci','--prefix',frontend,'--no-audit','--no-fund'])
        run([npm,'run','build','--prefix',frontend])
    if args.prepare:
        print('PostgreSQL и сборка готовы.');return
    port=args.port
    while port<args.port+20:
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',port))!=0:break
        port+=1
    else:raise RuntimeError('Не найден свободный порт. Укажите --port.')
    os.environ['OBNINSK_ORIGINS']=f'http://127.0.0.1:{port},http://localhost:{port}'
    print(f'Откройте http://127.0.0.1:{port} · Остановка: Ctrl+C',flush=True)
    os.chdir(ROOT)
    os.execv(str(python),[str(python),'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',str(port)])


if __name__=='__main__':
    try:main()
    except (RuntimeError,subprocess.CalledProcessError) as error:
        print('Ошибка запуска:',error,file=sys.stderr);sys.exit(1)
