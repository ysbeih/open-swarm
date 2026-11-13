import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { CHAT_KEY, conversationPrompt, readChats, loadDeviceChats, deviceChats, mergeChats } from '../../frontend/src/chat.js';
// Exercise the guest's actual helper without introducing another served asset/API route.
const source = fs.readFileSync(new URL('../../guest/guest.js', import.meta.url), 'utf8');
const guestContext = vm.createContext({});
vm.runInContext(source.slice(source.indexOf('function conversationPrompt('), source.indexOf('\nfunction controls()')), guestContext);
for (const [name, build] of [['dashboard', conversationPrompt], ['guest', guestContext.conversationPrompt]]) {
  test(`${name}: follow-ups retain complete pairs, never incomplete or imported answers`, () => {
    const turns = [{prompt:'Remember cedar', output:'cedar', status:'complete'}, {prompt:'bad',output:'partial',status:'incomplete'}, {output:'saved',status:'complete'}];
    const result = build(turns, 'Which word?', 2000);
    assert.match(result.prompt, /Remember cedar/); assert.match(result.prompt, /User: Which word?/);
    assert.equal(result.included, 1); assert.doesNotMatch(result.prompt, /partial|saved/);
    assert.equal(build([], 'A new chat', 2000).prompt, 'A new chat');
  });
  test(`${name}: bounded suffix keeps the latest whole pairs without cutting the user's input`, () => {
    const turns = [{prompt:'old'.repeat(700),output:'old answer',status:'complete'}, {prompt:'recent',output:'answer',status:'complete'}];
    const result = build(turns, 'follow-up', 2000);
    assert.equal(result.included, 1); assert.equal(result.omitted, 1); assert.ok(result.prompt.length <= 2000);
    const full = 'x'.repeat(2000);
    assert.equal(build(turns, full, 2000).prompt, full);
  });
  test(`${name}: exact sample bypasses conversational context`, () => {
    assert.equal(build([{prompt:'prior', output:'answer',status:'complete'}], 'sample', 2000, 'sample').prompt, 'sample');
  });
}
test('dashboard: restore history marks interrupted streams incomplete and preserves complete output', () => {
  const chats = [{id:'chat',title:'Test',draft:'unsent',turns:[{id:'1',output:'partial',status:'streaming'}, {id:'2',output:'done',status:'complete', result:{request_id:'request'}}]}];
  const result = readChats({getItem:()=>JSON.stringify({chats,activeId:'chat'})}, 'key');
  assert.equal(result.chats[0].turns[0].status, 'incomplete');
  assert.equal(result.chats[0].turns[1].result.request_id, 'request');
  assert.equal(result.chats[0].draft, 'unsent');
  assert.equal(readChats({getItem:()=>'{bad'}, 'key'), null);
  assert.equal(readChats({getItem:()=>JSON.stringify({chats:[{}]})}, 'key'), null);
});

test('dashboard: a background tab preserves other chats and newer saved turns', () => {
  const old = {id:'a', updatedAt:1, turns:[]}, recent = {id:'a',updatedAt:3,turns:[{id:'turn',output:'latest',status:'complete'}]};
  const other = {id:'b',updatedAt:2,turns:[]};
  const merged = mergeChats([old], [recent, other]);
  assert.equal(merged.length, 2);
  assert.equal(merged.find(c => c.id === 'a').turns[0].output, 'latest');
});

function memoryStorage(values = {}) {
  return {getItem:key => values[key] ?? null, setItem:(key,value) => {values[key] = value;}};
}
test('device migration removes coordinator imports and preserves local messages and drafts', () => {
  const imported = {id:'shared',title:'Saved coordinator answer',draft:'',turns:[{id:'remote',output:'someone else',status:'complete',restored:true}]};
  const own = {id:'own',title:'My prompt',draft:'my draft',turns:[{id:'local',prompt:'My prompt',output:'my answer',status:'complete'}]};
  const mixed = {...imported,id:'mixed',turns:[...imported.turns,...own.turns]};
  const storage = memoryStorage({'open-swarm-chats-v1':JSON.stringify({chats:[imported,own,mixed],activeId:'shared'})});
  const result = loadDeviceChats(storage);
  assert.deepEqual(result.chats.map(c=>c.id), ['own','mixed']);
  assert.equal(result.activeId, 'own');
  assert.equal(result.chats[0].draft, 'my draft');
  assert.equal(result.chats[1].title, 'My prompt');
  assert.ok(result.chats.every(c => c.turns.every(t=>!t.restored)));
  assert.match(storage.getItem('open-swarm-chats-v1'), /someone else/); // Leave legacy backup intact.
});
test('device storage does not discover chats from another browser/device', () => {
  const first = memoryStorage({[CHAT_KEY]:JSON.stringify({chats:[{id:'a',title:'Only here',draft:'',turns:[]}],activeId:'a'})});
  const second = memoryStorage();
  assert.equal(loadDeviceChats(first).chats[0].title, 'Only here');
  assert.equal(loadDeviceChats(second), null);
  assert.deepEqual(deviceChats([{id:'remote',title:'Saved coordinator answer',draft:'',turns:[{id:'r',output:'remote',restored:true}]}]), []);
});
test('same-device tabs retain distinct turns and newer drafts without downgrading completed replies', () => {
  const first = {id:'a',title:'Test',draft:'older',draftUpdatedAt:1,updatedAt:4,turns:[
    {id:'one',prompt:'one',output:'answer one',status:'complete',createdAt:1,updatedAt:3},
    {id:'two',prompt:'two',output:'answer two',status:'complete',createdAt:2,updatedAt:4}]};
  const second = {id:'a',title:'Test',draft:'newer draft',draftUpdatedAt:5,updatedAt:5,turns:[
    {id:'one',prompt:'one',output:'partial',status:'streaming',createdAt:1,updatedAt:2}]};
  const [merged] = mergeChats([second], [first]);
  assert.equal(merged.draft, 'newer draft');
  assert.deepEqual(merged.turns.map(t=>t.id), ['one','two']);
  assert.equal(merged.turns[0].output, 'answer one');
  assert.equal(merged.turns[0].status, 'complete');
  assert.deepEqual(mergeChats([merged], [merged]), [merged]);
});
test('new history takes precedence over the legacy shared history', () => {
  const storage = memoryStorage({[CHAT_KEY]:JSON.stringify({chats:[]}),
    'open-swarm-chats-v1':JSON.stringify({chats:[{id:'old',title:'Old',draft:'',turns:[]}]})});
  assert.deepEqual(loadDeviceChats(storage).chats, []);
});
