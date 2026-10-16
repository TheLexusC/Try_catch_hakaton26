import React from 'react';
export const format = value => value === null || value === undefined ? '—' : new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 1}).format(value);
export default function MetricsPanel({before, after, compact = false}) {
  if (!before) return null;
  const active = after || before;
  const entries = [
    {label:'До ближайшей остановки',key:'average_stop',unit:'м',note:'Среднее по доступным домам',lower:true},
    {label:'Жители рядом с парком',key:'park_percent',unit:'%',note:'Не дальше 500 м по сети',lower:false},
    {label:'Дома без пути к остановке',key:'unreachable_homes',unit:'из 5',note:'Учитываем недоступные маршруты',lower:true},
  ];
  return <div className={'metrics-grid ' + (compact ? 'compact' : '')}>
    {entries.map(item => {
      const prev=before[item.key], next=active[item.key];
      const delta=prev!==null&&next!==null ? Math.round((next-prev)*10)/10 : null;
      const good=delta!==null&&(item.lower?delta<0:delta>0);
      return <article className="metric" key={item.key}>
        <p className="metric-label">{item.label}</p>
        <div className="metric-value">{after && <span className="old-value">{format(prev)} → </span>}{format(next)} <small>{item.unit}</small></div>
        <div className="metric-bottom"><span>{item.note}</span>{after&&delta!==null&&<b className={delta===0?'neutral':good?'positive':'negative'}>{delta>0?'+':''}{format(delta)}{item.key==='park_percent'?' п.п.':''}</b>}</div>
      </article>;
    })}
  </div>;
}
