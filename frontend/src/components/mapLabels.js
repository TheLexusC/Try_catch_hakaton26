import L from 'leaflet';

export function addMapLabels(map, getObjects, getRoads, getSelected) {
  const pane = map.createPane('cityLabels');
  pane.style.zIndex = '625';
  pane.style.pointerEvents = 'none';
  
  const canvas = L.DomUtil.create('canvas', 'city-label-canvas', pane);
  const ctx = canvas.getContext('2d');
  
  let frame;
  let removed = false;
  
  const draw = () => {
    const size = map.getSize();
    const ratio = window.devicePixelRatio || 1;
    
    L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]));
    
    canvas.width = size.x * ratio;
    canvas.height = size.y * ratio;
    canvas.style.width = size.x + 'px';
    canvas.style.height = size.y + 'px';
    
    ctx.scale(ratio, ratio);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.lineJoin = 'round';
    
    const zoom = map.getZoom();
    const occupied = [];
    const namedRoads = new Set();
    
    const point = ([lon, lat]) => map.latLngToContainerPoint([lat, lon]);
    const visible = p => p.x > 12 && p.y > 12 && p.x < size.x - 12 && p.y < size.y - 12;
    
    function label(text, p, { angle = 0, size: fontSize = 11, color = '#233d50', force = false } = {}) {
      if (!text || !visible(p)) return false;
      
      ctx.font = `600 ${fontSize}px Montserrat, sans-serif`;
      
      const width = ctx.measureText(text).width + 12;
      const height = fontSize + 10;
      
      const w = Math.abs(Math.cos(angle)) * width + Math.abs(Math.sin(angle)) * height;
      const h = Math.abs(Math.sin(angle)) * width + Math.abs(Math.cos(angle)) * height;
      const box = { x: p.x - w / 2, y: p.y - h / 2, w, h };
      
      if (!force && occupied.some(b => box.x < b.x + b.w && box.x + box.w > b.x && box.y < b.y + b.h && box.y + box.h > b.y)) {
        return false;
      }
      
      occupied.push(box);
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(angle);
      
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 4;
      ctx.strokeText(text, 0, 0);
      
      ctx.fillStyle = color;
      ctx.fillText(text, 0, 0);
      ctx.restore();
      
      return true;
    }
    
    const objects = getObjects();
    const selected = objects.find(o => o.id === getSelected());
    
    const position = o => point([
      36.55 + o.x / (111320 * Math.cos(55.11 * Math.PI / 180)), 
      55.06 + o.y / 111320
    ]);
    
    if (selected && zoom >= 16) {
      label(selected.name, position(selected), { size: 12, color: '#00629f', force: true });
    }
    
    if (zoom >= 14) {
      for (const road of getRoads()) {
        const name = road.properties.name;
        if (!name || namedRoads.has(name)) continue;
        
        const pts = road.geometry.coordinates.map(point);
        let best = null;
        
        for (let i = 1; i < pts.length; i++) {
          const a = pts[i - 1];
          const b = pts[i];
          const mid = L.point((a.x + b.x) / 2, (a.y + b.y) / 2);
          const length = a.distanceTo(b);
          
          if (visible(mid) && (!best || length > best.length)) {
            best = { a, b, mid, length };
          }
        }
        
        if (!best) continue;
        
        let angle = Math.atan2(best.b.y - best.a.y, best.b.x - best.a.x);
        if (angle > Math.PI / 2) angle -= Math.PI;
        if (angle < -Math.PI / 2) angle += Math.PI;
        
        if (label(name, best.mid, { angle, size: zoom >= 16 ? 12 : 10, color: '#455561' })) {
          namedRoads.add(name);
        }
      }
    }
    
    if (zoom >= 15) {
      for (const obj of objects) {
        if (obj.id === selected?.id && zoom >= 16) continue;
        
        const facility = ['stop', 'park', 'school', 'clinic', 'shop'].includes(obj.kind);
        if (!facility && zoom < 17) continue;
        
        let text = obj.name;
        if (!facility) {
          if (text.includes(' · ') || text === 'Здание') continue;
          if (zoom === 17 && text.includes(', ')) text = text.split(', ').at(-1);
        }
        
        const color = obj.kind === 'stop' ? '#846017' : (obj.kind === 'park' ? '#2b6850' : '#233d50');
        label(text, position(obj), { size: facility ? 11 : 10, color });
      }
    }
  };
  
  const refresh = () => {
    if (removed) return;
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(draw);
  };
  
  map.on('moveend zoomend resize', refresh);
  document.fonts.ready.then(refresh);
  refresh();
  
  return {
    refresh,
    remove() {
      removed = true;
      cancelAnimationFrame(frame);
      map.off('moveend zoomend resize', refresh);
      canvas.remove();
    }
  };
}


