import React from 'react';

// Распакованная функция форматирования для лучшей читаемости
export const format = (value) => {
  if (value === null || value === undefined) {
    return '—';
  }
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value);
};

export default function MetricsPanel({ before, after, compact = false }) {
  if (!before) return null;
  
  const active = after || before;
  
  // Структурированный массив метрик
  const entries = [
    {
      label: 'До ближайшей остановки',
      key: 'average_stop',
      unit: 'м',
      note: 'Среднее по доступным домам',
      lower: true
    },
    {
      label: 'Жители рядом с парком',
      key: 'park_percent',
      unit: '%',
      note: 'Не дальше 500 м по сети',
      lower: false
    },
    {
      label: 'Дома без пути к остановке',
      key: 'unreachable_homes',
      unit: 'из 5',
      note: 'Учитываем недоступные маршруты',
      lower: true
    },
  ];

  return (
    <div className={`metrics-grid ${compact ? 'compact' : ''}`}>
      {entries.map((item) => {
        const prev = before[item.key];
        const next = active[item.key];
        
        // Вычисляем разницу
        const delta = (prev !== null && next !== null) 
          ? Math.round((next - prev) * 10) / 10 
          : null;
          
        // Определяем, является ли динамика положительной (учитывая флаг lower)
        const isGood = delta !== null && (item.lower ? delta < 0 : delta > 0);
        
        // Определяем класс для цветовой индикации
        let deltaClass = '';
        if (delta === 0) deltaClass = 'neutral';
        else if (isGood) deltaClass = 'positive';
        else deltaClass = 'negative';

        return (
          <article className="metric" key={item.key}>
            <p className="metric-label">{item.label}</p>
            
            <div className="metric-value">
              {after && <span className="old-value">{format(prev)} → </span>}
              {format(next)} <small>{item.unit}</small>
            </div>
            
            <div className="metric-bottom">
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


