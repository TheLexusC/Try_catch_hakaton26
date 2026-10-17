import React, {useCallback,useEffect,useRef,useState,useId} from 'react';
import {newId} from './ids.js';
import DistrictBuilder from './components/DistrictBuilder.jsx';
import CityMap,{kinds} from './components/CityMap.jsx';
import AnalyticsPanel,{radiusMetrics,ParkTable} from './components/AnalyticsPanel.jsx';
import ScenarioWorkbench from './components/ScenarioWorkbench.jsx';
import ControlPanel from './components/ControlPanel.jsx';
import PlanningPanel,{Estimate,money,actionLabel} from './components/PlanningPanel.jsx';
import ProposalHistory from './components/ProposalHistory.jsx';
import MetricsPanel,{format} from './components/MetricsPanel.jsx';

const names={object:'Объект',edge:'Дорожка',node:'Узел',area:'Район',road:'Дорожка'};
const operations={add:'Добавление',update:'Изменение',delete:'Удаление'};
const statuses={pending:'На модерации',approved:'Одобрена · закрыта',rejected:'Отклонена · закрыта'};
const date=value=>new Date(value).toLocaleString('ru-RU');
const title=a=>`${operations[a.operation]}: ${a.values?.name||names[a.entity]} · ${a.id.slice(0,10)}`;
function Dialog({title,onClose,locked,children,narrow=false,variant=''}){
  const ref=useRef(),titleId=useId();
  useEffect(()=>{const d=ref.current;d.showModal();return()=>d.close();},[]);
  return <dialog ref={ref} className={"dialog "+(narrow?"narrow":"wide")+" "+variant} aria-labelledby={titleId} onCancel={e=>{e.preventDefault();if(!locked)onClose();}}><div className="dialog-inner"><div className="dialog-top"><h2 id={titleId}>{title}</h2><button className="icon-button" aria-label="Закрыть окно" disabled={locked} onClick={onClose}>×</button></div>{children}</div></dialog>;
}

export default function App(){
  const [city,setCity]=useState(null),[session,setSession]=useState(null),[mode,setMode]=useState('inspect'),[tab,setTab]=useState('map');
  const [focusRequest,setFocusRequest]=useState(0),[movingStop,setMovingStop]=useState(null);
  const [home,setHome]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [auth,setAuth]=useState(null),[items,setItems]=useState([]),[editor,setEditor]=useState(null),[reason,setReason]=useState('');
  const [review,setReview]=useState(null),[reviewPreview,setReviewPreview]=useState(null),[comment,setComment]=useState(''),[formError,setFormError]=useState('');
  const [bundle,setBundle]=useState({actions:[],base_version:0}),[removeIndex,setRemoveIndex]=useState(null);
  const [radius,setRadius]=useState(500),[radii,setRadii]=useState([100,200,300,500,1000]),[rules,setRules]=useState(false),[mapFocus,setMapFocus]=useState(null);
  const [creativeDone,setCreativeDone]=useState(false);
  const [resetAction,setResetAction]=useState(null),[pickingPlace,setPickingPlace]=useState(false),[buildingDistrict,setBuildingDistrict]=useState(false),[districtBusy,setDistrictBusy]=useState(false);
  const mapCenter=useRef({x:3900,y:5343});
  const [scenarioSave,setScenarioSave]=useState(null),[scenarioName,setScenarioName]=useState(''),[scenarioRevision,setScenarioRevision]=useState(0);
  const user=session?.user;
  const canModerate=['moderator','admin'].includes(user?.role);
  useEffect(()=>{
    setEditor(null);setRemoveIndex(null);
    try{const saved=JSON.parse(localStorage.getItem('obninsk-bundle:'+user?.id)||'null');setBundle(user&&saved&&Array.isArray(saved.actions)&&saved.actions.length<=20?saved:{actions:[],base_version:0});}
    catch{setBundle({actions:[],base_version:0});}
  },[user?.id]);
  const storeBundle=next=>{setBundle(next);if(user)try{localStorage.setItem('obninsk-bundle:'+user.id,JSON.stringify(next));}catch{setNotice('Черновик доступен до закрытия страницы: браузер не разрешил сохранение.');}};

  const focusHome=id=>{setHome(id);setFocusRequest(n=>n+1);};
  const api=useCallback(async(path,payload)=>{
    const response=await fetch('/api'+path,{credentials:'same-origin',...(payload===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session?.csrf_token||''},body:JSON.stringify(payload)})});
    let result;try{result=await response.json();}catch{throw Error('Не удалось прочитать ответ сервера. Проверьте запуск backend.');}
    if(!response.ok){const e=Error(typeof result.detail==='string'?result.detail:'Проверьте обязательные поля и выбранные объекты.');e.status=response.status;throw e;}
    return result;
  },[session?.csrf_token]);
  const loadCity=useCallback(async()=>{const next=await api('/city');next.state.objects=next.state.objects.map(o=>({...o,demolition:next.demolition_costs?.[o.id]}));setCity(next);setHome(current=>next.metrics.rows.some(h=>h.id===current)?current:(next.metrics.rows.find(h=>h.name.includes('Курчатова, 17'))?.id||next.metrics.rows[0]?.id));return next;},[api]);
  const loadRequests=useCallback(async()=>{const r=await api('/proposals');setItems(r.items);},[api]);
  useEffect(()=>{loadCity().catch(e=>setError(e.message));api('/auth/me').then(setSession).catch(e=>{if(e.status!==401)setError(e.message);});},[]);
  useEffect(()=>{if(user)loadRequests().catch(e=>setError(e.message));else setItems([]);},[user?.id,loadRequests]);
  const run=async fn=>{setBusy(true);setError('');try{await fn();}catch(e){setError(e.message);}finally{setBusy(false);}};
  const refresh=()=>run(async()=>{await loadCity();if(user){setSession(await api('/auth/me'));await loadRequests();}setNotice('Данные PostgreSQL обновлены.');});
  const login=type=>{setFormError('');setAuth(type);};
  const authenticate=async e=>{
    e.preventDefault();const fields=new FormData(e.currentTarget);const payload=Object.fromEntries(fields);setBusy(true);setFormError('');
    try{setSession(await api('/auth/'+auth,payload));setAuth(null);setNotice('Вы вошли. Теперь можно отправлять изменения на модерацию.');}catch(e){setFormError(e.message);}finally{setBusy(false);}
  };
  const logout=()=>run(async()=>{await api('/auth/logout',{});setSession(null);setTab('map');});
  const openEditor=(entity,operation,item={})=>{
    if(!user){login('login');return;}if(entity==='object'&&operation==='delete'&&item.demolition?.allowed===false){setError(item.demolition.reason);return;}if(bundle.actions.length>=20){setError('В наборе уже 20 изменений. Удалите одно или отправьте набор.');return;}
    const {id,...values}=item;
    setEditor({action:{entity,operation,id:id||newId(entity[0]),values:operation==='delete'?{}:values},base_version:bundle.actions.length?bundle.base_version:city.state.version});
    setPickingPlace(false);setReason('');setFormError('');loadRequests().catch(e=>setFormError(e.message));
  };
  const moveStop=stop=>{if(!user){login('login');return;}setMovingStop(stop);setMode('move_stop');};
  const changeMode=value=>{if(value!=='inspect'&&!user){login('login');return;}if(value==='add_area'){try{localStorage.removeItem('obninsk-district:'+user.id);}catch{}setDistrictBusy(false);setBuildingDistrict(true);return;}setMode(value);if(value!=='move_stop')setMovingStop(null);if(['add_home','add_area','add_object'].includes(value))setNotice('Режим создания включён. Нажмите в нужное место на карте, в том числе в лесу или на пустом участке.');};
  const place=(point,tool=mode)=>{if(tool==='add_area'){openEditor('area','add',{name:'Новый район',width:600,height:600,...point});return;}if(tool==='add_home'){openEditor('object','add',{name:'Новый жилой дом',kind:'home',width:20,height:30,residents:100,...point});return;}if(tool==='move_stop'){if(movingStop)openEditor('object','update',{id:movingStop.id,...point});return;}openEditor('object','add',{name:'Новый парк',kind:'park',...point});};
  const select=(entity,item)=>entity==='edge'?openEditor('edge','update',{id:item.id,closed:!item.closed}):openEditor('object','delete',item);
  const updateField=(key,value)=>setEditor(current=>{
    const values={...current.action.values,[key]:value};
    if(key==='kind'){const defaults={home:'Новый жилой дом',park:'Новый парк',stop:'Новая остановка',parking:'Новая парковка',greenery:'Новое озеленение',school:'Новая школа',clinic:'Новая поликлиника',shop:'Новый магазин'};if(Object.values(defaults).includes(current.action.values.name)||current.action.values.name==='Новая зелёная зона')values.name=defaults[value];delete values.width;delete values.height;delete values.residents;if(value==='home')Object.assign(values,{width:20,height:30,residents:100});}
    return {...current,action:{...current.action,values}};
  });
  const focusObject=obj=>{if(obj.kind==='home')focusHome(obj.id);setMapFocus({id:obj.id,nonce:Date.now()});};
  const beginSaveScenario=data=>{setScenarioName('Вариант '+(scenarioRevision+1));setScenarioSave({actions:data.actions,base_version:data.base_version});setFormError('');};
  const saveScenario=async e=>{e.preventDefault();setBusy(true);setFormError('');try{await api('/scenarios',{...scenarioSave,name:scenarioName});setScenarioRevision(n=>n+1);setScenarioSave(null);setNotice('Сценарий сохранён. Он доступен в разделе сравнения.');}catch(e){setFormError(e.message);}finally{setBusy(false);}};
  const openScenario=id=>run(async()=>{
    const preview=await api(`/scenarios/${id}/evaluate`,{park_radius:radius,park_radii:radii});
    await loadCity();storeBundle({actions:preview.actions,base_version:preview.base_version});
    setCreativeDone(false);setReason('');setFormError('');setEditor({batch:true,action:preview.actions.at(-1),plannedActions:preview.actions,base_version:preview.base_version,preview});
  });
  const prepareActions=async actions=>{
    const homes=actions.filter(a=>a.entity==='object'&&a.operation==='add'&&a.values.kind==='home');if(!homes.length)return actions;
    const houses=homes.map(a=>({id:a.id,...Object.fromEntries(['name','x','y','width','height','residents','points','rotation'].map(k=>[k,a.values[k]]))}));
    const fitted=(await api('/layout/fit',{houses})).houses;
    return actions.map(a=>{const h=fitted.find(h=>h.id===a.id);return h?{...a,values:{...a.values,x:h.x,y:h.y,points:h.points,rotation:h.rotation}}:a;});
  };
  const sendDirect=async e=>{
    e.preventDefault();setBusy(true);setFormError('');
    try{const r=await api('/proposals',{actions:await prepareActions([...bundle.actions,editor.action]),base_version:editor.base_version,reason:reason.trim()});setEditor(null);setPickingPlace(false);storeBundle({actions:[],base_version:city.state.version});setMode('inspect');setTab('requests');setNotice('Заявка отправлена на модерацию. Номер: '+r.id.slice(0,8));await loadRequests();}catch(e){setFormError(e.message);}finally{setBusy(false);}
  };
  const addToProject=async()=>{if(bundle.actions.length>=20){setFormError('В проекте уже 20 изменений.');return;}setBusy(true);setFormError('');try{const actions=await prepareActions([...bundle.actions,editor.action]);storeBundle({actions,base_version:editor.base_version});setEditor(null);setPickingPlace(false);setMode('inspect');setNotice('Добавлено в проект. Расчёт всех изменений — кнопкой «Завершить и рассчитать».');}catch(e){setFormError(e.message);}finally{setBusy(false);}};
  const previewChange=async e=>{
    if(e.nativeEvent.submitter?.value==='send'){await sendDirect(e);return;}
    e.preventDefault();setBusy(true);setFormError('');
    try{const plannedActions=await prepareActions(editor.batch?bundle.actions:[...bundle.actions,editor.action]);const preview=await api('/preview',{actions:plannedActions,base_version:editor.base_version});setCreativeDone(false);setEditor(current=>({...current,preview,plannedActions}));}catch(e){setFormError(e.message);}finally{setBusy(false);}
  };
  const submit=async e=>{
    e.preventDefault();if(busy)return;
    if(!editor?.plannedActions?.length){setFormError('Сначала рассчитайте изменение.');return;}
    if(!editor.preview?.estimate?.can_submit){setFormError(editor.preview.estimate.blocked.map(b=>b.reason).join('; ')||'Снос запрещён по цене');return;}
    setBusy(true);setFormError('');
    try{
      const sentActions=editor.plannedActions;
      const r=await api('/proposals',{actions:sentActions,base_version:editor.base_version,reason:reason.trim()});
      const localItem={id:r.id,author_id:user.id,author_name:user.name,actions:sentActions,action:{actions:sentActions},status:'pending',reason:reason.trim()||'Предложение изменений городской инфраструктуры.',base_version:editor.base_version,created_at:new Date().toISOString(),estimated_cost:editor.preview.estimate.total,target_name:sentActions.length>1?`Набор из ${sentActions.length} изменений`:editor.preview.estimate.lines[0].name};
      setItems(current=>[localItem,...current.filter(i=>i.id!==r.id)]);
      setEditor(null);storeBundle({actions:[],base_version:city.state.version});setMode('inspect');setNotice('Заявка отправлена на модерацию. Номер: '+r.id.slice(0,8));setTab('requests');
      loadRequests().catch(e=>setError('Заявка отправлена, но список не обновился: '+e.message));
    }catch(e){setFormError(e.message);}finally{setBusy(false);}
  };
  const removeDraft=async()=>{
    const next={...bundle,actions:bundle.actions.filter((_,i)=>i!==removeIndex)};
    if(!next.actions.length)next.base_version=city.state.version;
    storeBundle(next);setRemoveIndex(null);
    if(!editor)return;
    const actions=editor.batch?next.actions:[...next.actions,editor.action];
    if(!actions.length){setEditor(null);return;}
    const base_version=next.actions.length?next.base_version:city.state.version;
    setEditor(current=>({...current,action:current.batch?actions.at(-1):current.action,base_version,preview:null,plannedActions:null}));
    if(editor.preview){
      setBusy(true);setFormError('');
      try{const preview=await api('/preview',{actions,base_version});setEditor(current=>current?{...current,preview,plannedActions:actions}:current);}
      catch(e){setFormError(e.message);}finally{setBusy(false);}
    }
  };
  const addMore=()=>{storeBundle({actions:editor.plannedActions,base_version:editor.base_version});setEditor(null);setMode('inspect');setNotice('Изменения сохранены в наборе. Выберите следующее действие на карте.');};
  const previewBundle=()=>run(async()=>{
    const preview=await api('/preview',{actions:bundle.actions,base_version:bundle.base_version});
    setCreativeDone(false);setReason('');setFormError('');setEditor({batch:true,action:bundle.actions.at(-1),plannedActions:bundle.actions,base_version:bundle.base_version,preview});
  });
  const saveBudget=e=>{e.preventDefault();const limit=Number(new FormData(e.currentTarget).get('limit'));run(async()=>{await api('/demolition-policy',{limit});await loadCity();setNotice('Порог стоимости сноса одного здания сохранён.');});};
  const openReview=async item=>{
    setReview(item);setReviewPreview(null);setComment('');setFormError('');setBusy(true);
    try{setReviewPreview(await api(`/proposals/${item.id}/preview`));}catch(e){setFormError(e.message);}finally{setBusy(false);}
  };
  const decide=async decision=>{
    setBusy(true);setFormError('');
    try{await api(`/proposals/${review.id}/decision`,{decision,comment:comment.trim()||(decision==='approved'?'Одобрено.':'Отклонено.')});setReview(null);await loadCity();await loadRequests();setNotice('Решение сохранено. Заявка закрыта.');}catch(e){setFormError(e.message);}finally{setBusy(false);}
  };
  const closeDistrict=()=>{try{localStorage.removeItem('obninsk-district:'+user.id);}catch{}setBuildingDistrict(false);setDistrictBusy(false);setMode('inspect');setNotice('Неотправленный район отменён. Можно начать новый.');};
  const resetDemo=()=>run(async()=>{await api('/admin/demo-reset',{action:resetAction});setResetAction(null);setEditor(null);setPickingPlace(false);setMode('inspect');setMovingStop(null);try{for(const key of Object.keys(localStorage))if((key.startsWith('obninsk-bundle:')||key.startsWith('obninsk-district:')))localStorage.removeItem(key);}catch{}storeBundle({actions:[],base_version:0});setScenarioRevision(n=>n+1);await loadCity();await loadRequests();setNotice('Готово. Карта и список заявок обновлены.');});
  const pending=items.filter(i=>i.status==='pending').length;
  const draftState=city?{...city.state,objects:city.state.objects.filter(o=>!bundle.actions.some(a=>a.entity==='object'&&a.operation==='delete'&&a.id===o.id)).map(o=>{const a=bundle.actions.find(a=>a.entity==='object'&&a.operation==='update'&&a.id===o.id);return a?{...o,...a.values,geom:null}:o;}).concat(bundle.actions.filter(a=>a.entity==='object'&&a.operation==='add').map(a=>{const v=a.values;const scale=111320*Math.cos(55.11*Math.PI/180);const p=(x,y)=>[36.55+x/scale,55.06+y/111320];const geom=v.points?{type:'Polygon',coordinates:[[...v.points,v.points[0]].map(p=>[36.55+p.x/scale,55.06+p.y/111320])]}:v.kind==='home'?{type:'Polygon',coordinates:[[[v.x-v.width/2,v.y-v.height/2],[v.x+v.width/2,v.y-v.height/2],[v.x+v.width/2,v.y+v.height/2],[v.x-v.width/2,v.y+v.height/2],[v.x-v.width/2,v.y-v.height/2]].map(([x,y])=>p(x,y))]}:null;return {...v,id:a.id,source:'proposal',geom};}))}:null;
  const selected=city?.metrics.rows.find(r=>r.id===home)||city?.metrics.rows[0];
  const action=editor?.action, values=action?.values;



  return <>
    <header className="site-header"><a className="brand" href="/"><span className="brand-mark">о<span>↗</span></span><span>ОБНИНСК <b>2040</b><small>КОНСТРУКТОР ГОРОДА</small></span></a><nav aria-label="Навигация"><button className={tab==='map'?'nav-active':''} onClick={()=>setTab('map')}>Карта города</button><button className={tab==='requests'?'nav-active':''} onClick={()=>{setTab('requests');if(user)loadRequests().catch(e=>setError(e.message));}}>{canModerate?'Модерация':'Мои заявки'} {pending>0&&<span className="count">{pending}</span>}</button></nav><div className="account">{user?<><span className="account-name">{user.name}<small>{user.role==='admin'?'Администратор':canModerate?'Модератор':'Житель'}</small></span><button className="text-button" disabled={busy} onClick={logout}>Выйти</button></>:<><button className="text-button" onClick={()=>login('login')}>Войти</button><button className="primary small" onClick={()=>login('register')}>Регистрация</button></>}</div></header>
    <main>
      {error&&<div className="banner error" role="alert">{error}<button aria-label="Скрыть ошибку" onClick={()=>setError('')}>×</button></div>}
      {notice&&<div className="banner success" role="status">{notice}<button aria-label="Скрыть уведомление" onClick={()=>setNotice('')}>×</button></div>}
      {tab==='map'?<>
        <section className="hero"><div><div className="eyebrow"><span className="live-dot"/> ОБНИНСК · РЕАЛЬНАЯ КАРТА ГОРОДА</div><h1>Обнинск 2040.<br/><span>План развития.</span></h1><p>Дома, районы и инфраструктура.<br/>Проверьте свой вариант на карте.</p></div><div className="hero-aside"><div className="coordinate">55.1080° N<br/>36.6120° E</div><div className="hero-stats"><div><strong>{city?.state.objects.length??'—'}</strong><span>объектов</span></div><div><strong>{format(city?.metrics.total_residents)}</strong><span>жителей в модели · база 133 000</span></div></div></div></section>
        {!city?<div className="empty-state"><h2>Подключаем район…</h2><p>Запустите PostgreSQL и backend через «Запустить.command».</p><button className="primary" onClick={refresh}>Обновить</button></div>:<>
          {user&&bundle.actions.length>0&&<section className="creative-summary"><div><strong>Ваш проект: {bundle.actions.length} изменений</strong><p>Общая карта пока не изменена. Добавьте всё задуманное, затем рассчитайте общий результат.</p></div><button className="primary" disabled={busy} onClick={previewBundle}>Завершить и рассчитать</button></section>}{user&&<div className="map-request-history"><ProposalHistory items={items} user={user} objects={city.state.objects} busy={busy} onRefresh={()=>loadRequests().catch(e=>setError(e.message))}/></div>}<section className="workspace"><ControlPanel mode={mode} setMode={changeMode} stops={city.state.objects.filter(o=>o.kind==='stop')} movingStop={movingStop} onMoveStop={moveStop} objects={city.state.objects} onFocus={focusObject} onRules={()=>setRules(true)} user={user} onLogin={()=>login('login')} busy={busy}/><CityMap state={draftState} metrics={city.metrics} mode={mode} onSelect={select} onPlace={place} onMapCenter={point=>{mapCenter.current=point;}} onMoveStop={moveStop} movingStopId={movingStop?.id} focusObject={mapFocus} selectedHome={home} setSelectedHome={focusHome} focusRequest={focusRequest}/></section>
          <div className="selection-strip"><span>{selected?<><b>{selected.name}</b> · остановка {format(selected.stop_distance)} м · парк {format(selected.park_distance)} м</>:'В районе пока нет жилых домов'}</span><div className="map-actions"><button onClick={refresh} disabled={busy}>↻ Обновить</button>{user?.role==='admin'&&<button className="danger-button" disabled={busy} onClick={()=>setResetAction('reset_all')}>Сбросить все изменения</button>}</div></div>
          <AnalyticsPanel metrics={city.metrics} radius={radius} setRadius={setRadius} radii={radii} setRadii={setRadii}/>
          <ScenarioWorkbench api={api} user={user} bundle={bundle} revision={scenarioRevision} radius={radius} radii={radii} onSave={beginSaveScenario} onOpen={openScenario}/>
          <PlanningPanel policy={city.state.demolition_policy||{limit:10000000}} user={user} bundle={bundle} objects={city.state.objects} busy={busy} onRemove={setRemoveIndex} onPreview={previewBundle} onBudget={saveBudget}/>

        </>}
      </>:<section className="requests-section"><div className="section-heading"><div><div className="section-kicker">ПРЕДЛОЖЕНИЯ ЖИТЕЛЕЙ</div><h1>{canModerate?'Модерация изменений':'Мои заявки'}</h1>{user?.role==='admin'&&<details className="demo-controls"><summary>Подготовка к защите</summary><p>Аккаунты и порог сноса сохраняются. Перед очисткой создаётся резервная копия.</p><button className="secondary" onClick={()=>setResetAction('reset_all')}>Исходная карта и очистка заявок</button><button className="secondary" onClick={()=>setResetAction('clear_proposals')}>Только очистить все заявки</button><button className="text-button" onClick={()=>setResetAction('undo')}>Отменить последнюю очистку</button></details>}</div><button className="secondary" onClick={refresh} disabled={busy}>↻ Обновить</button></div>{!user?<div className="empty-state"><h2>Войдите для работы с заявками</h2><button className="primary" onClick={()=>login('login')}>Войти</button></div>:items.length===0?<div className="empty-state"><h2>Заявок пока нет</h2><p>Выберите действие на карте и отправьте предложение.</p><button className="primary" onClick={()=>setTab('map')}>Открыть район</button></div>:<div className="request-list">{items.map(item=><article className="request-card" key={item.id}><div className="request-card-top"><span className={'status '+item.status}>{statuses[item.status]}</span><time>{date(item.created_at)}</time></div><h3>{item.target_name||title(item.action)}</h3><p className="request-cost">{money(item.estimated_cost)} · {(item.actions||[item.action]).length} изменений</p><details className="request-changes"><summary>Состав заявки</summary><ol>{(item.actions||[item.action]).map((a,i)=><li key={i}>{actionLabel(a,city?.state.objects||[],item.action_names||{})}</li>)}</ol></details><p className="request-reason">{item.reason}</p>{item.comment&&<div className="decision-note"><b>{item.reviewer_name} · {date(item.closed_at)}</b><p>{item.comment}</p></div>}<div className="request-card-bottom"><span>{item.author_name} · версия {item.base_version}</span>{canModerate&&item.status==='pending'&&<button className="primary small" disabled={busy} onClick={()=>openReview(item)}>Рассмотреть</button>}</div></article>)}</div>}</section>}
      <footer><span>ОБНИНСК <b>2040</b></span><span>Реальная геометрия © OpenStreetMap contributors · ODbL 1.0</span></footer>
    </main>

    {resetAction&&<Dialog narrow title={resetAction==='undo'?'Вернуть данные до очистки?':'Подготовить демонстрацию?'} locked={busy} onClose={()=>setResetAction(null)}><p>{resetAction==='reset_all'?'Вернём исходную карту Обнинска. Все заявки и сохранённые сценарии будут очищены.':resetAction==='clear_proposals'?'Все заявки жителей будут убраны из списка. Карта останется прежней.':'Восстановим карту, заявки и сценарии из последней резервной копии.'} Аккаунты сохраняются.</p><div className="form-actions"><button className="secondary" onClick={()=>setResetAction(null)}>Отмена</button><button className="primary" disabled={busy} onClick={resetDemo}>Подтвердить</button></div></Dialog>}
    {buildingDistrict&&<Dialog title="Новый район: граница, дома и дорожки" locked={districtBusy} onClose={closeDistrict}><DistrictBuilder onCancel={closeDistrict} onBusyChange={setDistrictBusy} draftKey={'obninsk-district:'+user.id} city={city} api={api} onSent={async id=>{setBuildingDistrict(false);setTab('requests');setNotice('Район отправлен на модерацию. Номер: '+id.slice(0,8));await loadRequests();}}/></Dialog>}
    {rules&&<Dialog narrow title="Правила пользования" onClose={()=>setRules(false)}><div className="site-rules"><p>Выбирайте объект на карте или создавайте новый дом, район и инфраструктуру.</p><p>Существующие здания не перетаскиваются. Снос доступен, если цена одного здания не превышает порог.</p><p>Изменения сначала показываются в предпросмотре. «Добавить ещё» собирает набор, «Сохранить сценарий» сохраняет вариант без изменения города.</p><p>Общий план меняется после одобрения. Администратор может рассматривать свои заявки.</p></div></Dialog>}
    {scenarioSave&&<Dialog narrow title="Сохранить сценарий" locked={busy} onClose={()=>setScenarioSave(null)}><form onSubmit={saveScenario}><label className="field">Название<input required maxLength="80" value={scenarioName} onChange={e=>setScenarioName(e.target.value)}/></label>{formError&&<p className="form-error" role="alert">{formError}</p>}<button className="primary full" disabled={busy}>Сохранить вариант</button></form></Dialog>}
    {removeIndex!==null&&<Dialog narrow title="Удалить изменение из набора?" onClose={()=>setRemoveIndex(null)}><p className="dialog-description">{bundle.actions[removeIndex]&&actionLabel(bundle.actions[removeIndex],city?.state.objects||[])}. Общая карта и отправленные заявки не изменятся.</p><div className="form-actions"><button className="secondary" onClick={()=>setRemoveIndex(null)}>Оставить</button><button className="danger-button" onClick={removeDraft}>Подтвердить удаление</button></div></Dialog>}
    {auth&&<Dialog narrow variant="auth-dialog" title={auth==='register'?'Регистрация':'Вход в аккаунт'} locked={busy} onClose={()=>setAuth(null)}><form onSubmit={authenticate}>{auth==='register'&&<label className="field">Имя<input name="name" autoComplete="name"/></label>}<label className="field">Email<input name="email" type="email" required placeholder="name@obninsk.test" autoComplete="email"/></label><label className="field">Пароль<input name="password" type="password" autoComplete={auth==='register'?'new-password':'current-password'}/></label><p className="form-note">Почта — в формате name@mail.ru. Имя и пароль — без ограничений; подтверждение почты не требуется.</p>{formError&&<p className="form-error" role="alert">{formError}</p>}<button className="primary full" disabled={busy}>{busy?'Подождите…':auth==='register'?'Создать аккаунт':'Войти'}</button></form><p className="auth-switch"><button disabled={busy} onClick={()=>login(auth==='register'?'login':'register')}>{auth==='register'?'Уже есть аккаунт? Войти':'Создать аккаунт'}</button></p></Dialog>}
    {editor&&<Dialog title={editor.preview?'Отправить изменение на модерацию':`${operations[action.operation]} · ${names[action.entity]}`} locked={busy} variant="proposal-editor-dialog" onClose={()=>setEditor(null)}><div className="proposal-editor-layout"><div className="proposal-editor-content">
      {pickingPlace?<><p className="dialog-description">Нажмите на новое место: лес, пустой участок или другую точку. Форма откроется здесь же, введённые параметры сохранятся.</p><CityMap state={city.state} metrics={city.metrics} mode={action.entity==='area'?'add_area':values.kind==='home'?'add_home':'add_object'} selectedHome={home} setSelectedHome={()=>{}} onSelect={()=>{}} onPlace={point=>{setEditor(current=>({...current,action:{...current.action,values:{...current.action.values,...point}},preview:null,plannedActions:null}));setPickingPlace(false);}}/><button className="secondary" onClick={()=>setPickingPlace(false)}>Отменить выбор места</button></>:editor.preview?<><p className="dialog-description">Общий расчёт всех изменений набора. Карта изменится после одобрения модератора.</p>
        <Estimate estimate={editor.preview.estimate}/>
        <form onSubmit={submit} noValidate>
          <label className="creative-confirm"><input type="checkbox" checked={creativeDone} onChange={e=>setCreativeDone(e.target.checked)}/> Я закончил редактирование и хочу отправить весь проект.</label><label className="field">Обоснование (необязательно)<textarea maxLength="1000" rows="2" value={reason} onChange={e=>setReason(e.target.value)} placeholder="Можно оставить пустым"/></label>
          {formError&&<p className="form-error" role="alert">{formError}</p>}
          <div className="form-actions proposal-send-actions"><button className="secondary" type="button" disabled={busy} onClick={()=>editor.batch?setEditor(null):setEditor(current=>({...current,preview:null,plannedActions:null}))}>Назад</button><button className="secondary" type="button" disabled={busy||editor.plannedActions.length>=20} onClick={addMore}>Добавить ещё</button><button className="secondary" type="button" disabled={busy} onClick={()=>beginSaveScenario({actions:editor.plannedActions,base_version:editor.base_version})}>Сохранить сценарий</button><button className="primary" type="submit" disabled={busy||!creativeDone}>{busy?'Отправляем…':'Отправить весь проект на модерацию'}</button></div>
        </form>
        <MetricsPanel before={radiusMetrics(editor.preview.before,radius)} after={radiusMetrics(editor.preview.after,radius)} compact/><ParkTable metrics={editor.preview.before} after={editor.preview.after} radii={radii} radius={radius} setRadius={setRadius} setRadii={setRadii}/>
        <CityMap state={editor.preview.state} metrics={editor.preview.after} relocation={action.entity==='object'&&action.operation==='update'?{before:city.state.objects.find(o=>o.id===action.id),after:editor.preview.state.objects.find(o=>o.id===action.id)}:null} mode="inspect" selectedHome={home} setSelectedHome={focusHome} focusRequest={focusRequest} compact/>
      </>:<form onSubmit={previewChange}>
        {action.operation==='add'&&<div className="placement-choice"><p>Место выбрано на карте. Можно указать другую точку, сохранив параметры объекта.</p><button type="button" className="secondary" onClick={()=>setPickingPlace(true)}>Выбрать место на карте</button></div>}{action.operation==='delete'?<p className="dialog-description">Подать заявку на снос или удаление существующего объекта «{city.state.objects.find(o=>o.id===action.id)?.name||action.id}»? Сначала покажем влияние на метрики. До одобрения модератора объект останется на карте.</p>:<div>
          {action.entity==='object'&&action.operation==='update'&&<p className="readonly-note">Перенос остановки «{city.state.objects.find(o=>o.id===action.id)?.name}» в выбранную точку. Изменятся привязка к пешеходной сети и маршруты. Остановка переместится после одобрения модератора.</p>}
          {action.entity==='object'&&action.operation==='add'&&<><p className="readonly-note">Новый объект появится в указанном месте после одобрения заявки.</p><label className="field">Название<input required value={values.name||''} maxLength="80" onChange={e=>updateField('name',e.target.value)}/></label><label className="field">Тип<select value={values.kind} onChange={e=>updateField('kind',e.target.value)}><option value="park">Парк</option><option value="parking">Парковка</option><option value="greenery">Озеленение</option><option value="stop">Остановка</option><option value="home">Жилой дом</option><option value="school">Школа</option><option value="clinic">Поликлиника</option><option value="shop">Магазин</option></select></label>{values.kind==='home'&&<div className="editor-grid"><label className="field">Ширина дома, м<input type="number" min="5" max="200" required value={values.width||''} onChange={e=>updateField('width',Number(e.target.value))}/></label><label className="field">Длина дома, м<input type="number" min="5" max="200" required value={values.height||''} onChange={e=>updateField('height',Number(e.target.value))}/></label><label className="field">Условных жителей<input type="number" min="0" max="100000" step="1" required value={values.residents??100} onChange={e=>updateField('residents',Number(e.target.value))}/></label></div>}</>}
          {action.entity==='area'&&<><label className="field">Название района<input required maxLength="80" value={values.name} onChange={e=>updateField('name',e.target.value)}/></label><div className="editor-grid"><label className="field">Ширина района, м<input type="number" min="5" max="4000" required value={values.width} onChange={e=>updateField('width',Number(e.target.value))}/></label><label className="field">Длина района, м<input type="number" min="5" max="4000" required value={values.height} onChange={e=>updateField('height',Number(e.target.value))}/></label></div><p className="form-note">Указанное место — центр района. Граница появится после одобрения; дома добавляются отдельно.</p></>}
          {action.entity==='edge'&&<p className="readonly-note">Предложение: {values.closed?'перекрыть пешеходный участок':'восстановить пешеходный участок'}. Изменять узлы, геометрию и нагрузку дорожки житель не может.</p>}
        </div>}{formError&&<p className="form-error" role="alert">{formError}</p>}<div className="form-actions"><button className="secondary" type="button" disabled={busy} onClick={()=>setEditor(null)}>Отмена</button><button className="secondary" type="button" disabled={busy} onClick={addToProject}>Добавить в проект</button><button className="secondary" value="preview" disabled={busy}>Рассчитать до / после</button><button className="primary" value="send" disabled={busy}>{busy?'Отправляем…':'Отправить на модерацию'}</button></div></form>}
    </div><ProposalHistory items={items} user={user} objects={city.state.objects} bundle={bundle} busy={busy} onRemove={setRemoveIndex} onRefresh={()=>loadRequests().catch(e=>setFormError(e.message))}/></div></Dialog>}
    {review&&<Dialog title="Решение модератора" locked={busy} onClose={()=>setReview(null)}><h3>{review.target_name||title(review.action)}</h3><blockquote>{review.reason}</blockquote>{reviewPreview&&<><Estimate estimate={reviewPreview.estimate}/><MetricsPanel before={radiusMetrics(reviewPreview.before,radius)} after={radiusMetrics(reviewPreview.after,radius)} compact/><CityMap state={reviewPreview.state} metrics={reviewPreview.after} relocation={review.action?.entity==='object'&&review.action.operation==='update'?{before:city.state.objects.find(o=>o.id===review.action.id),after:reviewPreview.state.objects.find(o=>o.id===review.action.id)}:null} mode="inspect" selectedHome={home} setSelectedHome={focusHome} focusRequest={focusRequest} compact/></>}{formError&&<p className="form-error" role="alert">{formError}</p>}{review.author_id===user.id&&user.role!=='admin'?<p className="form-note">Свою заявку должен рассмотреть другой модератор.</p>:<><label className="field">Обоснование решения (необязательно)<textarea rows="3" maxLength="1000" value={comment} onChange={e=>setComment(e.target.value)}/></label><div className="form-actions"><button className="danger-button" disabled={busy} onClick={()=>decide('rejected')}>Отклонить и закрыть</button><button className="primary" disabled={busy||!reviewPreview||!reviewPreview.estimate?.can_submit} onClick={()=>decide('approved')}>Одобрить и закрыть</button></div></>}</Dialog>}
  </>;
}
