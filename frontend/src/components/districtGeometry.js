export function boundaryError(points) {
  if (points.length < 3) return 'Отметьте минимум 3 разные вершины района.';
  if (points.length > 60) return 'В границе может быть до 60 вершин.';
  
  if (points.some(p => !Number.isFinite(p.x) || !Number.isFinite(p.y) || p.x < 0 || p.y < 0 || p.x > 20000 || p.y > 20000)) {
    return 'Граница выходит за пределы модели города.';
  }
  
  if (new Set(points.map(p => p.x + ',' + p.y)).size !== points.length) {
    return 'Две вершины совпадают. Отмените последнюю вершину.';
  }
  
  const edges = points.map((p, i) => [p, points[(i + 1) % points.length]]);
  const cross = (a, b, c) => (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
  
  for (let i = 0; i < edges.length; i++) {
    for (let j = i + 1; j < edges.length; j++) {
      if (j === i + 1 || (i === 0 && j === edges.length - 1)) continue;
      
      const [a, b] = edges[i];
      const [c, d] = edges[j];
      
      const intersects1 = cross(a, b, c) * cross(a, b, d) <= 0;
      const intersects2 = cross(c, d, a) * cross(c, d, b) <= 0;
      const overlapX = Math.max(Math.min(a.x, b.x), Math.min(c.x, d.x)) <= Math.min(Math.max(a.x, b.x), Math.max(c.x, d.x));
      const overlapY = Math.max(Math.min(a.y, b.y), Math.min(c.y, d.y)) <= Math.min(Math.max(a.y, b.y), Math.max(c.y, d.y));
      
      if (intersects1 && intersects2 && overlapX && overlapY) {
        return 'Граница пересекает сама себя. Отмените вершину или начните заново.';
      }
    }
  }
  
  const area = Math.abs(edges.reduce((n, [a, b]) => n + a.x * b.y - b.x * a.y, 0)) / 2;
  if (area < 25) return 'Площадь района должна быть не меньше 25 м². Разнесите вершины дальше.';
  
  return '';
}
