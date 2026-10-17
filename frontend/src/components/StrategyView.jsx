import React,{useEffect,useMemo,useState} from 'react';
import CityMap from './CityMap.jsx';
import {directions,phases,strategySource,phaseForYear,milestoneForYear,relatedBuildings,streetFeatures} from '../strategy.js';
const number=n=>n.toLocaleString('ru-RU');
export default function StrategyView({city}){
  const [year,setYear]=useState(2025),[selected,setSelected]=useState('all');
  const [onlyRelated,setOnlyRelated]=useState(true),[showBuildings,setShowBuildings]=useState(true);
  const [context,setContext]=useState({features:[]}),[error,setError]=useState('');
  useEffect(()=>{let cancelled=false;fetch('/api/map/context').then(r=>{if(!r.ok)throw Error('Не удалось загрузить привязки улиц.');return r.json();}).then(data=>{if(!cancelled)setContext(data);}).catch(e=>{if(!cancelled)setError(e.message);});return()=>{cancelled=true;};},[]);
  const phase=phaseForYear(year),target=milestoneForYear(year);
  const houses=useMemo(()=>relatedBuildings(city.state.objects,selected),[city.state.objects,selected]);
  const ids=useMemo(()=>showBuildings?houses.map(h=>h.id):[],[houses,showBuildings]);
  const features=useMemo(()=>streetFeatures(context,selected),[context,selected]);
  const state=useMemo(()=>onlyRelated?{...city.state,objects:showBuildings?houses:[],areas:[],demolished:[]}:city.state,[city.state,onlyRelated,showBuildings,houses]);
  return <section className="strategy-view">
    <div className="section-kicker">ГОСУДАРСТВЕННОЕ И МУНИЦИПАЛЬНОЕ СТРАТЕГИЧЕСКОЕ ПЛАНИРОВАНИЕ</div>
    <div className="strategy-heading"><div><h1>Стратегия города по годам</h1><p>{strategySource.title}</p></div><span className="strategy-readonly">Только просмотр</span></div>
    <p className="strategy-source">{strategySource.decision}. {strategySource.original}. <a href={strategySource.file} download>Скачать исходный документ (.doc)</a> · <a href={strategySource.url} target="_blank" rel="noreferrer">Официальная публикация</a></p>
    <details className="strategy-legal"><summary>Гос. планирование и указы Президента РФ — основание стратегии</summary><p>Это муниципальная стратегия. Во введении указано, что она разработана в соответствии со следующими указами Президента Российской Федерации:</p><ul>{strategySource.decrees.map(d=><li key={d.number}>Указ Президента РФ от {d.date} № {d.number} — {d.title}.</li>)}</ul><p>Само решение № 01-49 принято городским Собранием; оно не является указом Президента РФ.</p></details>
    <div className="strategy-year-panel">
      <label>Год просмотра <select aria-label="Год стратегии" value={year} onChange={e=>setYear(Number(e.target.value))}>{Array.from({length:16},(_,i)=>2025+i).map(y=><option key={y}>{y}</option>)}</select></label>
      <input aria-label="Шкала года стратегии" type="range" min="2025" max="2040" step="1" value={year} onChange={e=>setYear(Number(e.target.value))}/>
      <div className="strategy-phases">{phases.map(p=><button type="button" className={phase.id===p.id?'active':''} key={p.id} onClick={()=>setYear(p.start)} aria-pressed={phase.id===p.id}>{p.start}–{p.end}<small>Этап {p.id}</small></button>)}</div>
      <h2 style={{color:phase.color}}>{year} · этап {phase.id}: {phase.title}</h2><p>{phase.description}</p>
      <p className="strategy-note">В источнике сроки заданы этапами. Отдельные годы внутри одного этапа показывают одну программу; срок конкретного проекта не назначен. Это планы предоставленной стратегии 2025–2040, а не отчёт о выполненных работах.</p>
    </div>
    <div className="strategy-targets" aria-label="Целевые показатели стратегии">
      <div><small>Население к {target.year} году</small><strong>{number(target.population)} чел.</strong></div>
      <div><small>Численность работающих к {target.year} году</small><strong>{number(target.employment)} чел.</strong></div>
      <div><small>Инвестиции в основной капитал: прогноз на {target.year} год</small><strong>{number(target.investment)} млрд ₽</strong></div>
    </div>
    <p className="strategy-note">Прогнозные значения из приложения Д. Они не заменяют население рабочей модели 133 000 и не интерполируются между контрольными годами.</p>
    <div className="strategy-layout"><aside className="strategy-projects"><h2>Направления стратегии</h2><button type="button" className={'secondary '+(selected==='all'?'selected':'')} onClick={()=>setSelected('all')}>Все направления</button>{directions.map(d=><button type="button" className={'strategy-project '+(selected===d.id?'selected':'')} key={d.id} onClick={()=>setSelected(d.id)} aria-pressed={selected===d.id}><strong>{d.title}</strong><span>{d.description}</span><small>{d.section}</small><small>{d.location}</small><b>{d.streets||d.extra||d.objectIds?'Есть ориентир на карте':'Без точной геопривязки'}</b><small>Индивидуальный срок не указан</small></button>)}</aside>
      <div className="strategy-map-column"><div className="strategy-map-controls">
        <h2>Территории и здания, связанные с планом</h2>
        <label><input type="checkbox" checked={onlyRelated} onChange={e=>setOnlyRelated(e.target.checked)}/>Показать только объекты выбранного направления</label>
        <label><input type="checkbox" checked={showBuildings} onChange={e=>setShowBuildings(e.target.checked)}/>Выделить связанные здания по адресу ({houses.length})</label>
        <p>Цветные линии и маркеры — существующие ориентиры территории. Выделенные контуры — существующие здания по адресам улиц и названных объектов. Это не утверждённые границы работ и не перечень изменённых домов.</p>
        <p><b>Изменённые дома:</b> адреса и годы реконструкции жилых домов в документе не перечислены. Названные музей и туристические объекты выделяются как направления будущих работ. Будущее состояние отдельных домов по годам не задано; подложка и здания — текущая модель OSM.</p>
        {!features.length&&<p role="status">У выбранного направления нет подтверждённой привязки на карте.</p>}{error&&<p role="alert">{error}</p>}
      </div><CityMap state={state} metrics={city.metrics} readOnly mode="inspect" setSelectedHome={()=>{}} highlightIds={ids} highlightColor={phase.color} strategyFeatures={features}/></div>
    </div>
  </section>;
}
