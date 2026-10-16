import React, { useCallback, useEffect, useRef, useState } from 'react';
import CityMap from './components/CityMap.jsx';
import ControlPanel from './components/ControlPanel.jsx';
import MetricsPanel, { format } from './components/MetricsPanel.jsx';

const ACTION_NAMES = {
  close_edge: 'Перекрыть дорожку',
  open_edge: 'Открыть дорожку',
  move_stop: 'Перенести остановку',
  add_park: 'Добавить зелёную зону',
  remove_park: 'Убрать зелёную зону',
};

const STATUS_LABELS = {
  pending: 'На модерации',
  approved: 'Одобрена · закрыта',
  rejected: 'Отклонена · закрыта',
};

const FILTERS = [
  ['all', 'Все заявки'],
  ['pending', 'На модерации'],
  ['closed', 'Закрытые'],
];

const formatDate = (value) =>
  new Date(value).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });

function Dialog({ title, onClose, children, wide = false, locked = false }) {
  const ref = useRef(null);

  useEffect(() => {
    const dialog = ref.current;
    dialog.showModal();
    return () => dialog.close();
  }, []);

  const handleCancel = (event) => {
    event.preventDefault();
    if (!locked) onClose();
  };

  const handleBackdrop = (event) => {
    if (event.target === event.currentTarget && !locked) onClose();
  };

  return (
    <dialog
      ref={ref}
      className={wide ? 'dialog wide' : 'dialog'}
      aria-labelledby="dialog-title"
      onCancel={handleCancel}
      onClick={handleBackdrop}
    >
      <div className="dialog-inner">
        <div className="dialog-top">
          <h2 id="dialog-title">{title}</h2>
          <button
            className="icon-button"
            disabled={locked}
            onClick={onClose}
            aria-label="Закрыть окно"
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}

export default function App() {
  // --- город и сессия ---
  const [city, setCity] = useState(null);
  const [session, setSession] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  // --- вкладки и режим карты ---
  const [tab, setTab] = useState('map');
  const [mode, setMode] = useState('inspect');
  const [stopId, setStopId] = useState('');

  // --- выбор и список заявок ---
  const [selectedHome, setSelectedHome] = useState('home-17');
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState('all');

  // --- общие состояния интерфейса ---
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  // --- формы и диалоги ---
  const [auth, setAuth] = useState(null);
  const [authError, setAuthError] = useState('');
  const [draft, setDraft] = useState(null);
  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState('');
  const [reason, setReason] = useState('');
  const [review, setReview] = useState(null);
  const [reviewData, setReviewData] = useState(null);
  const [reviewError, setReviewError] = useState('');
  const [comment, setComment] = useState('');

  const user = session?.user;

  // ---------- сетевой слой ----------

  const api = useCallback(
    async (path, options = {}) => {
      const headers = {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(session?.csrf_token ? { 'X-CSRF-Token': session.csrf_token } : {}),
        ...options.headers,
      };

      const response = await fetch('/api' + path, {
        credentials: 'same-origin',
        ...options,
        headers,
      });

      let body;
      try {
        body = await response.json();
      } catch {
        throw new Error(
          'Сервер вернул некорректный ответ. Проверьте, запущен ли backend.'
        );
      }

      if (!response.ok) {
        const message =
          typeof body.detail === 'string'
            ? body.detail
            : response.status === 422
              ? 'Проверьте поля формы и выбранные объекты.'
              : 'Не удалось выполнить запрос';
        const error = new Error(message);
        error.status = response.status;
        throw error;
      }

      return body;
    },
    [session?.csrf_token]
  );

  const refreshCity = useCallback(async () => {
    const body = await api('/city');
    setCity(body);
    setStopId((current) => {
      const facilities = body.state.facilities;
      if (facilities.some((f) => f.id === current)) return current;
      return facilities.find((f) => f.kind === 'stop')?.id || '';
    });
    return body;
  }, [api]);

  const refreshItems = useCallback(async () => {
    const data = await api('/proposals');
    setItems(data.items);
  }, [api]);

  // ---------- загрузка при старте ----------

  useEffect(() => {
    let active = true;

    fetch('/api/city')
      .then((r) => {
        if (!r.ok) throw new Error('Не удалось загрузить карту');
        return r.json();
      })
      .then((body) => {
        if (!active) return;
        setCity(body);
        setStopId(body.state.facilities.find((f) => f.kind === 'stop')?.id || '');
      })
      .catch((e) => active && setError(e.message));

    fetch('/api/auth/me', { credentials: 'same-origin' })
      .then(async (r) => {
        if (r.ok) {
          const data = await r.json();
          if (active) setSession(data);
        } else if (r.status !== 401) {
          throw new Error('Не удалось проверить сессию');
        }
      })
      .catch((e) => active && setError(e.message))
      .finally(() => active && setAuthChecked(true));

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (user) {
      refreshItems().catch((e) => setError(e.message));
    } else {
      setItems([]);
    }
  }, [user?.id, refreshItems]);

  // ---------- авторизация ----------

  const openAuth = (type) => {
    setAuthError('');
    setAuth(type);
  };

  const authenticate = async (event) => {
    event.preventDefault();
    setBusy(true);
    setAuthError('');

    const fields = new FormData(event.currentTarget);
    const payload = {
      email: fields.get('email').trim(),
      password: fields.get('password'),
    };
    if (auth === 'register') {
      payload.name = fields.get('name').trim();
    }

    try {
      const result = await api('/auth/' + auth, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setSession(result);
      setAuth(null);
      setNotice(
        auth === 'register'
          ? 'Аккаунт создан. Теперь можно предлагать изменения.'
          : 'Вы вошли в аккаунт.'
      );
    } catch (e) {
      setAuthError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    setBusy(true);
    try {
      await api('/auth/logout', { method: 'POST', body: '{}' });
      setSession(null);
      setItems([]);
      setTab('map');
      setMode('inspect');
      setNotice('Вы вышли из аккаунта.');
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  // ---------- предложения ----------

  const propose = async (action) => {
    if (busy) return;
    if (!user) {
      openAuth('login');
      return;
    }

    const change = { action, base_version: city.state.version };
    setDraft(change);
    setReason('');
    setPreview(null);
    setPreviewError('');
    setBusy(true);

    try {
      const result = await api('/preview', {
        method: 'POST',
        body: JSON.stringify(change),
      });
      setPreview(result);
    } catch (e) {
      setPreviewError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setPreviewError('');

    try {
      const result = await api('/proposals', {
        method: 'POST',
        body: JSON.stringify({ ...draft, reason }),
      });
      setDraft(null);
      setPreview(null);
      setMode('inspect');
      setNotice(result.message);
      setTab('requests');
      await refreshItems();
    } catch (e) {
      setPreviewError(e.message);
    } finally {
      setBusy(false);
    }
  };

  // ---------- модерация ----------

  const openReview = async (item) => {
    setReview(item);
    setReviewData(null);
    setReviewError('');
    setComment('');

    if (item.status !== 'pending') return;

    setBusy(true);
    try {
      const data = await api(`/proposals/${item.id}/preview`);
      setReviewData(data);
    } catch (e) {
      setReviewError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const decide = async (decision) => {
    if (comment.trim().length < 5) {
      setReviewError('Напишите обоснование решения: не менее 5 символов.');
      return;
    }

    setBusy(true);
    setReviewError('');

    try {
      await api(`/proposals/${review.id}/decision`, {
        method: 'POST',
        body: JSON.stringify({ decision, comment }),
      });

      setReview(null);
      setReviewData(null);
      setNotice(
        decision === 'approved'
          ? 'Заявка одобрена и закрыта. Общая карта обновлена.'
          : 'Заявка отклонена и закрыта. Карта не изменилась.'
      );

      await refreshCity();
      await refreshItems();
    } catch (e) {
      setReviewError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const refresh = async () => {
    setBusy(true);
    setError('');

    try {
      await refreshCity();

      if (user) {
        const current = await api('/auth/me');
        setSession(current);
        await refreshItems();
      }

      setNotice('Данные обновлены.');
    } catch (e) {
      if (e.status === 401) {
        setSession(null);
        setItems([]);
      }
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  // ---------- производные значения ----------

  const pendingCount = items.filter((i) => i.status === 'pending').length;
  const selectedRow =
    city?.metrics.rows.find((r) => r.id === selectedHome) || city?.metrics.rows[0];

  const visibleItems = items.filter((item) => {
    if (filter === 'all') return true;
    if (filter === 'pending') return item.status === 'pending';
    return item.status !== 'pending';
  });

  const targetLabel = (action) => {
    if (!city) return action.target_id;
    const node = city.map.nodes.find((n) => n.id === action.target_id);
    if (node) return `узел ${node.label}`;
    const facility = city.state.facilities.find((f) => f.id === action.target_id);
    return facility?.name || `участок ${action.target_id}`;
  };

  // ---------- разметка ----------

  return (
    <>
      <header className="site-header">
        <a className="brand" href="/" aria-label="Обнинск 2040, главная">
          <span className="brand-mark">
            о<span>↗</span>
          </span>
          <span>
            ОБНИНСК <b>2040</b>
            <small>КОНСТРУКТОР ГОРОДА БУДУЩЕГО</small>
          </span>
        </a>

        <nav aria-label="Главная навигация">
          <button
            className={tab === 'map' ? 'nav-active' : ''}
            onClick={() => setTab('map')}
          >
            Карта района
          </button>
          <button
            className={tab === 'requests' ? 'nav-active' : ''}
            onClick={() => {
              setTab('requests');
              if (user) refreshItems().catch((e) => setError(e.message));
            }}
          >
            {user?.role === 'moderator' ? 'Модерация' : 'Мои заявки'}
            {pendingCount > 0 && <span className="count">{pendingCount}</span>}
          </button>
        </nav>

        <div className="account">
          {user ? (
            <>
              <span className="avatar">{user.name[0].toUpperCase()}</span>
              <span className="account-name">
                {user.name}
                <small>{user.role === 'moderator' ? 'Модератор' : 'Житель'}</small>
              </span>
              <button className="text-button" onClick={logout} disabled={busy}>
                Выйти
              </button>
            </>
          ) : (
            <>
              <button
                className="text-button"
                onClick={() => openAuth('login')}
                disabled={!authChecked}
              >
                Войти
              </button>
              <button
                className="primary small"
                onClick={() => openAuth('register')}
                disabled={!authChecked}
              >
                Регистрация ↗
              </button>
            </>
          )}
        </div>
      </header>

      <main>
        {error && (
          <div className="banner error" role="alert">
            {error}
            <button onClick={() => setError('')} aria-label="Скрыть ошибку">
              ×
            </button>
          </div>
        )}

        {notice && (
          <div className="banner success" role="status">
            {notice}
            <button onClick={() => setNotice('')} aria-label="Скрыть уведомление">
              ×
            </button>
          </div>
        )}

        {tab === 'map' ? (
          <>
            <section className="hero">
              <div>
                <div className="eyebrow">
                  <span className="live-dot" /> ОБНИНСК · УЛИЦА КУРЧАТОВА
                </div>
                <h1>
                  Город ближе.
                  <br />
                  <span>Начните со своей улицы.</span>
                </h1>
                <p>
                  Посмотрите на район глазами пешехода.
                  <br />
                  Предложите изменение — и оцените его влияние на жизнь города.
                </p>
              </div>
              <div className="hero-aside">
                <div className="coordinate">
                  55.1040° N
                  <br />
                  36.6180° E
                </div>
                <div className="hero-stats">
                  <div>
                    <strong>5</strong>
                    <span>жилых домов</span>
                  </div>
                  <div>
                    <strong>{city ? format(city.metrics.total_residents) : '900'}</strong>
                    <span>условных жителей</span>
                  </div>
                </div>
              </div>
            </section>

            {!city ? (
              <div className="empty-state">
                <h2>{error ? 'Карта недоступна' : 'Загружаем улицу…'}</h2>
                <p>Геометрия, маршруты и состояние городской модели.</p>
                {error && (
                  <button className="primary" onClick={refresh}>
                    Попробовать снова
                  </button>
                )}
              </div>
            ) : (
              <>
                <section className="workspace">
                  <ControlPanel
                    mode={mode}
                    setMode={setMode}
                    city={city}
                    stopId={stopId}
                    setStopId={setStopId}
                    onAction={propose}
                    user={user}
                    onLogin={() => openAuth('login')}
                    busy={busy}
                  />
                  <CityMap
                    map={city.map}
                    state={city.state}
                    metrics={city.metrics}
                    mode={mode}
                    stopId={stopId}
                    onAction={propose}
                    selectedHome={selectedHome}
                    setSelectedHome={setSelectedHome}
                  />
                </section>

                <div className="selection-strip">
                  <span>
                    <b>{selectedRow.name}</b> · {selectedRow.residents} условных жителей
                  </span>
                  <span>
                    Остановка <b>{format(selectedRow.stop_distance)} м</b>
                  </span>
                  <span>
                    Парк <b>{format(selectedRow.park_distance)} м</b>
                  </span>
                  <button onClick={refresh} disabled={busy}>
                    ↻ Обновить карту
                  </button>
                </div>

                <section className="analytics">
                  <div className="section-heading">
                    <div>
                      <div className="section-kicker">02 / ДОСТУПНОСТЬ СРЕДЫ</div>
                      <h2>Что говорят маршруты</h2>
                    </div>
                    <span className="pill">
                      Общая карта · версия {city.state.version}
                    </span>
                  </div>

                  <MetricsPanel before={city.metrics} />

                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Жилой объект</th>
                          <th>Жителей</th>
                          <th>До остановки</th>
                          <th>До парка</th>
                          <th>Парк в 500 м</th>
                        </tr>
                      </thead>
                      <tbody>
                        {city.metrics.rows.map((row) => (
                          <tr
                            key={row.id}
                            className={row.id === selectedHome ? 'selected-row' : ''}
                          >
                            <td>
                              <button
                                className="table-link"
                                onClick={() => {
                                  setSelectedHome(row.id);
                                  setMode('inspect');
                                }}
                              >
                                {row.name}
                              </button>
                            </td>
                            <td>{row.residents}</td>
                            <td>
                              {row.stop_distance === null
                                ? 'Нет пути'
                                : format(row.stop_distance) + ' м'}
                            </td>
                            <td>
                              {row.park_distance === null
                                ? 'Нет пути'
                                : format(row.park_distance) + ' м'}
                            </td>
                            <td>
                              <span
                                className={
                                  'access-tag ' + (row.park_access ? 'yes' : 'no')
                                }
                              >
                                {row.park_access ? 'Доступен' : 'Вне доступа'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="method">
                  <div className="section-kicker">03 / ПРОЗРАЧНАЯ МОДЕЛЬ</div>
                  <h2>Реальная улица. Понятные расчёты.</h2>

                  <div className="method-grid">
                    <article>
                      <span>01</span>
                      <h3>Карта из OpenStreetMap</h3>
                      <p>
                        Дома и геометрия дорожек взяты из открытых данных. Модель
                        ограничена участком улицы Курчатова.{' '}
                        <a
                          href={city.map.source.map_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Открыть исходную карту ↗
                        </a>
                      </p>
                    </article>
                    <article>
                      <span>02</span>
                      <h3>Кратчайший путь</h3>
                      <p>
                        Алгоритм Дейкстры на сервере находит путь до ближайшего парка
                        и остановки. Расстояние измеряется по дорожкам, а не по
                        прямой.
                      </p>
                    </article>
                    <article>
                      <span>03</span>
                      <h3>Изменения с проверкой</h3>
                      <p>
                        Выберите объект, оцените расчёт «до / после» и отправьте
                        предложение. Модератор примет решение и закроет заявку.
                      </p>
                    </article>
                  </div>

                  <details>
                    <summary>Допущения и источники данных</summary>
                    <p>{city.map.source.notes}</p>
                    <p>
                      Средний путь до остановки считается по доступным домам без
                      веса населения. Дома без маршрута показаны отдельно. Доля
                      доступа к парку взвешена по условному числу жителей, порог —
                      500 м. Скорость ходьбы, лестницы как барьер, рельеф и
                      светофоры не моделируются.
                    </p>
                    <p>
                      Снимок: {city.map.source.downloaded}. Геоданные:{' '}
                      <a href={city.map.source.url} target="_blank" rel="noreferrer">
                        © OpenStreetMap contributors, ODbL 1.0
                      </a>
                      . Новые зелёные зоны задаются точками доступа, а не земельными
                      участками. Это учебная модель, не план утверждённых городских
                      работ.
                    </p>
                  </details>
                </section>
              </>
            )}
          </>
        ) : (
          <section className="requests-section">
            <div className="section-heading">
              <div>
                <div className="section-kicker">ПРЕДЛОЖЕНИЯ ЖИТЕЛЕЙ</div>
                <h1>
                  {user?.role === 'moderator'
                    ? 'Модерация изменений'
                    : 'Мои заявки'}
                </h1>
                <p>
                  {user?.role === 'moderator'
                    ? 'Оцените влияние, примите решение и закройте заявку.'
                    : 'Все ваши предложения и решения модераторов — в одном месте.'}
                </p>
              </div>
              {user && (
                <button className="secondary" disabled={busy} onClick={refresh}>
                  ↻ Обновить
                </button>
              )}
            </div>

            {!user ? (
              <div className="empty-state">
                <div className="empty-icon">◇</div>
                <h2>У каждого предложения есть автор</h2>
                <p>
                  Войдите или зарегистрируйтесь, чтобы отправлять изменения и
                  следить за их статусом.
                </p>
                <button className="primary" onClick={() => openAuth('login')}>
                  Войти в аккаунт
                </button>
              </div>
            ) : (
              <>
                <div className="request-filters">
                  {FILTERS.map(([id, title]) => (
                    <button
                      key={id}
                      className={filter === id ? 'active' : ''}
                      onClick={() => setFilter(id)}
                    >
                      {title}
                      {id === 'pending' && <span>{pendingCount}</span>}
                    </button>
                  ))}
                </div>

                {visibleItems.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-icon">↗</div>
                    <h2>Пока здесь нет заявок</h2>
                    <p>
                      Начните с карты: выберите дорожку, остановку или место для
                      парка.
                    </p>
                    <button className="primary" onClick={() => setTab('map')}>
                      Перейти к карте
                    </button>
                  </div>
                ) : (
                  <div className="request-list">
                    {visibleItems.map((item) => (
                      <article className="request-card" key={item.id}>
                        <div className="request-card-top">
                          <span className={'status ' + item.status}>
                            {STATUS_LABELS[item.status]}
                          </span>
                          <time>{formatDate(item.created_at)}</time>
                        </div>

                        <h3>{ACTION_NAMES[item.action.type]}</h3>
                        <p className="target-label">
                          {targetLabel(item.action)} · версия карты {item.base_version}
                        </p>
                        <p className="request-reason">{item.reason}</p>

                        {item.status !== 'pending' && (
                          <div className="decision-note">
                            <b>Решение модератора</b>
                            <p>{item.comment}</p>
                            <small>
                              {item.reviewer_name} · {formatDate(item.closed_at)}
                            </small>
                          </div>
                        )}

                        <div className="request-card-bottom">
                          <span>
                            {item.author_name} · #{item.id.slice(0, 8)}
                          </span>
                          {user.role === 'moderator' && item.status === 'pending' && (
                            <button
                              className="primary small"
                              disabled={busy}
                              onClick={() => openReview(item)}
                            >
                              Рассмотреть →
                            </button>
                          )}
                        </div>
                      </article>
                    ))}
                  </div>
                )}

                <p className="muted small-text">
                  После отправки заявка ожидает решения. Одобрение применяет
                  изменение к общей карте; отклонение сохраняет карту. Оба решения
                  закрывают заявку.
                </p>
              </>
            )}
          </section>
        )}

        <footer>
          <span>
            ОБНИНСК <b>2040</b>
          </span>
          <span>Создаём город, в котором хочется ходить пешком.</span>
          <a
            href="https://www.openstreetmap.org/copyright"
            target="_blank"
            rel="noreferrer"
          >
            Данные © OpenStreetMap
          </a>
        </footer>
      </main>

      {auth && (
        <Dialog
          title={auth === 'register' ? 'Присоединиться к городу' : 'С возвращением'}
          onClose={() => setAuth(null)}
          locked={busy}
        >
          <p className="dialog-description">
            {auth === 'register'
              ? 'Создайте аккаунт, чтобы предлагать изменения своей улицы.'
              : 'Войдите, чтобы продолжить работу с предложениями.'}
          </p>

          <form onSubmit={authenticate}>
            {auth === 'register' && (
              <label className="field">
                Имя
                <input
                  name="name"
                  autoComplete="name"
                  minLength="2"
                  maxLength="60"
                  required
                  placeholder="Как к вам обращаться"
                />
              </label>
            )}

            <label className="field">
              Email
              <input
                name="email"
                type="email"
                autoComplete="email"
                required
                maxLength="254"
                placeholder="you@example.com"
              />
            </label>

            <label className="field">
              Пароль
              <input
                name="password"
                type="password"
                autoComplete={
                  auth === 'register' ? 'new-password' : 'current-password'
                }
                minLength="10"
                maxLength="128"
                required
                placeholder="Не менее 10 символов"
              />
            </label>

            {auth === 'register' && (
              <p className="form-note">
                Email используется для входа. Подтверждение email и восстановление
                пароля в этой локальной версии не подключены.
              </p>
            )}

            {authError && (
              <p className="form-error" role="alert">
                {authError}
              </p>
            )}

            <button className="primary full" disabled={busy}>
              {busy
                ? 'Подождите…'
                : auth === 'register'
                  ? 'Создать аккаунт →'
                  : 'Войти →'}
            </button>
          </form>

          <p className="auth-switch">
            {auth === 'register' ? 'Уже зарегистрированы?' : 'Пока нет аккаунта?'}{' '}
            <button
              disabled={busy}
              onClick={() => openAuth(auth === 'register' ? 'login' : 'register')}
            >
              {auth === 'register' ? 'Войти' : 'Зарегистрироваться'}
            </button>
          </p>
        </Dialog>
      )}

      {draft && (
        <Dialog
          title="Отправить изменение на модерацию"
          wide
          locked={busy}
          onClose={() => {
            setDraft(null);
            setPreview(null);
          }}
        >
          <div className="proposal-heading">
            <span className="status pending">ПРЕДЛОЖЕНИЕ</span>
            <h3>{ACTION_NAMES[draft.action.type]}</h3>
            <p>
              {targetLabel(draft.action)} · версия {draft.base_version}
            </p>
          </div>

          {preview ? (
            <>
              <p className="dialog-description">
                Так изменится доступность, если предложение одобрят. Сейчас общая
                карта остаётся прежней.
              </p>
              <MetricsPanel
                before={preview.before}
                after={preview.after}
                compact
              />
              <div className="mini-map">
                <CityMap
                  map={city.map}
                  state={preview.state}
                  metrics={preview.after}
                  mode="inspect"
                  stopId={stopId}
                  onAction={() => {}}
                  selectedHome={selectedHome}
                  setSelectedHome={setSelectedHome}
                  previewing
                />
              </div>
            </>
          ) : (
            !previewError && <p className="loading-text">Рассчитываем маршруты…</p>
          )}

          {previewError && (
            <p className="form-error" role="alert">
              {previewError}
            </p>
          )}

          <form onSubmit={submit}>
            <label className="field">
              Почему это нужно району?
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                minLength="10"
                maxLength="1000"
                required
                rows="3"
                placeholder="Опишите проблему и пользу изменения. Не менее 10 символов."
              />
            </label>

            <div className="form-actions">
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => {
                  setDraft(null);
                  setPreview(null);
                }}
              >
                Отмена
              </button>
              <button
                className="primary"
                disabled={busy || !preview || reason.trim().length < 10}
              >
                {busy ? 'Подождите…' : 'Отправить на модерацию →'}
              </button>
            </div>
          </form>
        </Dialog>
      )}

      {review && (
        <Dialog
          title="Рассмотрение заявки"
          wide
          locked={busy}
          onClose={() => setReview(null)}
        >
          <div className="proposal-heading">
            <span className={'status ' + review.status}>
              {STATUS_LABELS[review.status]}
            </span>
            <h3>{ACTION_NAMES[review.action.type]}</h3>
            <p>
              {targetLabel(review.action)} · {review.author_name} ·{' '}
              {formatDate(review.created_at)}
            </p>
          </div>

          <blockquote>{review.reason}</blockquote>

          {reviewData && (
            <>
              <MetricsPanel
                before={reviewData.before}
                after={reviewData.after}
                compact
              />
              <div className="mini-map">
                <CityMap
                  map={city.map}
                  state={reviewData.state}
                  metrics={reviewData.after}
                  mode="inspect"
                  stopId={stopId}
                  onAction={() => {}}
                  selectedHome={selectedHome}
                  setSelectedHome={setSelectedHome}
                  previewing
                />
              </div>
            </>
          )}

          {reviewError && (
            <p className="form-error" role="alert">
              {reviewError}
            </p>
          )}

          {busy && !reviewData && <p>Загружаем расчёт…</p>}

          {review.author_id === user?.id ? (
            <p className="form-note">
              Свою заявку нельзя рассмотреть самостоятельно. Её должен проверить
              другой модератор.
            </p>
          ) : (
            <>
              <label className="field">
                Обоснование решения
                <textarea
                  rows="3"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  minLength="5"
                  maxLength="1000"
                  placeholder="Комментарий будет виден автору заявки"
                />
              </label>

              <p className="form-note">
                Решение закроет заявку. Одобренное изменение сразу попадёт на общую
                карту. Устаревшую заявку можно отклонить и попросить автора
                отправить новую.
              </p>

              <div className="form-actions">
                <button
                  className="danger-button"
                  disabled={busy || comment.trim().length < 5}
                  onClick={() => decide('rejected')}
                >
                  Отклонить и закрыть
                </button>
                <button
                  className="primary"
                  disabled={busy || !reviewData || comment.trim().length < 5}
                  onClick={() => decide('approved')}
                >
                  Одобрить и закрыть
                </button>
              </div>
            </>
          )}
        </Dialog>
      )}
    </>
  );
}