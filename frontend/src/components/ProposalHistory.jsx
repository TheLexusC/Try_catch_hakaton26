import React from 'react';
import { actionLabel, money } from './PlanningPanel.jsx';

const statusNames = {
  pending: 'На модерации',
  approved: 'Одобрена · закрыта',
  rejected: 'Отклонена · закрыта'
};

export default function ProposalHistory({ items = [], user, objects = [], bundle, busy, onRemove, onRefresh }) {
  const own = items.filter(item => item.author_id === user?.id);
  
  return (
    <aside className="proposal-sidebar" aria-label="История и черновики заявок">
      {bundle && (
        <details className="editor-drafts" open>
          <summary>Мой набор ({bundle.actions.length})</summary>
          {bundle.actions.length ? (
            <ol>
              {bundle.actions.map((a, i) => (
                <li key={a.entity + a.id}>
                  <span>{actionLabel(a, objects)}</span>
                  <button type="button" className="text-button" disabled={busy} onClick={() => onRemove(i)}>Удалить изменение {i + 1}</button>
                </li>
              ))}
            </ol>
          ) : (
            <p>В наборе пока пусто. «Добавить ещё» сохранит текущее изменение.</p>
          )}
        </details>
      )}
      
      <details className="proposal-history">
        <summary>Мои прошлые заявки ({own.length})</summary>
        <button type="button" className="secondary small" disabled={busy} onClick={onRefresh}>
          Обновить историю
        </button>
        
        {own.length === 0 ? (
          <p>Отправленных заявок пока нет.</p>
        ) : (
          <div className="history-list">
            {own.map(item => (
              <article className="history-item" key={item.id}>
                <span className={`status ${item.status}`}>{statusNames[item.status]}</span>
                <h3>{item.target_name || 'Изменение инфраструктуры'}</h3>
                <time>{new Date(item.created_at).toLocaleString('ru-RU')}</time>
                <p>{money(item.estimated_cost)}</p>
                <details>
                  <summary>Состав и обоснование</summary>
                  <ol>
                    {(item.actions || [item.action]).map((a, i) => (
                      <li key={i}>{actionLabel(a, objects, item.action_names || {})}</li>
                    ))}
                  </ol>
                  <p>{item.reason || 'Без обоснования'}</p>
                  {item.comment && <p>Решение: {item.comment}</p>}
                </details>
              </article>
            ))}
          </div>
        )}
      </details>
    </aside>
  );
}


