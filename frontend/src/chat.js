// Chat history belongs to this browser/device. Never import the swarm's last_result.
export const CHAT_KEY = 'open-swarm-device-chats-v2';
const LEGACY_KEY = 'open-swarm-chats-v1';
export const chatTitle = prompt => prompt.trim().replace(/\s+/g, ' ').slice(0, 46) || 'New chat';

// Keep the existing single-prompt API. Include only complete, recent exchanges.
export function conversationPrompt(turns, prompt, limit, sample) {
  if (prompt === sample) return { prompt, included: 0, omitted: turns.length };
  const pairs = turns.filter(t => t.prompt && !t.restored && t.status === 'complete' && t.output);
  const prefix = 'Continue this conversation. Answer the latest user message.\n\n';
  const suffix = `User: ${prompt}\nAssistant:`;
  let history = '', included = 0;
  for (const turn of [...pairs].reverse()) {
    const pair = `User: ${turn.prompt}\nAssistant: ${turn.output}\n\n`;
    if ((prefix + pair + history + suffix).length > limit) break;
    history = pair + history; included++;
  }
  return { prompt: included ? prefix + history + suffix : prompt, included, omitted: pairs.length - included };
}

export const newChat = () => ({ id: crypto.randomUUID(), title: 'New chat', draft: '', turns: [], updatedAt: Date.now(), draftUpdatedAt: Date.now() });

export function readChats(storage, key, recoverStreams = true) {
  try {
    const saved = JSON.parse(storage.getItem(key));
    if (!Array.isArray(saved?.chats) || !saved.chats.every(c =>
      typeof c.id === 'string' && typeof c.title === 'string' && typeof c.draft === 'string' && Array.isArray(c.turns) &&
      c.turns.every(t => typeof t.id === 'string' && typeof t.output === 'string' && (!t.prompt || typeof t.prompt === 'string')))) return null;
    return { ...saved, chats: saved.chats.map(c => ({...c, turns: c.turns.map(t =>
      recoverStreams && t.status === 'streaming' ? {...t, status: 'incomplete', error: 'Stream interrupted. This saved partial response is incomplete.'} : t)})) };
  } catch { return null; }
}

export function deviceChats(chats) {
  // Only the old coordinator imports are removed. Preserve locally submitted
  // follow-ups and drafts, even when they were entered in an imported chat.
  return chats.flatMap(chat => {
    const turns = chat.turns.filter(turn => !turn.restored);
    const hadImports = turns.length !== chat.turns.length;
    if (hadImports && !turns.length && !chat.draft.trim()) return [];
    return [{...chat, turns, title: hadImports ? chatTitle(turns.find(t => t.prompt)?.prompt || '') : chat.title}];
  });
}

export function loadDeviceChats(storage) {
  const saved = readChats(storage, CHAT_KEY, false) ?? readChats(storage, LEGACY_KEY, false);
  if (!saved) return null;
  const chats = deviceChats(saved.chats);
  return {...saved, chats, activeId: chats.some(c => c.id === saved.activeId) ? saved.activeId : chats[0]?.id};
}

// Same-device tabs merge append-only messages by ID. Message updates cannot
// overwrite a draft edited in another tab, or erase a newer completed reply.
export function mergeChats(local, stored) {
  const merged = new Map(deviceChats(stored).map(chat => [chat.id, chat]));
  for (const chat of deviceChats(local)) {
    const previous = merged.get(chat.id);
    if (!previous) { merged.set(chat.id, chat); continue; }
    const latest = (chat.updatedAt || 0) >= (previous.updatedAt || 0) ? chat : previous;
    const draft = (chat.draftUpdatedAt || 0) >= (previous.draftUpdatedAt || 0) ? chat : previous;
    const turns = new Map(previous.turns.map(turn => [turn.id, turn]));
    for (const turn of chat.turns) {
      const old = turns.get(turn.id);
      if (!old || (turn.updatedAt || 0) > (old.updatedAt || 0) ||
          ((turn.updatedAt || 0) === (old.updatedAt || 0) && old.status !== 'complete')) turns.set(turn.id, turn);
    }
    merged.set(chat.id, {...latest, draft: draft.draft, draftUpdatedAt: draft.draftUpdatedAt,
      turns: [...turns.values()].sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0))});
  }
  return [...merged.values()].sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
}
