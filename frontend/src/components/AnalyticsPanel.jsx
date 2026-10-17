import React, { useState } from 'react';
import MetricsPanel, { format } from './MetricsPanel.jsx';

const labels = {
  stop: 'Остановки',
  park: 'Парки',
  school: 'Школы',
  clinic: 'Поликлиники',
  shop: 'Магазины',
  parking: 'Парковки',
  greenery: 'Озеленение'
};

export function radiusMetrics(metrics, radius) {
  if (!metrics) return metrics;
  
  const residents = metrics.rows
    .filter(r => r.park_distance !== null && r.park_distance <= radius)
    .reduce((n, r) => n + r.residents, 0);
    
  return {
    ...metrics,
    radius,
    accessible_residents: residents,
    park_percent: metrics.total_residents 
      ? Math.round((residents / metrics.total_residents) * 1000) / 10 
      : 0
  };
}

export function ParkTable({ metrics, after, radii, radius, setRadius, setRadii }) {
  const [custom, setCustom] = useState(750);
  
  const at = (m, r) => {
    const n = m.rows
      .filter(h => h.park_distance !== null && h.park_distance <= r)
      .reduce((a, h) => a + h.residents, 0);
      
    return {
      n,
      p: m.total_residents ? Math.round((n / m.total_residents) * 1000) / 10 : 0
    };
  };

  const handleAddRadius = (e) => {
    e.preventDefault();
    const newRadius = Number(custom);
    if (radii.length < 15 || radii.includes(newRadius)) {
      setRadii([...new Set([...radii, newRadius])].sort((a, b) => a - b));
      setRadius(newRadius);
    }
  };

  return (
    <div className="park-radius-panel">
      <div className="section-heading">
        <h3>Доступ к парку по расстоянию</h3>
        <form onSubmit={handleAddRadius}>
          <label>
            Добавить радиус, м 
            <input 
              aria-label="Новый радиус парка" 
              type="number" 
              min="10" 
              max="10000" 
              required 
              value={custom} 
              onChange={e => setCustom(e.target.value)}
            />
          </label>
          <button className="secondary small" disabled={radii.length >= 15}>
            Добавить
          </button>
        </form>
      </div>
      
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Радиус пешком</th>
              <th>Условных жителей</th>
              <th>Доля жителей</th>
              {after && <th>После изменения</th>}
            </tr>
          </thead>
          <tbody>
            {radii.map(r => {
              const b = at(metrics, r);
              const a = after ? at(after, r) : null;
              
              return (
                <tr className={r === radius ? 'selected-row' : ''} key={r}>
                  <td>
                    <label>
                      <input 
                        type="radio" 
                        aria-label={`Радиус ${r} м`} 
                        checked={r === radius} 
                        onChange={() => setRadius(r)}
                      /> 
                      {r} м
                    </label>
                  </td>
                  <td>{format(b.n)}</td>
                  <td>{format(b.p)} %</td>
                  {a && <td>{format(a.p)} % · {format(a.n)} жителей</td>}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="analysis-note">
        Выбранный радиус используется в показателе парков и сравнении сценариев. 
        Расстояния считаются по пешеходной сети.
      </p>
    </div>
  );
}

export default function AnalyticsPanel({ metrics, radius, setRadius, radii, setRadii }) {
  const m = radiusMetrics(metrics, radius);
  
  return (
    <section className="analytics">
      <div className="section-heading">
        <div>
          <div className="section-kicker">ПОКАЗАТЕЛИ</div>
          <h2>Как меняется город</h2>
        </div>
      </div>
      
      <MetricsPanel before={m} />
      <ParkTable 
        metrics={metrics} 
        radii={radii} 
        radius={radius} 
        setRadius={setRadius} 
        setRadii={setRadii} 
      />
      
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Инфраструктура</th>
              <th>Количество</th>
              <th>Объектов на 1000 жителей</th>
            </tr>
          </thead>
          <tbody>
            {(metrics.provision || []).map(p => (
              <tr key={p.kind}>
                <td>{labels[p.kind]}</td>
                <td>{p.count}</td>
                <td>{new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3 }).format(p.per_1000)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="analysis-note">
        Население условное. Обеспеченность показывает количество объектов, а не их вместимость.
      </p>
      
      {metrics.areas?.length > 0 && (
        <details className="area-summary">
          <summary>Проектные районы ({metrics.areas.length})</summary>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Район</th>
                  <th>Домов</th>
                  <th>Условных жителей</th>
                </tr>
              </thead>
              <tbody>
                {metrics.areas.map(a => (
                  <tr key={a.id}>
                    <td>{a.name}</td>
                    <td>{a.home_count}</td>
                    <td>{format(a.residents)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  );
}


