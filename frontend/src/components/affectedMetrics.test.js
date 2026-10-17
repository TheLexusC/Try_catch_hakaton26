import { test } from 'node:test';
import assert from 'node:assert/strict';
import { affectedMetrics } from './affectedMetrics.js';

const home = (id, stop, park, residents = 100) => ({
  id, 
  stop_distance: stop, 
  park_distance: park, 
  residents, 
  stop_path: ['a'], 
  park_path: ['b']
});

test('unchanged homes do not dilute affected metrics; new and removed homes have no fake baseline', () => {
  const before = { radius: 500, rows: [home('unchanged', 1000, 1000, 10000), home('changed', 200, 600), home('removed', 400, 100)] };
  const after = { radius: 500, rows: [home('unchanged', 1000, 1000, 10000), home('changed', 100, 400), home('new', 50, 100, 200)] };
  const r = affectedMetrics(before, after);
  
  assert.equal(r.count, 1);
  assert.equal(r.added, 1);
  assert.equal(r.removed, 1);
  assert.equal(r.before.average_stop, 200);
  assert.equal(r.after.average_stop, 100);
  assert.equal(r.before.park_percent, 0);
  assert.equal(r.after.park_percent, 100);
  assert.equal(r.newHomes.residents, 200);
  assert.equal(r.newHomes.park_percent, 100);
});

test('no affected homes yields no measurement rather than misleading zero', () => {
  const m = { rows: [home('a', 100, 100)] };
  const r = affectedMetrics(m, m);
  
  assert.equal(r.count, 0);
  assert.equal(r.after.average_stop, null);
  assert.equal(r.after.park_percent, null);
});

test('new-only district has no fabricated before/after percentage', () => {
  const r = affectedMetrics({ rows: [] }, { radius: 500, rows: [home('new', 40, 800, 200)] });
  
  assert.equal(r.count, 0);
  assert.equal(r.before.park_percent, null);
  assert.equal(r.after.park_percent, null);
  assert.equal(r.newHomes.park_percent, 0);
  assert.equal(r.newHomes.transport_access, 100);
  assert.equal(r.newHomes.residents, 200);
});


