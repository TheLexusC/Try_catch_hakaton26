import React from 'react';
import { affectedMetrics } from './affectedMetrics.js';

export const format = value => 
  value === null || value === undefined 
    ? '—' 
    : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(Object.is(value, -0) ? 0 : value);

function Card({ label, prev, next, unit, note, compare = false, digits = 1 }) {
  const display = n => 
    n === null || n === undefined 
      ? 'Нет данных' 
      : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits }).format(n);
      
  const showCompare = compare && prev !== null && prev !== undefined && prev !== next;
  
  return (
    <article className="metric">
      <p className="metric-label">{label}</p>
      <div className="metric-value">
        {showCompare && <span className="old-value">{display(prev)} → </span>}
        {display(next)} 
        <small>{next !== null && next !== undefined ? unit : ''}</small>
      </div>
      <div className="metric-bottom">
        <span>{compare && prev === next ? 'Показатель не изменился. ' : ''}{note}</span>
      </div>
    </article>
  );
}

export default function MetricsPanel({ before, after, compact = false }) {
  if (!before) return null;
  
  const active = after || before;
  const a = after ? affectedMetrics(before, after) : null;
  const radius = active.radius || 500;
  
  const cityTransport = active.rows
    .filter(h => h.stop_distance !== null && h.stop_distance <= 500)
    .reduce((n, h) => n + h.residents, 0);
    
  const count = (active.provision || []).reduce((n, p) => n + p.count, 0);
  const newHomes = a?.newHomes;
  
  return (
    <>
      {a && (
        <>
          <p className="affected-caption">
            Изменились маршруты или население у {format(a.count)} существующих домов. Новых домов: {a.added}; снесено: {a.removed}. Новые жители показаны отдельно — до строительства их в модели не было.
          </p>
          <div className="city-metric-corner">
            <span>Весь город: путь до остановки {format(before.average_stop)} → {format(after.average_stop)} м</span>
          </div>
        </>
      )}
      
      {a?.count > 0 && (
        <>
          <h3 className="metrics-scope-title">Существующие дома, которых затронул проект</h3>
          <div className={`metrics-grid ${compact ? 'compact' : ''}`}>
            <Card 
              label="Путь до остановки — затронутые дома" 
              prev={a.before.average_stop} 
              next={a.after.average_stop} 
              compare 
              unit="м" 
              note={`Средний пеший маршрут по одной группе из ${a.count} домов до и после проекта.`}
            />
            <Card 
              label="Доступ к парку — затронутые жители" 
              prev={a.before.park_percent} 
              next={a.after.park_percent} 
              compare 
              unit="%" 
              note={`В ${radius} м пешком: было ${format(a.before.park_residents)} из ${format(a.before.residents)}, стало ${format(a.after.park_residents)} из ${format(a.after.residents)} жителей.`}
            />
          </div>
        </>
      )}
      
      {newHomes?.home_count > 0 && (
        <>
          <h3 className="metrics-scope-title">Новые дома: условия после строительства</h3>
          <div className={`metrics-grid ${compact ? 'compact' : ''}`}>
            <Card 
              label="Новые жители с парком рядом" 
              next={newHomes.park_percent} 
              unit="%" 
              note={`${format(newHomes.park_residents)} из ${format(newHomes.residents)} новых жителей смогут дойти до парка за ${radius} м.${newHomes.park_percent === 0 ? ' Ни один новый дом не имеет такого короткого маршрута.' : ''}`}
            />
            <Card 
              label="Новые жители с остановкой рядом" 
              next={newHomes.transport_access} 
              unit="%" 
              note={`${format(newHomes.stop_residents)} из ${format(newHomes.residents)} новых жителей живут в 500 м пешком от остановки. Учитываются дорожки проекта.`}
            />
            <Card 
              label="От новых домов до остановки" 
              next={newHomes.average_stop} 
              unit="м" 
              note="Средний маршрут по пешеходной сети. Добавьте остановку и дорожки от домов к ней, чтобы сократить путь."
            />
          </div>
        </>
      )}
      
      <h3 className="metrics-scope-title">Весь город</h3>
      <div className={`metrics-grid ${compact ? 'compact' : ''}`}>
        {!after && (
          <Card 
            label="До ближайшей остановки" 
            next={active.average_stop} 
            unit="м" 
            note="Средний пеший маршрут по всем доступным домам города."
          />
        )}
        <Card 
          label="Жители с парком рядом — весь город" 
          prev={before.park_percent} 
          next={active.park_percent} 
          compare={!!after} 
          unit="%" 
          note={`${format(active.accessible_residents)} из ${format(active.total_residents)} жителей имеют маршрут к парку не длиннее ${radius} м.`}
        />
        <Card 
          label="Жители с остановкой рядом — весь город" 
          prev={before.transport_access} 
          next={active.transport_access} 
          compare={!!after} 
          unit="%" 
          note={`${format(cityTransport)} из ${format(active.total_residents)} жителей живут в 500 м пешком от остановки. При появлении удалённых домов доля может снизиться.`}
        />
        <Card 
          label="Объекты на 1000 жителей — весь город" 
          prev={before.facility_provision} 
          next={active.facility_provision} 
          compare={!!after} 
          unit="на 1000" 
          digits={3} 
          note={`${format(count)} объектов ÷ ${format(active.total_residents)} жителей × 1000. Число остановок, парков, школ и других объектов; при росте населения без новых объектов показатель падает.`}
        />
      </div>
    </>
  );
}


