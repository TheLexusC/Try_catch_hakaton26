import psycopg

url = "postgresql://obninsk:obninsk_local@127.0.0.1:5432/obninsk2040"
with psycopg.connect(url, connect_timeout=5) as db:
    for row in db.execute("select email, created_at from users"):
        print(row)
    print("OK, подключение работает")