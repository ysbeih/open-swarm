import { test } from 'node:test';
import assert from 'node:assert/strict';
import { peerContribution } from '../../frontend/src/peer-status.js';

const session = { id: 'current', coordinator: 'a', members: ['a', 'b', 'c'] };
const coordinator = { id: 'a', online: true, sharing: true, state: 'ready', session, runtime: { running: true } };
const worker = { id: 'b', online: true, sharing: true, state: 'worker_ready', session, runtime: { running: true, rss_bytes: 2e9 } };

test('a reachable peer and an offered budget do not prove loaded model memory', () => {
  const idle = { ...worker, session: null, state: 'off', sharing: false, runtime: { running: false, rss_bytes: 50e6 } };
  const off = peerContribution(idle, null);
  assert.equal(off.online, true);
  assert.equal(off.label, 'Not sharing');
  assert.equal(off.memoryInUse, false);
  const offered = peerContribution({ ...idle, sharing: true, state: 'offered' }, null);
  assert.equal(offered.label, 'Sharing enabled');
  assert.equal(offered.sharingEnabled, true);
  assert.equal(offered.memoryInUse, false);
});

test('an idle loaded session still holds model memory on workers and coordinator', () => {
  for (const peer of [worker, coordinator]) {
    const status = peerContribution(peer, coordinator);
    assert.equal(status.label, 'Memory in use');
    assert.equal(status.memoryInUse, true);
    assert.match(status.detail, /waiting for requests/);
  }
  const busy = peerContribution(worker, { ...coordinator, busy: true });
  assert.equal(busy.memoryInUse, true);
  assert.match(busy.detail, /session generating/);
});

test('a worker process during loading is not a confirmed loaded model', () => {
  const status = peerContribution(worker, { ...coordinator, state: 'loading' });
  assert.equal(status.label, 'Loading model');
  assert.equal(status.memoryInUse, false);
});

test('stale, offline and stopped processes cannot retain a positive contribution badge', () => {
  assert.equal(peerContribution(worker, coordinator, false).label, 'Status unavailable');
  for (const [peer, leader, fresh] of [
    [{ ...worker, online: false }, coordinator, true],
    [worker, coordinator, false],
    [{ ...worker, runtime: { running: false } }, coordinator, true],
    [worker, { ...coordinator, runtime: { running: false } }, true],
    [worker, { ...coordinator, online: false }, true],
    [worker, { ...coordinator, state: 'failed' }, true],
  ]) assert.equal(peerContribution(peer, leader, fresh).memoryInUse, false);
});

test('readiness from a different session or roster cannot confirm this peer', () => {
  for (const session of [
    { id: 'old', coordinator: 'a', members: ['a', 'b', 'c'] },
    { id: 'current', coordinator: 'c', members: ['a', 'b', 'c'] },
  ]) assert.equal(peerContribution({ ...worker, session }, coordinator).memoryInUse, false);
  assert.equal(peerContribution(worker, { ...coordinator, session: { ...session, members: ['a', 'c'] } }).memoryInUse, false);
  assert.equal(peerContribution(worker, undefined).memoryInUse, false);
});

test('withdrawal and failure override stale loaded-runtime evidence', () => {
  assert.equal(peerContribution({ ...worker, sharing: false }, coordinator).label, 'Releasing memory');
  assert.equal(peerContribution({ ...worker, state: 'stopping' }, coordinator).memoryInUse, false);
  assert.equal(peerContribution({ ...worker, state: 'failed' }, coordinator).label, 'Needs attention');
});
