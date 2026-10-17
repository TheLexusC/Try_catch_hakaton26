import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import { addMapLabels } from './mapLabels.js';
import 'leaflet/dist/leaflet.css';

export const kinds = {
  home: 'Жилой дом',
  building: 'Здание',
  stop: 'Остановка',
  park: 'Парк',
  school: 'Школа',
  clinic: 'Поликлиника',
  shop: 'Магазин',
  parking: 'Парковка',
  greenery: 'Озеленение'
};

const scale = 111320 * Math.cos(55.11 * Math.PI / 180);
const latlng = (o) => [55.06 + o.y / 111320, 36.55 + o.x / scale];
const xy = (p) => ({
  x: Math.round((p.lng - 36.55) * scale),
  y: Math.round((p.lat - 55.06) * 111320)
});

const colors = {
  home: '#9aafc0',
  building: '#c2cdd6',
  school: '#8b9eae',
  clinic: '#c99b96',
  shop: '#bca77b',
  parking: '#727fba',
  greenery: '#409d69',
  park: '#79a96c',
  stop: '#d3a348'
};

export default function CityMap(props) {
  const { state, metrics, mode, selectedHome, compact = false } = props;
  
  const layerNames = {home:'Жилые дома',building:'Другие здания',stop:'Остановки',park:'Парки',greenery:'Озеленённые зоны',parking:'Парковки',school:'Школы',clinic:'Поликлиники',shop:'Магазины',areas:'Районы',roads:'Проектные дороги и перекрытия'};
  const [visibleLayers,setVisibleLayers] = useState(()=>Object.fromEntries(Object.keys(layerNames).map(k=>[k,true])));
  const visibleLayersRef=useRef(visibleLayers);
  visibleLayersRef.current=visibleLayers;
  const [full, setFull] = useState(false);
  const [placement, setPlacement] = useState(null);
  
  const placing = ['add_home', 'add_area', 'add_stop', 'add_object', 'draw_polygon', 'draw_road'].includes(mode);
  
  const container = useRef();
  const map = useRef();
  const latest = useRef(props);
  const layers = useRef({});
  
  latest.current = props;

  // Управление полноэкранным режимом
  useEffect(() => {
    if (!full) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    
    const escape = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); setFull(false); }
    };
    
    window.addEventListener('keydown', escape);
    return () => {
      document.body.style.overflow = original;
      window.removeEventListener('keydown', escape);
    };
  }, [full]);

  // Инициализация карты
  useEffect(() => {
    const instance = L.map(container.current, {
      preferCanvas: true,
      minZoom: 12,
      maxZoom: 19,
      zoomControl: true,
      maxBounds: [[55.06, 36.55], [55.16, 36.69]],
      maxBoundsViscosity: 0.8
    }).setView([55.108, 36.612], 14);
    
    instance.attributionControl.setPrefix(false);
    map.current = instance;
    layers.current.roadsData = [];
    
    const labels = addMapLabels(
      instance, 
      () => latest.current.state.objects.filter(o=>visibleLayersRef.current[o.kind]!==false),
      () => layers.current.roadsData, 
      () => latest.current.selectedHome
    );
    layers.current.labels = labels;
    
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(instance);
    
    let cancelled = false;
    
    // Загрузка контекстных данных
    fetch('/api/map/context')
      .then(r => {
        if (!r.ok) throw Error();
        return r.json();
      })
      .then(geo => {
        if (cancelled) return;
        layers.current.roadsData = geo.features.filter(f => f.properties.kind === 'road');
        labels.refresh();
        
        layers.current.context = L.geoJSON(geo, {
          interactive: false,
          style: f => f.properties.kind === 'road' 
            ? { color: '#f8f7ef', weight: 3, opacity: 0.85 } 
            : { color: f.properties.kind === 'water' ? '#a4cad7' : '#b4cda5', fillOpacity: 0.4, weight: 1 }
        }).addTo(instance);
        
        layers.current.context.bringToBack();
      })
      .catch(() => {});
      
    // Обработка кликов и расстановки объектов
    let pointerStart = null;
    const start = e => { pointerStart = { x: e.clientX, y: e.clientY }; };
    
    const placeClick = e => {
      const current = latest.current;
      if (current.compact || current.busy || !['add_home', 'add_area', 'add_stop', 'add_object', 'draw_polygon', 'draw_road'].includes(current.mode) || e.button !== 0 || e.target.closest('.leaflet-control,.leaflet-popup,.leaflet-tooltip')) return;
      if (pointerStart && Math.hypot(e.clientX - pointerStart.x, e.clientY - pointerStart.y) > 6) return;
      
      e.preventDefault();
      e.stopPropagation();
      
      const point = instance.mouseEventToLatLng(e);
      setPlacement(point);
      
      if (!current.mode.startsWith('draw_') && current.drawPoints === undefined) setFull(false);
      current.onPlace(xy(point));
    };
    
    container.current.addEventListener('pointerdown', start, true);
    container.current.addEventListener('click', placeClick, true);
    
    instance.on('click', e => {
      const current = latest.current;
      if (!current.compact && ['add_object', 'add_home', 'add_area', 'add_stop', 'draw_polygon', 'draw_road', 'move_stop'].includes(current.mode)) {
        current.onPlace(xy(e.latlng));
      }
    });
    
    const observer = new ResizeObserver(() => instance.invalidateSize());
    observer.observe(container.current);
    
    return () => {
      cancelled = true;
      observer.disconnect();
      instance.getContainer().removeEventListener('pointerdown', start, true);
      instance.getContainer().removeEventListener('click', placeClick, true);
      labels.remove();
      instance.remove();
      map.current = null;
    };
  }, []);

  // Рендеринг объектов на карте
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    
    if (layers.current.objects) instance.removeLayer(layers.current.objects);
    const group = L.featureGroup().addTo(instance);
    layers.current.objects = group;
    
    const popup = (layer, obj) => {
      layer.options.bubblingMouseEvents = false;
      layer.bindTooltip(obj.name, { sticky: true });
      
      layer.on('click', event => {
        const current = latest.current;
        
        if (!current.compact && ['add_object', 'add_home', 'add_area', 'add_stop', 'draw_polygon', 'draw_road', 'move_stop'].includes(current.mode)) {
          if (current.mode === 'move_stop' && obj.kind === 'stop') current.onMoveStop(obj);
          else current.onPlace(xy(event.latlng || L.latLng(latlng(obj))));
          return;
        }
        
        if (current.mode === 'delete' && !current.compact && obj.demolition?.allowed !== false) {
          current.onSelect('object', obj);
          return;
        }
        
        if (obj.kind === 'home') current.setSelectedHome(obj.id);
        
        // Создание содержимого попапа
        const box = document.createElement('div');
        const name = document.createElement('strong');
        const note = document.createElement('p');
        
        name.textContent = obj.name;
        note.textContent = kinds[obj.kind] + (obj.kind === 'home' ? ` · ≈${obj.residents} жителей (оценка)` : '');
        box.append(name, note);
        
        if (obj.demolition) {
          const cost = document.createElement('p');
          cost.textContent = `Снос: ${obj.demolition.amount.toLocaleString('ru-RU')} ₽ · порог ${obj.demolition.limit.toLocaleString('ru-RU')} ₽. Площадь ${obj.demolition.area_m2} м² · жителей ${obj.demolition.residents} · коэффициент расположения ${obj.demolition.location_factor}. ${obj.demolition.reason || 'Снос допустим по цене.'}`;
          if (!obj.demolition.allowed) cost.className = 'demolition-denied';
          box.append(cost);
        }
        
        if (!current.compact) {
          const button = document.createElement('button');
          button.className = 'map-proposal-button';
          button.disabled = obj.demolition?.allowed === false;
          button.textContent = button.disabled ? 'Снос запрещён по цене' : (obj.demolition ? 'Предложить снос' : 'Предложить удаление');
          button.onclick = () => {
            instance.closePopup();
            latest.current.onSelect('object', obj);
          };
          box.append(button);
          
          if (obj.kind === 'stop') {
            const move = document.createElement('button');
            move.className = 'map-proposal-button';
            move.textContent = 'Предложить перенос';
            move.onclick = () => {
              instance.closePopup();
              latest.current.onMoveStop(obj);
            };
            box.append(move);
          }
        }
        
        L.popup().setLatLng(latlng(obj)).setContent(box).openOn(instance);
      });
    };
    
    instance.closePopup();
    for (const obj of state.objects) {
      if(visibleLayers[obj.kind]===false)continue;
      const style = {
        dashArray: obj.source === 'proposal' && obj.kind === 'home' ? '5 3' : undefined,
        color: obj.id === selectedHome ? '#177ebc' : colors[obj.kind],
        weight: obj.id === selectedHome ? 2.5 : 1,
        fillColor: obj.id === selectedHome ? '#42b3ff' : colors[obj.kind],
        fillOpacity: obj.kind === 'park' ? 0.35 : 0.65
      };
      
      if (['parking', 'greenery'].includes(obj.kind)) {
        popup(L.circleMarker(latlng(obj), { ...style, radius: 6, weight: 2, color: obj.kind === 'parking' ? '#4c5ca6' : '#25804c', fillOpacity: .9 }).addTo(group), obj);
      } else if (obj.geom) {
        L.geoJSON({ type: 'Feature', properties: { id: obj.id }, geometry: obj.geom }, { style, onEachFeature: (_, layer) => popup(layer, obj) }).addTo(group);
      } else {
        popup(L.circleMarker(latlng(obj), { ...style, radius: obj.kind === 'stop' ? 5 : 7 }).addTo(group), obj);
      }
    }
    
    for (const obj of visibleLayers.building || visibleLayers.home ? state.demolished || [] : []) {
      L.geoJSON(obj.geom, {
        interactive: false,
        style: { color: '#c65248', weight: 2, dashArray: '5 4', fillColor: '#fff5eb', fillOpacity: 0.85 }
      }).addTo(group);
    }
    
    layers.current.labels?.refresh();
  }, [state.objects, state.demolished, selectedHome, visibleLayers]);

  useEffect(()=>{
    const instance=map.current;if(!instance)return;
    for(const key of ['routes','edges'])if(layers.current[key])instance.removeLayer(layers.current[key]);
    const routes=L.layerGroup().addTo(instance),roads=L.layerGroup().addTo(instance);layers.current.routes=routes;layers.current.edges=roads;
    const nodes=Object.fromEntries(state.nodes.map(n=>[n.id,n]));
    const edges=new Map(state.edges.map(e=>[[e.a,e.b].sort().join('|'),e]));
    for(const edge of visibleLayers.roads ? state.edges : []){
      const proposed=edge.id.includes('_e');if(mode!=='edge'&&!edge.closed&&!proposed)continue;
      const points=edge.geom?edge.geom.coordinates.map(([lon,lat])=>[lat,lon]):[latlng(nodes[edge.a]),latlng(nodes[edge.b])];
      const line=L.polyline(points,{color:edge.closed?'#bf594e':proposed?'#0075c6':'#7b9c87',weight:mode==='edge'?5:4,opacity:edge.closed?1:.5,dashArray:edge.closed?'7 5':undefined}).addTo(roads);
      line.bindTooltip(`${edge.closed?'Перекрыта':'Открыта'} · ${Math.round(edge.length||0)} м`);
      if(!compact)line.on('click',event=>{const current=latest.current;if(['add_home','add_area','add_stop','add_object','move_stop'].includes(current.mode))current.onPlace(xy(event.latlng));else if(current.mode==='edge')current.onSelect('edge',edge);});
    }
    const row=metrics.rows.find(h=>h.id===selectedHome);
    if(!row)return;
    for(const kind of ['stop','park']){
      if(!visibleLayers.home || !visibleLayers[kind])continue;
      const direct=row[kind+'_route'];if(direct?.length){L.polyline(direct.map(([lon,lat])=>[lat,lon]),{color:kind==='stop'?'#c98d25':'#28835c',weight:4,opacity:.95,dashArray:kind==='park'?'7 5':undefined,interactive:false}).addTo(routes);continue;}
      const path=row[kind+'_path'],target=state.objects.find(o=>o.id===row[kind+'_target']);if(!target||!path.length)continue;
      const points=[latlng(row),latlng(nodes[path[0]])];
      for(let i=1;i<path.length;i++){
        const edge=edges.get([path[i-1],path[i]].sort().join('|'));
        if(edge?.geom){let coords=edge.geom.coordinates.map(([lon,lat])=>[lat,lon]);const start=latlng(nodes[path[i-1]]);if(L.latLng(start).distanceTo(coords[0])>L.latLng(start).distanceTo(coords.at(-1)))coords=coords.slice().reverse();points.push(...coords);}
        else points.push(latlng(nodes[path[i]]));
      }
      points.push(latlng(target));L.polyline(points,{color:kind==='stop'?'#c98d25':'#28835c',weight:4,opacity:.95,dashArray:kind==='park'?'7 5':undefined,interactive:false}).addTo(routes);
    }
  },[state,metrics,selectedHome,mode,visibleLayers]);
  useEffect(()=>{
    const instance=map.current;if(!instance)return;
    if(layers.current.relocation)instance.removeLayer(layers.current.relocation);
    const group=L.layerGroup().addTo(instance);layers.current.relocation=group;
    const selected=state.objects.find(o=>o.id===props.movingStopId);
    if(selected){L.circleMarker(latlng(selected),{radius:12,color:'#138acb',weight:3,fillOpacity:0,interactive:false}).addTo(group);instance.flyTo(latlng(selected),17,{duration:.4});}
    const change=props.relocation;
    if(change?.before&&change?.after){
      const a=latlng(change.before),b=latlng(change.after);
      L.circleMarker(a,{radius:8,color:'#be7967',dashArray:'4 4',fillOpacity:0,interactive:false}).bindTooltip('Прежнее место',{permanent:true,direction:'top'}).addTo(group);
      L.circleMarker(b,{radius:9,color:'#158bcc',fillColor:'#42b3ff',fillOpacity:.8,interactive:false}).bindTooltip('Предлагаемое место',{permanent:true,direction:'bottom'}).addTo(group);
      L.polyline([a,b],{color:'#158bcc',dashArray:'6 5',weight:3,interactive:false}).addTo(group);
      instance.fitBounds(L.latLngBounds([a,b]),{padding:[55,55],maxZoom:17});
    }
  },[props.movingStopId,props.relocation?.before?.id,props.relocation?.before?.x,props.relocation?.before?.y,props.relocation?.after?.x,props.relocation?.after?.y]);
  useEffect(()=>{
    const instance=map.current;
    const selected=state.objects.find(o=>o.id===props.movingStopId);
    if(!instance || compact || mode!=='move_stop' || !selected)return;
    const line=L.polyline([],{color:'#158bcc',weight:3,dashArray:'7 5',interactive:false,className:'stop-cursor-line'}).addTo(instance);
    const follow=event=>line.setLatLngs([latlng(selected),event.latlng]);
    const clear=()=>line.setLatLngs([]);
    instance.on('mousemove',follow);instance.on('mouseout',clear);instance.on('click',clear);
    return()=>{instance.off('mousemove',follow);instance.off('mouseout',clear);instance.off('click',clear);instance.removeLayer(line);};
  },[mode,props.movingStopId,compact,state.objects]);
  useEffect(()=>{
    const instance=map.current;if(!instance)return;
    if(layers.current.areas)instance.removeLayer(layers.current.areas);
    const group=L.layerGroup().addTo(instance);layers.current.areas=group;
    for(const area of visibleLayers.areas ? state.areas||[] : []){const layer=L.geoJSON(area.geom,{interactive:false,style:{color:'#147dcc',weight:2,dashArray:'9 5',fillColor:'#42b3ff',fillOpacity:.09}}).addTo(group);layer.bindTooltip(area.name,{permanent:true,direction:'center',className:'area-map-label'});}
  },[state.areas,visibleLayers.areas]);
  useEffect(()=>{const obj=state.objects.find(o=>o.id===props.focusObject?.id);if(obj)map.current?.flyTo(latlng(obj),17,{duration:.4});},[props.focusObject]);
  useEffect(()=>{
    if(!placing||compact)return;
    map.current?.closePopup();
    const panel=container.current?.parentElement;if(panel)window.scrollTo({top:window.scrollY+panel.getBoundingClientRect().top-20,behavior:'smooth'});
  },[mode,compact]);
  useEffect(()=>{
    if(layers.current.placement)map.current?.removeLayer(layers.current.placement);
    if(placement)layers.current.placement=L.circleMarker(placement,{radius:10,color:'#0077c8',weight:3,fillColor:'#42b3ff',fillOpacity:.55,interactive:false}).addTo(map.current);
  },[placement]);
  useEffect(()=>{
    if(layers.current.sketch)map.current?.removeLayer(layers.current.sketch);
    const group=L.layerGroup().addTo(map.current);layers.current.sketch=group;
    for(const path of visibleLayers.roads ? props.sketchPaths||[] : [])if(path.points.length>1)L.polyline(path.points.map(latlng),{color:'#0075c6',weight:4,dashArray:'6 4',interactive:false}).addTo(group);
    const points=props.drawPoints||[];
    if(points.length>1){const factory=mode==='draw_polygon'?L.polygon:L.polyline;factory(points.map(latlng),{color:'#0075c6',weight:3,fillOpacity:.14,interactive:false}).addTo(group);}
    for(const point of points)L.circleMarker(latlng(point),{radius:5,color:'#006fab',fillOpacity:1,interactive:false}).addTo(group);
  },[props.drawPoints,props.sketchPaths,mode,visibleLayers.roads]);
  useEffect(()=>{
    if(layers.current.draftHomes)map.current?.removeLayer(layers.current.draftHomes);
    const group=L.layerGroup().addTo(map.current);layers.current.draftHomes=group;
    for(const obj of state.objects.filter(o=>visibleLayers[o.kind]!==false&&['home','stop'].includes(o.kind)&&(o.source==='proposal'||(state.draft_ids||[]).includes(o.id)))){
      if(obj.geom)L.geoJSON(obj.geom,{interactive:false,style:{color:'#0066b0',weight:3,fillColor:'#42b3ff',fillOpacity:.75}}).addTo(group);
      L.circleMarker(latlng(obj),{radius:5,color:'#0066b0',fillColor:obj.kind==='stop'?'#e8ba46':'white',fillOpacity:1,weight:2,interactive:false}).bindTooltip(obj.name,{permanent:true,direction:'top',className:'draft-home-label'}).addTo(group);
    }
  },[state.objects,state.draft_ids,visibleLayers]);
  useEffect(()=>{
    if(props.focusBoundary?.length>=3)map.current?.fitBounds(L.latLngBounds(props.focusBoundary.map(latlng)),{padding:[45,45],maxZoom:17,animate:false});
  },[props.focusBoundary]);
  const previous=useRef();
  useEffect(()=>{if(previous.current&&(previous.current!==selectedHome||props.focusRequest)){const home=state.objects.find(o=>o.id===selectedHome);if(home)map.current?.flyTo(latlng(home),17,{duration:.45});}previous.current=selectedHome;},[selectedHome,props.focusRequest]);
  useEffect(() => {
    if (props.viewReset) map.current?.setView([55.108, 36.612], 14);
  }, [props.viewReset]);

  return (
    <div className={`map-panel ${compact ? 'compact-map ' : ''}${full ? 'map-fullscreen ' : ''}${placing && !compact ? 'placing-object' : ''}`}>
      <div className="map-top">
        <div>
          <span className="map-status">{compact ? 'ПРЕДПРОСМОТР' : 'КАРТА ГОРОДА'}</span>
          <strong>Обнинск</strong>
        </div>
        <button type="button" className="secondary small" aria-label={full ? 'Закрыть полноэкранную карту' : 'Открыть карту на весь экран'} onClick={() => setFull(v => !v)}>
          {full ? '× Закрыть карту' : '⛶ На весь экран'}
        </button>
      </div>
      
      {!compact && <details className="map-layer-filters">
        <summary>Слои карты · показано {Object.values(visibleLayers).filter(Boolean).length} из {Object.keys(layerNames).length}</summary>
        <div className="layer-filter-options" role="group" aria-label="Фильтры объектов карты">
          {Object.entries(layerNames).map(([kind,label])=><label key={kind}>
            <input type="checkbox" checked={visibleLayers[kind]} onChange={e=>setVisibleLayers(current=>({...current,[kind]:e.target.checked}))}/>
            <i className="layer-color" style={{background:colors[kind]||'#147dcc'}}/>{label}
          </label>)}
        </div>
        <div className="layer-filter-actions"><button type="button" className="text-button" onClick={()=>setVisibleLayers(Object.fromEntries(Object.keys(layerNames).map(k=>[k,true])))}>Показать все слои</button><button type="button" className="text-button" onClick={()=>setVisibleLayers(Object.fromEntries(Object.keys(layerNames).map(k=>[k,false])))}>Скрыть все слои</button></div>
        <p>Фильтры скрывают объекты и их подписи. Фоновая карта и расчёт показателей сохраняются.</p>
      </details>}
      {placing && !compact && (
        <div className="placement-banner" role="status">
          <strong>
            {mode === 'draw_polygon' ? 'Граница района: отметьте вершины' : 
             mode === 'draw_road' ? 'Дорожка: отметьте точки' : 
             mode === 'add_home' ? 'Новый дом: нажмите на место' : 
             mode === 'add_area' ? 'Новый район: нажмите на место' : 
             mode === 'add_stop' ? 'Остановка: нажмите на место' : 'Инфраструктура: нажмите на место'}
          </strong>
          <span>
            {props.placementHint || (mode.startsWith('draw_') ? 'Завершите рисование кнопкой в конструкторе.' : 'Можно выбрать пустой участок или лес. После клика откроется форма.')}
          </span>
          {!mode.startsWith('draw_') && (
          <button type="button" className="secondary small" disabled={props.busy} onClick={() => {
            const point = map.current.getCenter();
            setPlacement(point);
            props.onPlace(xy(point));
          }}>
            Выбрать центр карты
          </button>
          )}
          {full && props.drawingControls && <div className="map-drawing-controls">{props.drawingControls}</div>}
          {full && props.drawingError && <p className="map-drawing-error" role="alert">{props.drawingError}</p>}
        </div>
      )}
      
      <div ref={container} className="leaflet-city" aria-label="Карта Обнинска с реальными зданиями" />
      
      <div className="map-bottom">
        <small>
          Выберите здание на карте. {mode === 'delete' ? 'Будет открыта заявка на снос.' : 
          mode === 'edge' ? 'Нажмите на дорожку для предложения перекрытия.' : 
          mode === 'move_stop' ? 'Выберите новое место остановки.' : 
          ['add_home', 'add_area', 'add_stop', 'add_object', 'draw_polygon', 'draw_road'].includes(mode) ? 'Нажмите на место нового объекта.' : 'Масштаб — колёсиком мыши.'}
        </small>
        <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap · ODbL</a>
      </div>
    </div>
  );
}


