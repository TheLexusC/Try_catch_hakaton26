import React from 'react';

export const format = (value) => {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value);
};

export default function MetricsPanel({ before, after, compact = false }) {
  if (!before) return null;
  const active = after || before;
  
  // НОВОЕ: добавлен параметр `max` для вычисления визуальной заполненности шкалы
  const entries = [
    {
      label: 'До ближайшей остановки',
      key: 'average_stop',
      unit: 'м',
      note: 'Среднее по доступным домам',
      lower: true,
      max: 1000 // Предполагаемый максимум для шкалы в метрах
    },
    {
      label: 'Жители рядом с парком',
      key: 'park_percent',
      unit: '%',
      note: 'Не дальше 500 м по сети',
      lower: false,
      max: 100 // Максимум в процентах
    },
    {
      label: 'Дома без пути к остановке',
      key: 'unreachable_homes',
      unit: 'из 5',
      note: 'Учитываем недоступные маршруты',
      lower: true,
      max: 5 // Максимум домов
    },
  ];

  return (
    <div className={`metrics-grid ${compact ? 'compact' : ''}`}>
      {entries.map((item) => {
        const prev = before[item.key];
        const next = active[item.key];
        
        const delta = (prev !== null && next !== null) 
          ? Math.round((next - prev) * 10) / 10 
          : null;
          
        const isGood = delta !== null && (item.lower ? delta < 0 : delta > 0);
        
        let deltaClass = 'neutral';
        if (delta !== 0 && delta !== null) {
          deltaClass = isGood ? 'positive' : 'negative';
        }

        // НОВОЕ: Высчитываем ширину шкалы прогресса (от 0 до 100%)
        const fillPercentage = next !== null 
          ? Math.min((next / item.max) * 100, 100) 
          : 0;

        return (
          <article className="metric" key={item.key}>
            <p className="metric-label">{item.label}</p>
            
            <div className="metric-value">
              {after && <span className="old-value">{format(prev)} → </span>}
              {format(next)} <small>{item.unit}</small>
            </div>
            
            {/*(Progress Bar) */}
            <div 
              className="metric-progress-bg" 
              style={{ width: '100%', height: '4px', background: '#e0e0e0', borderRadius: '2px', marginTop: '8px', overflow: 'hidden' }}
            >
              <div 
                className={`metric-progress-fill ${deltaClass}`}
                style={{ 
                  width: `${fillPercentage}%`, 
                  height: '100%', 
                  background: deltaClass === 'positive' ? '#4caf50' : deltaClass === 'negative' ? '#f44336' : '#2196f3',
                  transition: 'width 0.4s ease-out, background-color 0.4s ease' 
                }} 
              />
            </div>

            <div className="metric-bottom" style={{ marginTop: '8px' }}>
              <span>{item.note}</span>
              {after && delta !== null && (
                <b className={deltaClass}>
                  {delta > 0 ? '+' : ''}
                  {format(delta)}
                  {item.key === 'park_percent' ? ' п.п.' : ''}
                </b>
              )}
            </div>
          </article>
        );
      })}
    </div>
  );
}
