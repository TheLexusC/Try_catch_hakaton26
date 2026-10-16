import React,{useEffect,useRef} from 'react';
import L from 'leaflet';
import {addMapLabels} from './mapLabels.js';
import 'leaflet/dist/leaflet.css';
export const kinds={home:'Жилой дом',building:'Здание',stop:'Остановка',park:'Парк',school:'Школа',clinic:'Поликлиника',shop:'Магазин'};
const scale=111320*Math.cos(55.11*Math.PI/180);
const latlng=o=>[55.06+o.y/111320,36.55+o.x/scale];
const xy=p=>({x:Math.round((p.lng-36.55)*scale),y:Math.round((p.lat-55.06)*111320)});
const colors={home:'#9aafc0',building:'#c2cdd6',school:'#8b9eae',clinic:'#c99b96',shop:'#bca77b',park:'#79a96c',stop:'#d3a348'};

export default function CityMap(props){
  const {state,metrics,mode,selectedHome,compact=false}=props;
  const container=useRef(),map=useRef(),latest=useRef(props),layers=useRef({});latest.current=props;
  useEffect(()=>{
    const instance=L.map(container.current,{preferCanvas:true,minZoom:12,maxZoom:19,zoomControl:true,maxBounds:[[55.06,36.55],[55.16,36.69]],maxBoundsViscosity:.8}).setView([55.108,36.612],14);
    instance.attributionControl.setPrefix('<a href="https://leafletjs.com" title="Interactive maps">Leaflet</a>');
    map.current=instance;
    layers.current.roadsData=[];
    const labels=addMapLabels(instance,()=>latest.current.state.objects,()=>layers.current.roadsData,()=>latest.current.selectedHome);layers.current.labels=labels;
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(instance);
    let cancelled=false;
    fetch('/api/map/context').then(r=>{if(!r.ok)throw Error();return r.json();}).then(geo=>{
      if(cancelled)return;
      layers.current.roadsData=geo.features.filter(f=>f.properties.kind==='road');labels.refresh();
      layers.current.context=L.geoJSON(geo,{interactive:false,style:f=>f.properties.kind==='road'?{color:'#f8f7ef',weight:3,opacity:.85}:{color:f.properties.kind==='water'?'#a4cad7':'#b4cda5',fillOpacity:.4,weight:1}}).addTo(instance);
      layers.current.context.bringToBack();
    }).catch(()=>{});
    instance.on('click',e=>{const current=latest.current;if(!current.compact&&['add_object','move_stop'].includes(current.mode))current.onPlace(xy(e.latlng));});
    const observer=new ResizeObserver(()=>instance.invalidateSize());observer.observe(container.current);
    return()=>{cancelled=true;observer.disconnect();labels.remove();instance.remove();map.current=null;};
  },[]);
  useEffect(()=>{
    const instance=map.current;if(!instance)return;
    if(layers.current.objects)instance.removeLayer(layers.current.objects);
    const group=L.featureGroup().addTo(instance);layers.current.objects=group;
    const popup=(layer,obj)=>{
      layer.options.bubblingMouseEvents=false;
      layer.bindTooltip(obj.name,{sticky:true});
      layer.on('click',()=>{
        const current=latest.current;
        if(!current.compact&&['add_object','move_stop'].includes(current.mode)){if(current.mode==='move_stop'&&obj.kind==='stop')current.onMoveStop(obj);else current.onPlace(xy(L.latLng(latlng(obj))));return;}
        if(current.mode==='delete'&&!current.compact&&obj.demolition?.allowed!==false){current.onSelect('object',obj);return;}
        if(obj.kind==='home')current.setSelectedHome(obj.id);
        const box=document.createElement('div'),name=document.createElement('strong'),note=document.createElement('p');
        name.textContent=obj.name;note.textContent=kinds[obj.kind]+(obj.kind==='home'?` · ≈${obj.residents} жителей (оценка)`:'' );box.append(name,note);if(obj.demolition){const cost=document.createElement('p');cost.textContent=`Снос: ${obj.demolition.amount.toLocaleString('ru-RU')} ₽ · порог ${obj.demolition.limit.toLocaleString('ru-RU')} ₽. Площадь ${obj.demolition.area_m2} м² · жителей ${obj.demolition.residents} · коэффициент расположения ${obj.demolition.location_factor}. ${obj.demolition.reason||'Снос допустим по цене.'}`;if(!obj.demolition.allowed)cost.className='demolition-denied';box.append(cost);}
        if(!current.compact){const button=document.createElement('button');button.className='map-proposal-button';button.disabled=obj.demolition?.allowed===false;button.textContent=button.disabled?'Снос запрещён по цене':obj.geom&&obj.kind!=='park'?'Предложить снос':'Предложить удаление';button.onclick=()=>{instance.closePopup();latest.current.onSelect('object',obj);};box.append(button);if(obj.kind==='stop'){const move=document.createElement('button');move.className='map-proposal-button';move.textContent='Предложить перенос';move.onclick=()=>{instance.closePopup();latest.current.onMoveStop(obj);};box.append(move);}}
        L.popup().setLatLng(latlng(obj)).setContent(box).openOn(instance);
      });
    };
    for(const obj of state.objects){
      const style={color:obj.id===selectedHome?'#177ebc':colors[obj.kind],weight:obj.id===selectedHome?2.5:1,fillColor:obj.id===selectedHome?'#42b3ff':colors[obj.kind],fillOpacity:obj.kind==='park'?.35:.65};
      if(obj.geom)L.geoJSON({type:'Feature',properties:{id:obj.id},geometry:obj.geom},{style,onEachFeature:(_,layer)=>popup(layer,obj)}).addTo(group);
      else popup(L.circleMarker(latlng(obj),{...style,radius:obj.kind==='stop'?5:7}).addTo(group),obj);
    }
    for(const obj of state.demolished||[]){L.geoJSON(obj.geom,{interactive:false,style:{color:'#c65248',weight:2,dashArray:'5 4',fillColor:'#fff5eb',fillOpacity:.85}}).addTo(group);}
    layers.current.labels?.refresh();
  },[state.objects,state.demolished,selectedHome]);
  useEffect(()=>{
    const instance=map.current;if(!instance)return;
    for(const key of ['routes','edges'])if(layers.current[key])instance.removeLayer(layers.current[key]);
    const routes=L.layerGroup().addTo(instance),roads=L.layerGroup().addTo(instance);layers.current.routes=routes;layers.current.edges=roads;
    const nodes=Object.fromEntries(state.nodes.map(n=>[n.id,n]));
    const edges=new Map(state.edges.map(e=>[[e.a,e.b].sort().join('|'),e]));
    for(const edge of state.edges){
      if(mode!=='edge'&&!edge.closed)continue;
      const points=edge.geom?edge.geom.coordinates.map(([lon,lat])=>[lat,lon]):[latlng(nodes[edge.a]),latlng(nodes[edge.b])];
      const line=L.polyline(points,{color:edge.closed?'#bf594e':'#7b9c87',weight:mode==='edge'?5:4,opacity:edge.closed?1:.5,dashArray:edge.closed?'7 5':undefined}).addTo(roads);
      line.bindTooltip(`${edge.closed?'Перекрыта':'Открыта'} · ${Math.round(edge.length||0)} м`);
      if(!compact)line.on('click',()=>latest.current.onSelect('edge',edge));
    }
    const row=metrics.rows.find(h=>h.id===selectedHome);
    if(!row)return;
    for(const kind of ['stop','park']){
      const path=row[kind+'_path'],target=state.objects.find(o=>o.id===row[kind+'_target']);if(!target||!path.length)continue;
      const points=[latlng(row),latlng(nodes[path[0]])];
      for(let i=1;i<path.length;i++){
        const edge=edges.get([path[i-1],path[i]].sort().join('|'));
        if(edge?.geom){let coords=edge.geom.coordinates.map(([lon,lat])=>[lat,lon]);const start=latlng(nodes[path[i-1]]);if(L.latLng(start).distanceTo(coords[0])>L.latLng(start).distanceTo(coords.at(-1)))coords=coords.slice().reverse();points.push(...coords);}
        else points.push(latlng(nodes[path[i]]));
      }
      points.push(latlng(target));L.polyline(points,{color:kind==='stop'?'#c98d25':'#28835c',weight:4,opacity:.95,dashArray:kind==='park'?'7 5':undefined,interactive:false}).addTo(routes);
    }
  },[state,metrics,selectedHome,mode]);
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
  const previous=useRef();
  useEffect(()=>{if(previous.current&&(previous.current!==selectedHome||props.focusRequest)){const home=state.objects.find(o=>o.id===selectedHome);if(home)map.current?.flyTo(latlng(home),17,{duration:.45});}previous.current=selectedHome;},[selectedHome,props.focusRequest]);
  return <div className={'map-panel '+(compact?'compact-map':'')}><div className="map-top"><div><span className="map-status">{compact?'ПРЕДПРОСМОТР':'OPENSTREETMAP'}</span><strong>Обнинск</strong><small>Реальные контуры зданий и улиц · версия {state.version}</small></div><span className="version">{state.objects.filter(o=>o.geom&&o.kind!=='park').length.toLocaleString('ru-RU')} зданий</span></div><div ref={container} className="leaflet-city" aria-label="Карта Обнинска с реальными зданиями"/><div className="map-bottom"><small>Выберите здание на карте. {mode==='delete'?'Будет открыта заявка на снос.':mode==='edge'?'Нажмите на дорожку для предложения перекрытия.':mode==='move_stop'?'Выберите новое место остановки.':'Масштаб — колёсиком мыши.'}</small><a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap · ODbL</a></div></div>;
}
