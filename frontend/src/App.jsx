import React, {useCallback,useEffect,useRef,useState,useId} from 'react';
import CityMap,{kinds} from './components/CityMap.jsx';
import ControlPanel from './components/ControlPanel.jsx';
import PlanningPanel,{Estimate,money,actionLabel} from './components/PlanningPanel.jsx';
import ProposalHistory from './components/ProposalHistory.jsx';
import MetricsPanel,{format} from './components/MetricsPanel.jsx';

const names={object:'Объект',edge:'Дорожка',node:'Узел'};
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
  const [query,setQuery]=useState(''),[page,setPage]=useState(0),[focusRequest,setFocusRequest]=useState(0),[movingStop,setMovingStop]=useState(null);
  const [home,setHome]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [auth,setAuth]=useState(null),[items,setItems]=useState([]),[editor,setEditor]=useState(null),[reason,setReason]=useState('');
  const [review,setReview]=useState(null),[reviewPreview,setReviewPreview]=useState(null),[comment,setComment]=useState(''),[formError,setFormError]=useState('');
  const [bundle,setBundle]=useState({actions:[],base_version:0}),[removeIndex,setRemoveIndex]=useState(null);
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
    if(!user){login('login');return;}if(busy)return;if(entity==='object'&&operation==='delete'&&item.demolition?.allowed===false){setError(item.demolition.reason);return;}if(bundle.actions.length>=20){setError('В наборе уже 20 изменений. Удалите одно или отправьте набор.');return;}
    const {id,...values}=item;
    setEditor({action:{entity,operation,id:id||`${entity[0]}-${crypto.randomUUID()}`,values:operation==='delete'?{}:values},base_version:bundle.actions.length?bundle.base_version:city.state.version});
    setReason('');setFormError('');loadRequests().catch(e=>setFormError(e.message));
  };
  const moveStop=stop=>{if(!user){login('login');return;}setMovingStop(stop);setMode('move_stop');};
  const changeMode=value=>{setMode(value);if(value!=='move_stop')setMovingStop(null);};
  const place=point=>{if(mode==='move_stop'){if(movingStop)openEditor('object','update',{id:movingStop.id,...point});return;}openEditor('object','add',{name:'Новая зелёная зона',kind:'park',...point});};
  const select=(entity,item)=>entity==='edge'?openEditor('edge','update',{id:item.id,closed:!item.closed}):openEditor('object','delete',item);
  const updateField=(key,value)=>setEditor(current=>({...current,action:{...current.action,values:{...current.action.values,[key]:value}}}));
  const previewChange=async e=>{
    e.preventDefault();setBusy(true);setFormError('');
    try{const plannedActions=editor.batch?bundle.actions:[...bundle.actions,editor.action];const preview=await api('/preview',{actions:plannedActions,base_version:editor.base_version});setEditor(current=>({...current,preview,plannedActions}));}catch(e){setFormError(e.message);}finally{setBusy(false);}
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
    setReason('');setFormError('');setEditor({batch:true,action:bundle.actions.at(-1),plannedActions:bundle.actions,base_version:bundle.base_version,preview});
  });
  const saveBudget=e=>{e.preventDefault();const limit=Number(new FormData(e.currentTarget).get('limit'));run(async()=>{await api('/demolition-policy',{limit});await loadCity();setNotice('Порог стоимости сноса одного здания сохранён.');});};
  const openReview=async item=>{
    setReview(item);setReviewPreview(null);setComment('');setFormError('');setBusy(true);
    try{setReviewPreview(await api(`/proposals/${item.id}/preview`));}catch(e){setFormError(e.message);}finally{setBusy(false);}
  };
  const decide=async decision=>{
    setBusy(true);setFormError('');
    try{await api(`/proposals/${review.id}/decision`,{decision,comment});setReview(null);await loadCity();await loadRequests();setNotice('Решение сохранено. Заявка закрыта.');}catch(e){setFormError(e.message);}finally{setBusy(false);}
  };
  const pending=items.filter(i=>i.status==='pending').length;
  const selected=city?.metrics.rows.find(r=>r.id===home)||city?.metrics.rows[0];
  const action=editor?.action, values=action?.values;
  const found=city?.state.objects.filter(o=>(o.name+' '+kinds[o.kind]).toLocaleLowerCase('ru-RU').includes(query.toLocaleLowerCase('ru-RU')))||[];
  const shown=found.slice(page*50,(page+1)*50);


  return <>
    <header className="site-header"><a className="brand" href="/"><span className="brand-mark">о<span>↗</span></span><span>ОБНИНСК <b>2040</b><small>КОНСТРУКТОР ГОРОДА</small></span></a><nav aria-label="Навигация"><button className={tab==='map'?'nav-active':''} onClick={()=>setTab('map')}>Карта города</button><button className={tab==='requests'?'nav-active':''} onClick={()=>{setTab('requests');if(user)loadRequests().catch(e=>setError(e.message));}}>{canModerate?'Модерация':'Мои заявки'} {pending>0&&<span className="count">{pending}</span>}</button></nav><div className="account">{user?<><span className="account-name">{user.name}<small>{user.role==='admin'?'Администратор':canModerate?'Модератор':'Житель'}</small></span><button className="text-button" disabled={busy} onClick={logout}>Выйти</button></>:<><button className="text-button" onClick={()=>login('login')}>Войти</button><button className="primary small" onClick={()=>login('register')}>Регистрация</button></>}</div></header>
    <main>
      {error&&<div className="banner error" role="alert">{error}<button aria-label="Скрыть ошибку" onClick={()=>setError('')}>×</button></div>}
      {notice&&<div className="banner success" role="status">{notice}<button aria-label="Скрыть уведомление" onClick={()=>setNotice('')}>×</button></div>}
      {tab==='map'?<>
        <section className="hero"><div><div className="eyebrow"><span className="live-dot"/> ОБНИНСК · РЕАЛЬНАЯ КАРТА ГОРОДА</div><h1>Город ближе.<br/><span>Начните со своей улицы.</span></h1><p>Посмотрите на город глазами пешехода.<br/>Предложите изменение — и оцените его влияние на жизнь города.</p></div><div className="hero-aside"><div className="coordinate">55.1080° N<br/>36.6120° E</div><div className="hero-stats"><div><strong>{city?.state.objects.length??'—'}</strong><span>объектов</span></div><div><strong>{format(city?.metrics.total_residents)}</strong><span>жителей · оценка</span></div></div></div></section>
        {!city?<div className="empty-state"><h2>Подключаем район…</h2><p>Запустите PostgreSQL и backend через «Запустить.command».</p><button className="primary" onClick={refresh}>Обновить</button></div>:<>
          <PlanningPanel policy={city.state.demolition_policy||{limit:10000000}} user={user} bundle={bundle} objects={city.state.objects} busy={busy} onRemove={setRemoveIndex} onPreview={previewBundle} onBudget={saveBudget}/>{user&&<div className="map-request-history"><ProposalHistory items={items} user={user} objects={city.state.objects} busy={busy} onRefresh={()=>loadRequests().catch(e=>setError(e.message))}/></div>}<section className="workspace"><ControlPanel mode={mode} setMode={changeMode} stops={city.state.objects.filter(o=>o.kind==='stop')} movingStop={movingStop} onMoveStop={moveStop} user={user} onLogin={()=>login('login')} busy={busy}/><CityMap state={city.state} metrics={city.metrics} mode={mode} onSelect={select} onPlace={place} onMoveStop={moveStop} movingStopId={movingStop?.id} selectedHome={home} setSelectedHome={focusHome} focusRequest={focusRequest}/></section>
          <div className="selection-strip"><span>{selected?<><b>{selected.name}</b> · остановка {format(selected.stop_distance)} м · парк {format(selected.park_distance)} м</>:'В районе пока нет жилых домов'}</span><span>{city.state.nodes.length} узлов · {city.state.edges.length} дорожек</span><button onClick={refresh} disabled={busy}>↻ Обновить</button></div>
          <section className="analytics"><div className="section-heading"><div><div className="section-kicker">02 / МЕТРИКИ РАЙОНА</div><h2>Доступность и нагрузка</h2></div><span className="pill">Версия {city.state.version} · PostgreSQL</span></div><MetricsPanel before={city.metrics}/><div className="load-summary">Контуры и адреса — OSM. Число жителей — расчётная оценка, нагрузка не измерена. Данные можно уточнить отдельно в PostgreSQL.</div>
            <div className="object-search"><input aria-label="Поиск здания" placeholder="Найти дом, улицу или объект…" value={query} onChange={e=>{setQuery(e.target.value);setPage(0);}}/><small>Найдено: {found.length.toLocaleString('ru-RU')}</small></div>
            {mode==='move_stop'&&<div className="readonly-note" role="status">{movingStop?`Перенос «${movingStop.name}»: нажмите на новое место на карте. Остановка останется на прежнем месте до одобрения заявки.`:'Выберите остановку в панели слева или нажмите на её маркер.'}</div>}
            <div className="table-wrap"><table><thead><tr><th>Объект</th><th>Тип</th><th>Жителей · оценка</th><th>Снос · оценка</th><th>Действия</th></tr></thead><tbody>{shown.map(o=><tr key={o.id}><td><button className="table-link" onClick={()=>{if(o.kind==='home')focusHome(o.id);else select('object',o);setMode('inspect');}}>{o.name}</button></td><td>{kinds[o.kind]}</td><td>{o.kind==='home'?'≈ '+format(o.residents):'—'}</td><td>{o.demolition?<details><summary>{money(o.demolition.amount)}</summary><p className="demolition-table-note">{format(o.demolition.area_m2)} м² · {o.demolition.residents} жителей<br/>Коэффициент расположения: {o.demolition.location_factor}<br/>Порог: {money(o.demolition.limit)}</p></details>:'—'}</td><td className="table-actions">{o.kind==='stop'&&<button onClick={()=>{moveStop(o);window.scrollTo({top:250,behavior:'smooth'});}}>Заявка на перенос</button>}<button disabled={o.demolition?.allowed===false} title={o.demolition?.reason||''} onClick={()=>openEditor('object','delete',o)}>{o.geom&&o.kind!=='park'?'Заявка на снос':'Заявка на удаление'}</button>{o.demolition?.allowed===false&&<small className="demolition-denied">Снос невозможен: цена выше порога</small>}</td></tr>)}</tbody></table></div>
            <div className="pagination"><button disabled={page===0} onClick={()=>setPage(p=>p-1)}>← Назад</button><span>{page+1} / {Math.max(1,Math.ceil(found.length/50))}</span><button disabled={(page+1)*50>=found.length} onClick={()=>setPage(p=>p+1)}>Далее →</button></div>
            <details className="routes-details"><summary>Маршруты всех жилых домов</summary><div className="table-wrap"><table><thead><tr><th>Дом</th><th>Остановка</th><th>Парк</th><th>Парк в 500 м</th></tr></thead><tbody>{city.metrics.rows.filter(r=>r.name.toLocaleLowerCase('ru-RU').includes(query.toLocaleLowerCase('ru-RU'))).slice(0,100).map(r=><tr key={r.id}><td><button className="table-link" onClick={()=>{focusHome(r.id);setMode('inspect');}}>{r.name}</button></td><td>{r.stop_distance===null?'Нет пути':format(r.stop_distance)+' м'}</td><td>{r.park_distance===null?'Нет пути':format(r.park_distance)+' м'}</td><td>{r.park_access?'Да':'Нет'}</td></tr>)}</tbody></table></div></details>
          </section>
          <section className="method"><div className="section-kicker">03 / КАК УСТРОЕНО</div><h2>Один объект — одна запись.</h2><div className="method-grid"><article><h3>PostgreSQL</h3><p>Узлы, дорожки и объекты — отдельные таблицы. В них координаты, жители, нагрузка и вместимость. Контуры зданий хранятся одним GeoJSON-значением на объект, без ручной разметки в коде.</p></article><article><h3>Дейкстра</h3><p>Длина пути — сумма участков и подходов к ближайшим узлам. До остановки считаем среднее по доступным домам; доступ к парку — долю жителей в 500 м.</p></article><article><h3>Модерация</h3><p>Предпросмотр → обоснование → заявка → решение. Одобрение применяет изменение, отклонение сохраняет район. Оба решения закрывают заявку.</p></article></div><p className="model-note">{city.map.notes} Нагрузка показана отдельно и не изменяет геометрическую длину маршрута. Существующие здания нельзя двигать или менять. Жители предлагают снос существующего объекта, перенос остановки, новый парк или остановку, открытие или перекрытие дорожки.</p></section>
        </>}
      </>:<section className="requests-section"><div className="section-heading"><div><div className="section-kicker">ПРЕДЛОЖЕНИЯ ЖИТЕЛЕЙ</div><h1>{canModerate?'Модерация изменений':'Мои заявки'}</h1></div><button className="secondary" onClick={refresh} disabled={busy}>↻ Обновить</button></div>{!user?<div className="empty-state"><h2>Войдите для работы с заявками</h2><button className="primary" onClick={()=>login('login')}>Войти</button></div>:items.length===0?<div className="empty-state"><h2>Заявок пока нет</h2><p>Выберите действие на карте и отправьте предложение.</p><button className="primary" onClick={()=>setTab('map')}>Открыть район</button></div>:<div className="request-list">{items.map(item=><article className="request-card" key={item.id}><div className="request-card-top"><span className={'status '+item.status}>{statuses[item.status]}</span><time>{date(item.created_at)}</time></div><h3>{item.target_name||title(item.action)}</h3><p className="request-cost">{money(item.estimated_cost)} · {(item.actions||[item.action]).length} изменений</p><details className="request-changes"><summary>Состав заявки</summary><ol>{(item.actions||[item.action]).map((a,i)=><li key={i}>{actionLabel(a,city?.state.objects||[])}</li>)}</ol></details><p className="request-reason">{item.reason}</p>{item.comment&&<div className="decision-note"><b>{item.reviewer_name} · {date(item.closed_at)}</b><p>{item.comment}</p></div>}<div className="request-card-bottom"><span>{item.author_name} · версия {item.base_version}</span>{canModerate&&item.status==='pending'&&<button className="primary small" disabled={busy} onClick={()=>openReview(item)}>Рассмотреть</button>}</div></article>)}</div>}</section>}
      <footer><span>ОБНИНСК <b>2040</b></span><span>Реальная геометрия © OpenStreetMap contributors · ODbL 1.0</span></footer>
    </main>

    {removeIndex!==null&&<Dialog narrow title="Удалить изменение из набора?" onClose={()=>setRemoveIndex(null)}><p className="dialog-description">{bundle.actions[removeIndex]&&actionLabel(bundle.actions[removeIndex],city?.state.objects||[])}. Общая карта и отправленные заявки не изменятся.</p><div className="form-actions"><button className="secondary" onClick={()=>setRemoveIndex(null)}>Оставить</button><button className="danger-button" onClick={removeDraft}>Подтвердить удаление</button></div></Dialog>}
    {auth&&<Dialog narrow variant="auth-dialog" title={auth==='register'?'Регистрация':'Вход в аккаунт'} locked={busy} onClose={()=>setAuth(null)}><form onSubmit={authenticate}>{auth==='register'&&<label className="field">Имя<input name="name" autoComplete="name"/></label>}<label className="field">Email<input name="email" type="email" required placeholder="name@obninsk.test" autoComplete="email"/></label><label className="field">Пароль<input name="password" type="password" autoComplete={auth==='register'?'new-password':'current-password'}/></label><p className="form-note">Почта — в формате name@mail.ru. Имя и пароль — без ограничений; подтверждение почты не требуется.</p>{formError&&<p className="form-error" role="alert">{formError}</p>}<button className="primary full" disabled={busy}>{busy?'Подождите…':auth==='register'?'Создать аккаунт':'Войти'}</button></form><p className="auth-switch"><button disabled={busy} onClick={()=>login(auth==='register'?'login':'register')}>{auth==='register'?'Уже есть аккаунт? Войти':'Создать аккаунт'}</button></p></Dialog>}
    {editor&&<Dialog title={editor.preview?'Отправить изменение на модерацию':`${operations[action.operation]} · ${names[action.entity]}`} locked={busy} variant="proposal-editor-dialog" onClose={()=>setEditor(null)}><div className="proposal-editor-layout"><div className="proposal-editor-content">
      {editor.preview?<><p className="dialog-description">Общий расчёт всех изменений набора. Карта изменится после одобрения модератора.</p>
        <Estimate estimate={editor.preview.estimate}/>
        <form onSubmit={submit} noValidate>
          <label className="field">Обоснование (необязательно)<textarea maxLength="1000" rows="2" value={reason} onChange={e=>setReason(e.target.value)} placeholder="Можно оставить пустым"/></label>
          {formError&&<p className="form-error" role="alert">{formError}</p>}
          <div className="form-actions proposal-send-actions"><button className="secondary" type="button" disabled={busy} onClick={()=>editor.batch?setEditor(null):setEditor(current=>({...current,preview:null,plannedActions:null}))}>Назад</button><button className="secondary" type="button" disabled={busy||editor.plannedActions.length>=20} onClick={addMore}>Добавить ещё</button><button className="primary" type="submit" disabled={busy}>{busy?'Отправляем…':'Отправить на модерацию'}</button></div>
        </form>
        <MetricsPanel before={editor.preview.before} after={editor.preview.after} compact/>
        <CityMap state={editor.preview.state} metrics={editor.preview.after} relocation={action.entity==='object'&&action.operation==='update'?{before:city.state.objects.find(o=>o.id===action.id),after:editor.preview.state.objects.find(o=>o.id===action.id)}:null} mode="inspect" selectedHome={home} setSelectedHome={focusHome} focusRequest={focusRequest} compact/>
      </>:<form onSubmit={previewChange}>
        {action.operation==='delete'?<p className="dialog-description">Подать заявку на снос или удаление существующего объекта «{city.state.objects.find(o=>o.id===action.id)?.name||action.id}»? Сначала покажем влияние на метрики. До одобрения модератора объект останется на карте.</p>:<div>
          {action.entity==='object'&&action.operation==='update'&&<p className="readonly-note">Перенос остановки «{city.state.objects.find(o=>o.id===action.id)?.name}» в выбранную точку. Изменятся привязка к пешеходной сети и маршруты. Остановка переместится после одобрения модератора.</p>}
          {action.entity==='object'&&action.operation==='add'&&<><p className="readonly-note">Место выбрано на карте. Можно предложить новую остановку или зелёную зону. Строительство и перемещение зданий недоступны.</p><label className="field">Название<input required value={values.name||''} maxLength="80" onChange={e=>updateField('name',e.target.value)}/></label><label className="field">Тип<select value={values.kind} onChange={e=>updateField('kind',e.target.value)}><option value="park">Зелёная зона</option><option value="stop">Остановка</option></select></label></>}
          {action.entity==='edge'&&<p className="readonly-note">Предложение: {values.closed?'перекрыть пешеходный участок':'восстановить пешеходный участок'}. Изменять узлы, геометрию и нагрузку дорожки житель не может.</p>}
        </div>}{formError&&<p className="form-error" role="alert">{formError}</p>}<div className="form-actions"><button className="secondary" type="button" disabled={busy} onClick={()=>setEditor(null)}>Отмена</button><button className="primary" disabled={busy}>{busy?'Считаем…':'Рассчитать до / после →'}</button></div></form>}
    </div><ProposalHistory items={items} user={user} objects={city.state.objects} bundle={bundle} busy={busy} onRemove={setRemoveIndex} onRefresh={()=>loadRequests().catch(e=>setFormError(e.message))}/></div></Dialog>}
    {review&&<Dialog title="Решение модератора" locked={busy} onClose={()=>setReview(null)}><h3>{review.target_name||title(review.action)}</h3><blockquote>{review.reason}</blockquote>{reviewPreview&&<><Estimate estimate={reviewPreview.estimate}/><MetricsPanel before={reviewPreview.before} after={reviewPreview.after} compact/><CityMap state={reviewPreview.state} metrics={reviewPreview.after} relocation={review.action?.entity==='object'&&review.action.operation==='update'?{before:city.state.objects.find(o=>o.id===review.action.id),after:reviewPreview.state.objects.find(o=>o.id===review.action.id)}:null} mode="inspect" selectedHome={home} setSelectedHome={focusHome} focusRequest={focusRequest} compact/></>}{formError&&<p className="form-error" role="alert">{formError}</p>}{review.author_id===user.id?<p className="form-note">Свою заявку должен рассмотреть другой модератор.</p>:<><label className="field">Обоснование решения<textarea rows="3" minLength="5" maxLength="1000" value={comment} onChange={e=>setComment(e.target.value)}/></label><div className="form-actions"><button className="danger-button" disabled={busy||comment.trim().length<5} onClick={()=>decide('rejected')}>Отклонить и закрыть</button><button className="primary" disabled={busy||!reviewPreview||!reviewPreview.estimate?.can_submit||comment.trim().length<5} onClick={()=>decide('approved')}>Одобрить и закрыть</button></div></>}</Dialog>}
  </>;
}
