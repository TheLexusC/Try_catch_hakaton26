"""Local metre coordinates for routing; GeoJSON remains WGS84 for Leaflet."""
from math import cos, radians, floor, hypot
ORIGIN_LON,ORIGIN_LAT = 36.55,55.06
X_SCALE = 111320*cos(radians(55.11))

def project(lon,lat):return round((lon-ORIGIN_LON)*X_SCALE,2),round((lat-ORIGIN_LAT)*111320,2)
def unproject(x,y):return [ORIGIN_LON+x/X_SCALE,ORIGIN_LAT+y/111320]

class NodeIndex:
    def __init__(self,nodes,cell=200):
        self.cell=cell;self.grid={};self.nodes={n['id']:n for n in nodes}
        for n in nodes:self.grid.setdefault((floor(n['x']/cell),floor(n['y']/cell)),[]).append(n)
    def nearest(self,x,y):
        if not self.nodes:raise ValueError('Пешеходная сеть пуста')
        c=self.cell;gx,gy=floor(x/c),floor(y/c);best=(float('inf'),'')
        for radius in range(201):
            for i in range(gx-radius,gx+radius+1):
                for j in range(gy-radius,gy+radius+1):
                    if radius and abs(i-gx)!=radius and abs(j-gy)!=radius:continue
                    for n in self.grid.get((i,j),()):best=min(best,(hypot(n['x']-x,n['y']-y),n['id']))
            outside=min(x-(gx-radius)*c,(gx+radius+1)*c-x,y-(gy-radius)*c,(gy+radius+1)*c-y)
            if best[0]<=outside:return best[1],best[0]
        raise ValueError('Объект слишком далеко от сети')
