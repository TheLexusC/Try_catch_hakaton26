"""Условный район Обнинска: 16 узлов, 24 дорожки, 11 объектов. Всё в метрах."""
DISTRICT = 'obninsk-central'

def seed_state():
    nodes = [dict(id=f'n{r*4+c+1}', name=f'Узел {r*4+c+1}', x=150+c*270, y=120+r*220)
             for r in range(4) for c in range(4)]
    edges = []
    for i, node in enumerate(nodes):
        for j in ([i+1] if i%4<3 else []) + ([i+4] if i<12 else []):
            edges.append(dict(id=f'e{len(edges)+1}', a=node['id'], b=nodes[j]['id'], closed=False, capacity=500, load=100+(i%4)*60))
    # id, name, type, x, y, residents, capacity, current load (people or visits/h).
    rows = [
        ('h1','Курчатова, 15','home',120,80,180,220,180),
        ('h2','Курчатова, 17','home',390,160,240,280,240),
        ('h3','Курчатова, 19','home',730,290,200,240,200),
        ('h4','Мира, 12','home',120,600,120,180,120),
        ('h5','Мира, 14','home',1010,820,160,200,160),
        ('s1','Остановка «Курчатова»','stop',435,340,0,150,110),
        ('s2','Остановка «Мира»','stop',945,560,0,120,135),
        ('p1','Зелёный сквер','park',660,790,0,300,90),
        ('sc1','Школа района','school',1000,300,0,600,540),
        ('cl1','Поликлиника','clinic',340,580,0,100,115),
        ('sh1','Магазин у дома','shop',730,90,0,120,85),
    ]
    objects = [dict(zip(('id','name','kind','x','y','residents','capacity','load'), row)) for row in rows]
    return dict(version=0, nodes=nodes, edges=edges, objects=objects)
