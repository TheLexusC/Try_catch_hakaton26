import React, { useState } from 'react';

// Конфигурация инструментов вынесена для удобства чтения
const tools = [
  ['inspect', '↗', 'Исследовать', 'Маршруты от выбранного дома'],
  ['edge', '⊘', 'Изменить дорожку', 'Перекрыть или открыть участок'],
  ['move_stop', '▣', 'Перенести остановку', 'Выбрать новое место'],
  ['add_park', '♧', 'Добавить зелёную зону', 'Предложить место для отдыха'],
  ['remove_park', '−', 'Убрать зелёную зону', 'Отправить на рассмотрение'],
];

export default function ControlPanel({
  mode,
  setMode,
  city,
  stopId,
  setStopId,
  onAction,
  user,
  onLogin,
  busy
}) {
  const [target, setTarget] = useState('');
  const nodes = city.map.nodes;

  // Распакованный выбор опций вместо сложного тернарного оператора
  let options = [];
  if (mode === 'edge') {
    options = city.map.edges.map(e => {
      const isClosed = city.state.closed_edges.includes(e.id);
      return [e.id, `${e.id} · Math.round(e.length)м{isClosed ? ' · закрыта' : ''}`];
    });
  } else if (mode === 'remove_park') {
    options = city.state.facilities
      .filter(f => f.kind === 'park')
      .map(f => [f.id, f.name]);
  } else {
    options = nodes.map(n => [n.id, n.label]);
  }

  const selectTool = (next) => {
    setTarget('');
    setMode(next);
  };

  // Распакованная логика формирования payload для экшена
  const propose = () => {
    if (!target) return;

    let actionPayload;
    if (mode === 'edge') {
      const isClosed = city.state.closed_edges.includes(target);
      actionPayload = { 
        type: isClosed ? 'open_edge' : 'close_edge', 
        target_id: target 
      };
    } else if (mode === 'move_stop') {
      actionPayload = { type: mode, target_id: target, facility_id: stopId };
    } else {
      actionPayload = { type: mode, target_id: target };
    }

    onAction(actionPayload);
  };

  // Вспомогательная функция для читаемости плейсхолдера
  const getSelectPlaceholder = () => {
    if (mode === 'edge') return 'участок';
    if (mode === 'remove_park') return 'зелёную зону';
    return 'узел';
  };

  return (
    <aside className="control-panel">
      <div className="section-kicker">01 / ИНСТРУМЕНТЫ</div>
      <h2>Что изменим?</h2>
      
      {/* Список инструментов */}
      <div className="tools">
        {tools.map(([id, icon, title, subtitle]) => (
          <button 
            key={id} 
            disabled={busy} 
            aria-pressed={mode === id} 
            className={`tool ${mode === id ? 'active' : ''}`} 
            onClick={() => selectTool(id)}
          >
            <span className="tool-icon" aria-hidden="true">{icon}</span>
            <span>
              <strong>{title}</strong>
              <small>{subtitle}</small>
            </span>
            {mode === id && <i />}
          </button>
        ))}
      </div>

      {/* Выбор остановки (только для режима move_stop) */}
      {mode === 'move_stop' && (
        <label className="field">
          Остановка
          <select value={stopId} onChange={e => setStopId(e.target.value)}>
            {city.state.facilities
              .filter(f => f.kind === 'stop')
              .map((f, i) => (
                <option key={f.id} value={f.id}>
                  {f.name} · {i + 1}
                </option>
              ))}
          </select>
        </label>
      )}

      {/* Выбор цели для изменения */}
      {mode !== 'inspect' && (
        <div className="target-select">
          <label className="field">
            Или выберите из списка
            <select value={target} onChange={e => setTarget(e.target.value)}>
              <option value="">Выберите {getSelectPlaceholder()}</option>
              {options.map(([id, label]) => (
                <option key={id} value={id}>{label}</option>
              ))}
            </select>
          </label>
          
          <button 
            className="primary full" 
            disabled={!target || busy} 
            onClick={propose}
          >
            Предложить изменение →
          </button>
        </div>
      )}

      {/* Информационные блоки */}
      <div className="moderation-note">
        <span aria-hidden="true">◇</span>
        <div>
          <b>Решаем вместе</b>
          <p>Каждое изменение сначала проходит модерацию. Общая карта обновится только после одобрения.</p>
        </div>
      </div>

      {!user && (
        <button className="secondary full" onClick={onLogin}>
          Войти, чтобы предложить
        </button>
      )}

      <div className="dataset-note">
        <span className="live-dot" /> Реальная геометрия OSM<br />
        <small>{nodes.length} узлов · {city.map.edges.length} участков</small>
      </div>
    </aside>
  );
}


