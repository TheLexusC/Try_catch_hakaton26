import React from 'react';

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

export default function PlanningPanel({ policy, user, bundle, objects, busy, onRemove, onPreview, onBudget }) {
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
      
      <details className="bundle-menu">
        <summary>Мой набор изменений ({bundle.actions.length}) — открыть / закрыть</summary>
        {!user ? (
          <p>Войдите, чтобы собрать свой набор.</p>
        ) : (
          <>
            <p>Добавляйте изменения на карте кнопкой «Добавить ещё» в предпросмотре. Все изменения набора отправляются одной заявкой и применяются вместе.</p>
            <small>Черновик сохранён в этом браузере отдельно для вашего аккаунта. После обновления карты нужно пересобрать набор.</small>
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


