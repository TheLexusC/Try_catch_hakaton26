import React, { useState, useEffect } from 'react';

// Добавлен 5-й элемент в массив конфигурации: цифра для горячей клавиши
const tools = [
  ['inspect', '↗', 'Исследовать', 'Маршруты от выбранного дома', '1'],
  ['edge', '⊘', 'Изменить дорожку', 'Перекрыть или открыть участок', '2'],
  ['move_stop', '▣', 'Перенести остановку', 'Выбрать новое место', '3'],
  ['add_park', '♧', 'Добавить зелёную зону', 'Предложить место', '4'],
  ['remove_park', '−', 'Убрать зелёную зону', 'Отправить на рассмотрение', '5'],
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

  // НОВОЕ: Обработчик горячих клавиш (1-5) для переключения инструментов
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Игнорируем нажатия, если пользователь вводит текст в инпут или селект
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
      
      const keyIndex = parseInt(e.key, 10) - 1;
      if (keyIndex >= 0 && keyIndex < tools.length) {
        setTarget('');
        setMode(tools[keyIndex][0]);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [setMode]);

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

  const propose = () => {
    if (!target) return;
    let actionPayload;
    if (mode === 'edge') {
      actionPayload = { 
        type: city.state.closed_edges.includes(target) ? 'open_edge' : 'close_edge', 
        target_id: target 
      };
    } else if (mode === 'move_stop') {
      actionPayload = { type: mode, target_id: target, facility_id: stopId };
    } else {
      actionPayload = { type: mode, target_id: target };
    }
    onAction(actionPayload);
  };

  const getSelectPlaceholder = () => {
    if (mode === 'edge') return 'участок';
    if (mode === 'remove_park') return 'зелёную зону';
    return 'узел';
  };

  return (
    <aside className="control-panel">
      <div className="section-kicker">01 / ИНСТРУМЕНТЫ</div>
      <h2>Что изменим?</h2>
      
      <div className="tools">
        {tools.map(([id, icon, title, subtitle, hotkey]) => (
          <button 
            key={id} 
            disabled={busy} 
            aria-pressed={mode === id} 
            className={`tool ${mode === id ? 'active' : ''}`} 
            onClick={() => selectTool(id)}
            title={`Горячая клавиша: ${hotkey}`} // Подсказка при наведении
          >
            <span className="tool-icon" aria-hidden="true">{icon}</span>
            <span className="tool-content">
              <strong>{title}</strong>
              <small>{subtitle}</small>
            </span>
            {/* НОВОЕ: Визуальное отображение кнопки клавиатуры */}
            <kbd className="hotkey-hint">{hotkey}</kbd>
            {mode === id && <i />}
          </button>
        ))}
      </div>

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
            {busy ? 'Отправка...' : 'Предложить изменение →'}
          </button>
        </div>
      )}

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
