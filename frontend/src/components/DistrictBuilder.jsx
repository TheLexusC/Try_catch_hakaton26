import React, { useState, useEffect } from 'react';
import MetricsPanel from './MetricsPanel.jsx';
import { Estimate } from './PlanningPanel.jsx';
import CityMap from './CityMap.jsx';
import { newId } from '../ids.js';

// Математические утилиты для геометрии
const scale = 111320 * Math.cos(55.11 * Math.PI / 180);
const coord = p => [36.55 + p.x / scale, 55.06 + p.y / 111320];
const geometry = points => ({ type: 'Polygon', coordinates: [[...points, points[0]].map(coord)] });

// Алгоритм Ray-casting для проверки нахождения точки внутри полигона
function inside(p, ring) {
  let yes = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i], b = ring[j];
    if ((a.y > p.y) !== (b.y > p.y) && p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x) {
      yes = !yes;
    }
  }
  return yes;
}

export default function DistrictBuilder({ city, api, onSent, draftKey = 'obninsk-district:default' }) {
  // Загрузка черновика из localStorage
  const [saved] = useState(() => {
    try {
      const d = JSON.parse(localStorage.getItem(draftKey));
      return d?.version === city.state.version ? d : {};
    } catch {
      return {};
    }
  });

  // Состояния
  const [boundary, setBoundary] = useState(saved.boundary || []);
  const [closed, setClosed] = useState(saved.closed || false);
  const [mode, setMode] = useState(saved.closed ? 'add_home' : 'draw_polygon');
  const [points, setPoints] = useState([]);
  const [houses, setHouses] = useState(saved.houses || []);
  const [roads, setRoads] = useState(saved.roads || []);
  const [stops, setStops] = useState(saved.stops || []);
  
  const [name, setName] = useState(saved.name || 'Новый район');
  const [width, setWidth] = useState(saved.width || 20);
  const [height, setHeight] = useState(saved.height || 30);
  const [residents, setResidents] = useState(saved.residents ?? 100);
  
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const [planned, setPlanned] = useState([]);
  const [confirmed, setConfirmed] = useState(false);

  const count = 1 + houses.length + roads.length + stops.length;

  // Автосохранение черновика
  useEffect(() => {
    try {
      localStorage.setItem(draftKey, JSON.stringify({
        version: city.state.version,
        boundary, closed, houses, roads, stops, name, width, height, residents
      }));
    } catch {}
  }, [boundary, closed, houses, roads, stops, name, width, height, residents, draftKey]);

  const fit = async (items, paths = roads) => {
    const specs = items.map(h => Object.fromEntries(
      ['id', 'name', 'x', 'y', 'width', 'height', 'residents', 'points', 'rotation'].map(k => [k, h[k]])
    ));
    return (await api('/layout/fit', { houses: specs, boundary, roads: paths.map(r => r.points) })).houses;
  };

  const add = async point => {
    if (busy) return;
    setError('');
    
    if (mode === 'draw_polygon') {
      setBoundary(p => [...p, point]);
      return;
    }
    if (mode === 'draw_road') {
      setPoints(p => [...p, point]);
      return;
    }
    if (!['add_home', 'add_stop'].includes(mode)) return;
    
    if (count >= 20) {
      setError('В одной заявке помещается район и до 19 домов, остановок и дорожек.');
      return;
    }
    if (!inside(point, boundary)) {
      setError('Выберите место внутри района.');
      return;
    }
    
    if (mode === 'add_stop') {
      setStops(all => [...all, { id: newId('s'), name: 'Остановка ' + (all.length + 1), kind: 'stop', ...point, source: 'proposal' }]);
      return;
    }
    
    setBusy(true);
    try {
      const next = {
        id: newId('h'),
        name: 'Дом ' + (houses.length + 1),
        x: point.x,
        y: point.y,
        width: Number(width),
        height: Number(height),
        residents: Number(residents)
      };
      setHouses(await fit([...houses, next]));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const finishBoundary = () => {
    if (boundary.length < 3) {
      setError('Отметьте минимум 3 вершины.');
      return;
    }
    setClosed(true);
    setMode('add_home');
    setError('');
  };

  const finishRoad = async () => {
    if (points.length < 2) {
      setError('Для дорожки нужно минимум 2 точки.');
      return;
    }
    if (count >= 20) {
      setError('Достигнут предел 20 изменений.');
      return;
    }
    
    setBusy(true);
    setError('');
    
    try {
      const next = [...roads, { id: newId('r'), name: 'Дорожка ' + (roads.length + 1), points }];
      if (houses.length) setHouses(await fit(houses, next));
      setRoads(next);
      setPoints([]);
      setMode('add_home');
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const send = async e => {
    e.preventDefault();
    if (!closed) { setError('Сначала завершите границу района.'); return; }
    if (points.length) { setError('Завершите дорожку или отмените её рисование.'); return; }
    
    setBusy(true);
    setError('');
    
    try {
      const actions = [
        { entity: 'area', operation: 'add', id: newId('a'), values: { name, points: boundary } },
        ...roads.map(r => ({ entity: 'road', operation: 'add', id: r.id, values: { name: r.name, points: r.points } })),
        ...stops.map(s => ({ entity: 'object', operation: 'add', id: s.id, values: Object.fromEntries(['name', 'kind', 'x', 'y'].map(k => [k, s[k]])) })),
        ...houses.map(h => ({ entity: 'object', operation: 'add', id: h.id, values: Object.fromEntries(['name', 'kind', 'x', 'y', 'width', 'height', 'residents', 'points', 'rotation'].map(k => [k, h[k]])) }))
      ];
      
      const result = await api('/preview', { actions, base_version: city.state.version });
      setPlanned(actions);
      setPreview(result);
      setConfirmed(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    setBusy(true);
    setError('');
    
    try {
      const r = await api('/proposals', { 
        actions: planned, 
        base_version: city.state.version, 
        reason: 'Проект нового района с домами и пешеходными дорожками.' 
      });
      try { localStorage.removeItem(draftKey); } catch {}
      await onSent(r.id);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  // Экран предпросмотра
  if (preview) {
    return (
      <section>
        <h3>Итог проекта: район, {houses.length} домов, {stops.length} остановок, {roads.length} дорожек</h3>
        <MetricsPanel before={preview.before} after={preview.after} />
        <Estimate estimate={preview.estimate} />
        
        {error && <p className="form-error" role="alert">{error}</p>}
        
        <label className="creative-confirm">
          <input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} /> 
          Я закончил редактирование района.
        </label>
        
        <div className="form-actions">
          <button className="secondary" disabled={busy} onClick={() => setPreview(null)}>
            Продолжить редактирование
          </button>
          <button className="primary" disabled={busy || !confirmed || !preview.estimate.can_submit} onClick={submit}>
            Отправить весь район на модерацию
          </button>
        </div>
        
        <CityMap 
          state={{ ...preview.state, draft_ids: houses.map(h => h.id) }} 
          focusBoundary={boundary} 
          metrics={preview.after} 
          mode="inspect" 
          compact 
          setSelectedHome={() => {}} 
        />
      </section>
    );
  }

  // Основной экран конструктора
  const state = {
    ...city.state,
    draft_ids: houses.map(h => h.id),
    objects: [...city.state.objects, ...houses, ...stops],
    areas: [...(city.state.areas || []), ...(closed ? [{ id: 'district-draft', name, geom: geometry(boundary) }] : [])]
  };

  return (
    <form onSubmit={send} className="district-builder">
      <label className="field">
        Название района
        <input required maxLength="80" value={name} onChange={e => setName(e.target.value)} />
      </label>
      
      <div className="district-toolbar">
        {!closed ? (
          <>
            <span>1. Отметьте вершины многоугольника: {boundary.length}</span>
            <button type="button" className="primary" onClick={finishBoundary} disabled={boundary.length < 3}>Завершить границу</button>
            <button type="button" className="secondary" onClick={() => setBoundary(p => p.slice(0, -1))}>Убрать последнюю вершину</button>
          </>
        ) : (
          <>
            <button type="button" className={mode === 'add_home' ? 'primary' : 'secondary'} onClick={() => { setPoints([]); setMode('add_home'); }}>Расставить дома</button>
            <button type="button" className={mode === 'add_stop' ? 'primary' : 'secondary'} onClick={() => { setPoints([]); setMode('add_stop'); }}>Добавить остановку</button>
            <button type="button" className={mode === 'draw_road' ? 'primary' : 'secondary'} onClick={() => { setPoints([]); setMode('draw_road'); }}>Провести дорожку</button>
            {mode === 'draw_road' && (
              <button type="button" className="secondary" disabled={points.length < 2} onClick={finishRoad}>Завершить дорожку ({points.length} точек)</button>
            )}
          </>
        )}
      </div>

      {closed && (
        <div className="editor-grid">
          <label className="field">Ширина новых домов, м<input required type="number" min="5" max="200" value={width} onChange={e => setWidth(e.target.value)} /></label>
          <label className="field">Длина новых домов, м<input required type="number" min="5" max="200" value={height} onChange={e => setHeight(e.target.value)} /></label>
          <label className="field">Жителей в новом доме<input required type="number" min="0" max="100000" step="1" value={residents} onChange={e => setResidents(e.target.value)} /></label>
        </div>
      )}
      
      <p className="district-count">В проекте: {houses.length} домов · {stops.length} остановок · {roads.length} дорожек. Все дома сохраняются в черновике.</p>
      
      <p>
        {!closed ? 'Нажимайте на карту по контуру будущего района.' : 
         mode === 'add_stop' ? 'Нажмите внутри района, чтобы поставить остановку. Подведите к ней дорожку от домов.' : 
         mode === 'draw_road' ? 'Отметьте точки дорожки и нажмите «Завершить дорожку». Её концы соединятся с городской пешеходной сетью.' : 
         'Нажимайте внутри района — каждый клик добавляет дом с указанными параметрами.'}
      </p>
      
      {error && <p className="form-error" role="alert">{error}</p>}
      {busy && <p role="status">Подбираем контуры и сохраняем дома…</p>}
      
      <CityMap state={state} focusBoundary={closed ? boundary : null} metrics={city.metrics} mode={mode} onPlace={add} onSelect={() => {}} setSelectedHome={() => {}} drawPoints={closed ? points : boundary} sketchPaths={roads} />
      
      <div className="district-items">
        <h3>Проект: {houses.length} домов, {stops.length} остановок, {roads.length} дорожек</h3>
        {houses.map(h => (
          <div key={h.id}>
            <input aria-label={'Название ' + h.name} required maxLength="80" value={h.name} onChange={e => setHouses(all => all.map(o => o.id === h.id ? { ...o, name: e.target.value } : o))} />
            <span>{h.residents} жителей · {h.area_m2 || Math.round(h.width * h.height)} м² · {h.rotation || 0}°{h.trimmed ? ' · подрезан по участку' : ''}</span>
            <button type="button" className="text-button" onClick={() => setHouses(all => all.filter(o => o.id !== h.id))}>Убрать дом</button>
          </div>
        ))}
        {stops.map(s => (
          <div key={s.id}>
            <input aria-label={'Название ' + s.name} required maxLength="80" value={s.name} onChange={e => setStops(all => all.map(o => o.id === s.id ? { ...o, name: e.target.value } : o))} />
            <button type="button" className="text-button" onClick={() => setStops(all => all.filter(o => o.id !== s.id))}>Убрать остановку</button>
          </div>
        ))}
        {roads.map(r => (
          <div key={r.id}>
            <span>{r.name}: {r.points.length} точек</span>
            <button type="button" className="text-button" onClick={() => setRoads(all => all.filter(o => o.id !== r.id))}>Убрать дорожку</button>
          </div>
        ))}
      </div>
      
      <p>Это один проект на модерацию. До одобрения общая карта не изменится.</p>
      <button className="primary" disabled={busy || !closed}>{busy ? 'Отправляем…' : 'Завершить и рассчитать район'}</button>
    </form>
  );
}
