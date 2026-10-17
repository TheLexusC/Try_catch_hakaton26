import React from 'react';

const workTypes = {'move_stop': ['Перенос остановки', 150000], 'add_stop': ['Новая остановка', 500000], 'add_home': ['Новый дом', 6000000], 'add_park': ['Новый парк', 2000000], 'add_parking': ['Парковка', 800000], 'add_greenery': ['Озеленение', 250000], 'add_school': ['Школа', 4000000], 'add_clinic': ['Поликлиника', 3000000], 'add_shop': ['Магазин', 1000000], 'add_road': ['Дорожка', 200000], 'add_area': ['Район', 0], 'remove_stop': ['Удаление остановки', 100000], 'remove_park': ['Удаление парка', 300000], 'remove_parking': ['Удаление парковки', 100000], 'remove_greenery': ['Удаление озеленения', 50000], 'close_edge': ['Перекрытие дорожки', 50000], 'open_edge': ['Открытие дорожки', 25000]};

export const money = n => new Intl.NumberFormat('ru-RU', { 
  style: 'currency', 
  currency: 'RUB', 
  maximumFractionDigits: 0 
}).format(n || 0);

export function actionLabel(action, objects, names = {}) {
  let name = names[action.id] || objects.find(o => o.id === action.id)?.name || action.values?.name;
  
  if (!name) {
    if (action.entity === 'edge') name = 'Пешеходный участок';
    else if (action.entity === 'area') name = 'Район';
    else name = `Объект ${action.id}`;
  }
  
  let verb = '';
  if (action.entity === 'edge') verb = action.values.closed ? 'Перекрыть' : 'Открыть';
  else if (action.operation === 'add') verb = 'Добавить';
  else if (action.operation === 'delete') verb = 'Удалить';
  else verb = 'Перенести остановку';
  
  return `${verb}: ${name}`;
}

export function Estimate({ estimate }) {
  if (!estimate) return null;
  
  return (
    <section className={`estimate ${estimate.can_submit ? '' : 'over-budget'}`} aria-label="Оценка стоимости изменений">
      <h3>Справочная оценка набора: {money(estimate.total)}</h3>
      <ul>
        {estimate.lines.map((l, i) => (
          <li key={i}>
            <div>
              <span>{l.label} · {l.name}</span>
              {l.demolition && (
                <small className="demolition-factors">
                  Пятно здания: {l.demolition.area_m2.toLocaleString('ru-RU')} м²
                  {l.demolition.area_estimated ? ' (условная площадь)' : ''} · жителей: {l.demolition.residents} · коэффициент расположения: {l.demolition.location_factor}
                  <br />
                  Порог для одного здания: {money(l.demolition.limit)} · {l.demolition.allowed ? 'Снос допустим по цене' : 'Снос запрещён по цене'}
                </small>
              )}
            </div>
            <strong>{money(l.amount)}</strong>
          </li>
        ))}
      </ul>
      {estimate.blocked.map(b => (
        <p key={b.id} role="alert"><b>{b.name}: {b.reason}</b></p>
      ))}
      <small>{estimate.note}</small>
    </section>
  );
}

export default function PlanningPanel({ policy, user, bundle, objects, busy, onRemove, onPreview, onBudget, workLimits, onWorkLimits }) {
  return (
    <section className="planning-panel">
      <details className="demolition-settings">
        <summary>Ограничения сноса</summary>
        <div className="budget-strip">
          <div>
            <small>СТОИМОСТЬ СНОСА</small>
            <strong>До {money(policy.limit)} за одно здание</strong>
            <p>Каждый дом проверяется отдельно. Общего бюджета и списания денег нет.</p>
          </div>
          {['moderator', 'admin'].includes(user?.role) && (
            <form onSubmit={onBudget}>
              <label className="field">
                Порог сноса одного здания, ₽
                <input aria-label="Порог стоимости сноса здания" name="limit" type="number" min="0" max="1000000000000" step="1" required defaultValue={policy.limit} key={policy.limit} />
              </label>
              <button className="secondary" disabled={busy}>Сохранить порог</button>
            </form>
          )}
        </div>
      </details>
      

      <details className="demolition-settings work-limit-settings">
        <summary>Бюджеты строительства и других работ</summary>
        <p>Для каждого вида — отдельный лимит на один проект. Пустое поле означает отсутствие ограничения. Стоимости учебные.</p>
        <form onSubmit={onWorkLimits}>
          <div className="work-limits-grid">
            {Object.entries(workTypes).map(([code,[label,price]])=><label className="field" key={code}>
              {label} · {money(price)} за действие
              <input aria-label={'Бюджет: '+label} name={code} type="number" min="0" max="1000000000000" step="1" placeholder="Без ограничения" defaultValue={workLimits?.[code]??''} key={code+':'+workLimits?.[code]} disabled={!['admin','moderator'].includes(user?.role)||busy}/>
            </label>)}
          </div>
          {['admin','moderator'].includes(user?.role)&&<button className="secondary" disabled={busy}>Сохранить бюджеты работ</button>}
        </form>
      </details>
      <details className="bundle-menu">
        <summary>Мой набор изменений ({bundle.actions.length}) — открыть / закрыть</summary>
        {!user ? (
          <p>Войдите, чтобы собрать свой набор.</p>
        ) : (
          <>
            <p>Добавляйте изменения на карте кнопкой «Добавить ещё» в предпросмотре. Все изменения набора отправляются одной заявкой и применяются вместе.</p>
            <small>Черновик сохранён в этом браузере отдельно для вашего аккаунта. Расчёт выполняется по текущей карте.</small>
            {bundle.actions.length > 0 ? (
              <>
                <ol>
                  {bundle.actions.map((a, i) => (
                    <li key={a.entity + a.id}>
                      <span>{actionLabel(a, objects)}</span>
                      <button className="text-button" disabled={busy} onClick={() => onRemove(i)}>Удалить изменение {i + 1}</button>
                    </li>
                  ))}
                </ol>
                <button className="primary" disabled={busy} onClick={onPreview}>Завершить и рассчитать проект</button>
              </>
            ) : (
              <p>Набор пока пуст.</p>
            )}
          </>
        )}
      </details>
    </section>
  );
}


