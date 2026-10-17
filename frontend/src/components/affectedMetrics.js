// Existing residents are compared on a fixed cohort; new homes have no baseline.
export function summarizeHomes(metrics, ids) {
  const chosen = new Set(ids);
  const rows = metrics.rows.filter(r => chosen.has(r.id));
  const reachable = rows.filter(r => r.stop_distance !== null);
  const parks = rows.filter(r => r.park_distance !== null);
  
  const residents = rows.reduce((n, r) => n + r.residents, 0);
  const parkResidents = rows
    .filter(r => r.park_distance !== null && r.park_distance <= (metrics.radius || 500))
    .reduce((n, r) => n + r.residents, 0);
  const stopResidents = rows
    .filter(r => r.stop_distance !== null && r.stop_distance <= 500)
    .reduce((n, r) => n + r.residents, 0);
    
  return {
    average_stop: reachable.length ? Math.round((reachable.reduce((n, r) => n + r.stop_distance, 0) / reachable.length) * 10) / 10 : null,
    average_park: parks.length ? Math.round((parks.reduce((n, r) => n + r.park_distance, 0) / parks.length) * 10) / 10 : null,
    park_percent: residents ? Math.round((parkResidents / residents) * 1000) / 10 : null,
    transport_access: residents ? Math.round((stopResidents / residents) * 1000) / 10 : null,
    park_residents: parkResidents,
    stop_residents: stopResidents,
    residents,
    home_count: rows.length
  };
}

export function affectedMetrics(before, after) {
  const old = new Map(before.rows.map(h => [h.id, h]));
  const next = new Map(after.rows.map(h => [h.id, h]));
  
  const added = [...next.keys()].filter(id => !old.has(id));
  const removed = [...old.keys()].filter(id => !next.has(id));
  
  const ids = [...old.keys()].filter(id => {
    const a = old.get(id);
    const b = next.get(id);
    if (!b) return false;
    
    const primitivesChanged = ['residents', 'stop_distance', 'park_distance', 'stop_target', 'park_target'].some(k => a[k] !== b[k]);
    const pathsChanged = ['stop_path', 'park_path', 'stop_route', 'park_route'].some(k => JSON.stringify(a[k] || []) !== JSON.stringify(b[k] || []));
    
    return primitivesChanged || pathsChanged;
  });
  
  return {
    before: summarizeHomes(before, ids),
    after: summarizeHomes(after, ids),
    newHomes: summarizeHomes(after, added),
    removedHomes: summarizeHomes(before, removed),
    count: ids.length,
    added: added.length,
    removed: removed.length
  };
}


