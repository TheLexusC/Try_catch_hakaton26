import React, { useMemo, useState } from 'react';

export default function CityMap({ 
  map, 
  state, 
  metrics, 
  mode, 
  stopId, 
  onAction, 
  selectedHome, 
  setSelectedHome, 
  previewing 
}) {
  // Состояния
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [drag, setDrag] = useState(null);

  const width = 1000;
  const height = 760;

  // Математика и проекции
  const project = ([lon, lat]) => [
    (lon - 36.618) * Math.cos((55.104 * Math.PI) / 180) * 111320 * 0.68 + width / 2,
    (55.104 - lat) * 111320 * 0.68 + height / 2,
  ];
  
  const points = (geo) => geo.map(project).map((p) => p.join(',')).join(' ');
  const nodeMap = useMemo(() => Object.fromEntries(map.nodes.map((n) => [n.id, n])), [map]);
  const closed = new Set(state.closed_edges);
  
  // Данные для маршрутов
  const row = metrics.rows.find((r) => r.id === selectedHome) || metrics.rows[0];
  
  const routeEdges = (path) =>
    path
      .slice(1)
      .map((id, index) =>
        map.edges
          .filter(
            (e) =>
              !closed.has(e.id) &&
              ((e.a === id && e.b === path[index]) || (e.b === id && e.a === path[index]))
          )
          .sort((a, b) => a.length - b.length)[0]
      )
      .filter(Boolean);

  const routes = [
    ['park', row.park_path],
    ['stop', row.stop_path],
  ];

  // Обработчики действий
  const activateEdge = (e) =>
    mode === 'edge' &&
    onAction({
      type: closed.has(e.id) ? 'open_edge' : 'close_edge',
      target_id: e.id,
    });

  const activateNode = (n) => {
    if (mode === 'move_stop') {
      onAction({ type: mode, target_id: n.id, facility_id: stopId });
    }
    if (mode === 'add_park') {
      onAction({ type: mode, target_id: n.id });
    }
  };

  const reset = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  // Тексты подсказок
  const hints = {
    inspect: 'Выберите жилой дом — покажем его маршруты',
    edge: 'Нажмите на дорожку, чтобы предложить изменение',
    move_stop: 'Нажмите на узел для нового положения остановки',
    add_park: 'Нажмите на узел для новой зелёной зоны',
    remove_park: 'Нажмите на зелёный маркер парка',
  };

  // Обработчики мыши/тач-событий карты
  const handlePointerDown = (e) => {
    if (e.target === e.currentTarget || e.target.dataset.pan === 'true') {
      e.currentTarget.setPointerCapture(e.pointerId);
      setDrag({
        cx: e.clientX,
        cy: e.clientY,
        px: pan.x,
        py: pan.y,
        scale: width / e.currentTarget.getBoundingClientRect().width,
      });
    }
  };

  const handlePointerMove = (e) => {
    if (drag) {
      setPan({
        x: drag.px + (e.clientX - drag.cx) * drag.scale,
        y: drag.py + (e.clientY - drag.cy) * drag.scale,
      });
    }
  };

  const handlePointerUpOrCancel = () => setDrag(null);

  return (
    <div className="map-panel">
      {/* Верхняя панель */}
      <div className="map-top">
        <div>
          <span className={`map-status ${previewing ? 'draft' : ''}`}>
            {previewing ? 'ПРЕДПРОСМОТР' : 'ОБЩАЯ КАРТА'}
          </span>
          <strong>Улица Курчатова</strong>
          <small>{hints[mode]}</small>
        </div>
        <span className="version">v{state.version}</span>
      </div>

      {/* Контейнер карты */}
      <div className="map-viewport">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="city-map"
          aria-label="Модель улицы Курчатова на основе OpenStreetMap"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUpOrCancel}
          onPointerCancel={handlePointerUpOrCancel}
        >
          <defs>
            <pattern id="map-grain" width="22" height="22" patternUnits="userSpaceOnUse">
              <circle cx="1" cy="1" r=".6" fill="#cbd8d0" />
            </pattern>
          </defs>
          
          <rect width={width} height={height} fill="#eaf0e9" data-pan="true" />
          <rect width={width} height={height} fill="url(#map-grain)" data-pan="true" />
          
          <g transform={`translate(${width / 2 + pan.x},height/2+pan.y)scale({zoom}) translate(-width/2,{-height / 2})`}>
            
            {/* Земля */}
            {map.land.map((l, i) => (
              <polygon key={`land${i}`} points={points(l.geometry)} fill="#c6dbbd" stroke="#b8d2af" pointerEvents="none" />
            ))}
            
            {/* Дороги */}
            {map.roads.map((r, i) => (
              <g key={`road${i}`} pointerEvents="none">
                <polyline points={points(r.geometry)} fill="none" stroke="#d3dcd4" strokeWidth="18" />
                <polyline points={points(r.geometry)} fill="none" stroke="#fafbf7" strokeWidth="14" />
              </g>
            ))}
            
            {/* Здания */}
            {map.buildings.map((b) => (
              <polygon
                key={b.id}
                points={points(b.geometry)}
                className={`building ${map.homes.some((h) => h.building_id === b.id) ? 'residential' : ''}`}
              >
                <title>{b.address || 'Здание OSM'}</title>
              </polygon>
            ))}
            
            {/* Дорожки и ребра */}
            {map.edges.map((e) => (
              <g key={e.id} className={mode === 'edge' ? 'clickable-edge' : ''}>
                <polyline
                  points={points(e.geometry)}
                  fill="none"
                  stroke={closed.has(e.id) ? '#be7366' : e.synthetic ? '#c2bfa9' : '#fff'}
                  strokeWidth={closed.has(e.id) ? 3 : 2.5}
                  strokeDasharray={closed.has(e.id) ? '5 4' : e.synthetic ? '3 4' : undefined}
                  pointerEvents="none"
                />
                {mode === 'edge' && (
                  <polyline
                    points={points(e.geometry)}
                    fill="none"
                    stroke="transparent"
                    strokeWidth="13"
                    tabIndex="0"
                    role="button"
                    aria-label={`Дорожка ${e.id}, ${Math.round(e.length)} метров, ${closed.has(e.id) ? 'закрыта' : 'открыта'}`}
                    onClick={() => activateEdge(e)}
                    onKeyDown={(ev) => {
                      if (['Enter', ' '].includes(ev.key)) {
                        ev.preventDefault();
                        activateEdge(e);
                      }
                    }}
                  >
                    <title>{e.id} · {Math.round(e.length)} м</title>
                  </polyline>
                )}
              </g>
            ))}
            
            {/* Маршруты */}
            {routes.map(([type, path]) => (
              <g key={type} className={`route ${type}`} pointerEvents="none">
                {routeEdges(path).map((e) => (
                  <polyline
                    key={e.id}
                    points={points(e.geometry)}
                    fill="none"
                    strokeWidth="4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                ))}
              </g>
            ))}
            
            {/* Текст улицы */}
            <text x="515" y="420" className="street-label" transform="rotate(-77 515 420)" pointerEvents="none">
              УЛИЦА КУРЧАТОВА
            </text>
            
            {/* Узлы для изменения остановок и парков */}
            {['move_stop', 'add_park'].includes(mode) &&
              map.nodes.map((n) => {
                const [x, y] = project([n.lon, n.lat]);
                return (
                  <g
                    key={n.id}
                    className="map-node"
                    role="button"
                    tabIndex="0"
                    aria-label={`Узел ${n.label}`}
                    onClick={() => activateNode(n)}
                    onKeyDown={(e) => {
                      if (['Enter', ' '].includes(e.key)) {
                        e.preventDefault();
                        activateNode(n);
                      }
                    }}
                  >
                    <circle cx={x} cy={y} r="8" fill="transparent" />
                    <circle cx={x} cy={y} r="3.2" fill="#718b81" stroke="white" strokeWidth="1" />
                    <title>{n.label}</title>
                  </g>
                );
              })}
              
            {/* Маркеры домов */}
            {map.homes.map((h) => {
              const [x, y] = project([h.lon, h.lat]);
              return (
                <g
                  key={h.id}
                  className={`home-marker ${selectedHome === h.id ? 'selected' : ''}`}
                  tabIndex="0"
                  role="button"
                  aria-label={`Дом ${h.name}, ${h.residents} жителей`}
                  onClick={() => (mode === 'inspect' ? setSelectedHome(h.id) : activateNode(nodeMap[h.node]))}
                  onKeyDown={(e) => {
                    if (['Enter', ' '].includes(e.key)) {
                      e.preventDefault();
                      mode === 'inspect' ? setSelectedHome(h.id) : activateNode(nodeMap[h.node]);
                    }
                  }}
                >
                  <circle cx={x} cy={y} r="17" />
                  <text x={x} y={y + 5} textAnchor="middle" fontSize="14">⌂</text>
                  <rect x={x - 38} y={y + 21} width="76" height="20" rx="5" className="home-label-bg" />
                  <text x={x} y={y + 35} textAnchor="middle" className="home-label">
                    Дом {h.name.split(', ')[1]}
                  </text>
                </g>
              );
            })}
            
            {/* Объекты (остановки, парки) */}
            {state.facilities.map((f) => {
              const n = nodeMap[f.node];
              const [x, y] = project([n.lon, n.lat]);
              const remove = mode === 'remove_park' && f.kind === 'park';
              return (
                <g
                  key={f.id}
                  className={`facility f.kind{remove ? ' removable' : ''}`}
                  tabIndex={remove ? 0 : undefined}
                  role={remove ? 'button' : undefined}
                  aria-label={`${f.kind === 'stop' ? 'Остановка' : 'Парк'} ${f.name}`}
                  onClick={() => remove && onAction({ type: 'remove_park', target_id: f.id })}
                  onKeyDown={(e) => {
                    if (remove && ['Enter', ' '].includes(e.key)) {
                      e.preventDefault();
                      onAction({ type: 'remove_park', target_id: f.id });
                    }
                  }}
                >
                  <rect x={x - 12} y={y - 12} width="24" height="24" rx={f.kind === 'park' ? 12 : 6} />
                  <text x={x} y={y + 5} textAnchor="middle" fontSize="14">
                    {f.kind === 'stop' ? '▣' : '♧'}
                  </text>
                  <title>{f.name} · {n.label}</title>
                </g>
              );
            })}
          </g>
          
          {/* Компас */}
          <g transform="translate(940,40)" className="north" pointerEvents="none">
            <text textAnchor="middle" y="-8">С</text>
            <path d="M0 0L-5 17L0 13L5 17Z" fill="#43665c" />
          </g>
          
          {/* Масштабная линейка */}
          <g transform="translate(25,728)" pointerEvents="none">
            <path d={`M0 -4V0H${100 * 0.68 * zoom}V-4`} fill="none" stroke="#58746b" />
            <text x="0" y="16" fontSize="10" fill="#58746b">100 м</text>
          </g>
        </svg>

        {/* Управление масштабом */}
        <div className="zoom-controls">
          <button aria-label="Приблизить карту" disabled={zoom >= 3} onClick={() => setZoom((z) => Math.min(3, z + 0.4))}>+</button>
          <button aria-label="Отдалить карту" disabled={zoom <= 1} onClick={() => setZoom((z) => Math.max(1, z - 0.4))}>−</button>
          <button aria-label="Вся карта" onClick={reset}>⌖</button>
        </div>
        
        {/* Подпись */}
        <div className="map-caption">
          <span className="live-dot" /> Обнинск, Калужская область
        </div>
      </div>

      {/* Нижняя панель с легендой */}
      <div className="map-bottom">
        <div className="legend">
          <span><i className="legend-home" />Дома</span>
          <span><i className="legend-stop" />Остановки</span>
          <span><i className="legend-park" />Зелёные зоны</span>
          <span className="route-label">— к остановке · ┄ к парку</span>
        </div>
        <a href={map.source.url} target="_blank" rel="noreferrer">© OpenStreetMap</a>
      </div>
    </div>
  );
}
