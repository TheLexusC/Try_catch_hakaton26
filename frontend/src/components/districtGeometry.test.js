import { test } from 'node:test';
import assert from 'node:assert/strict';
import { boundaryError } from './districtGeometry.js';

const points = xs => xs.map(([x, y]) => ({ x, y }));

test('rejects an unfinished, repeated, crossed or tiny boundary before proceeding', () => {
  assert.match(boundaryError(points([[0, 0], [100, 0]])), /3/);
  assert.match(boundaryError(points([[0, 0], [100, 0], [0, 0]])), /совпадают/);
  assert.match(boundaryError(points([[0, 0], [100, 100], [0, 100], [100, 0]])), /пересекает/);
  assert.match(boundaryError(points([[0, 0], [1, 0], [0, 1]])), /25/);
});

test('a mistaken vertex can be undone and replaced with a valid boundary', () => {
  const draft = points([[0, 0], [100, 0], [0, 100], [100, 100]]);
  assert.ok(boundaryError(draft));
  
  const corrected = [...draft.slice(0, -1), { x: -1, y: 0 }];
  assert.ok(boundaryError(corrected));
  
  assert.equal(boundaryError(points([[0, 0], [100, 0], [100, 100], [0, 100]])), '');
  assert.equal(boundaryError(points([[0, 0], [100, 0], [100, 100], [50, 50], [0, 100]])), '');
});


