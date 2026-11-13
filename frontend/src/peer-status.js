// Reachability and owner consent do not establish that a model is loaded.
export function peerContribution(peer, coordinator, fresh = true) {
  const online = fresh && !!peer.online;
  const base = { online, sharingEnabled: online && !!peer.sharing, memoryInUse: false };
  const status = (label, detail, tone = 'idle') => ({ ...base, label, detail, tone });
  if (!fresh) return status('Status unavailable', 'Waiting for a fresh status update.', 'unknown');
  if (!online) return status('Not reachable', 'Memory contribution cannot be confirmed.', 'unknown');
  if (peer.state === 'failed') return status('Needs attention', 'Model contribution is not ready.', 'warning');
  if (peer.state === 'stopping' || (!peer.sharing && peer.runtime?.running)) {
    return status('Releasing memory', 'The native runtime is stopping.', 'loading');
  }
  if (!peer.sharing) return status('Not sharing', 'The peer app is online. Sharing is switched off.');
  if (!peer.session) return status('Sharing enabled', 'Available to contribute to the next session.', 'available');

  const sameSession = peer.session.id && coordinator?.session?.id === peer.session.id &&
    peer.session.coordinator === coordinator?.id && coordinator?.session?.members?.includes(peer.id);
  if (!sameSession || !coordinator?.online || coordinator.state === 'failed') {
    return status('Session unavailable', 'Cannot confirm that this peer holds a loaded model.', 'warning');
  }
  const loaded = coordinator.runtime?.running && peer.runtime?.running &&
    ['ready', 'computing'].includes(coordinator.state) &&
    ['ready', 'computing', 'worker_ready'].includes(peer.state);
  if (loaded) return {
    ...base, memoryInUse: true, tone: 'loaded', label: 'Memory in use',
    detail: coordinator.busy || coordinator.state === 'computing'
      ? 'Model loaded · session generating'
      : 'Model loaded · waiting for requests',
  };
  if (coordinator.state === 'loading' && peer.runtime?.running) {
    return status('Loading model', 'Preparing the model slice in memory.', 'loading');
  }
  return status('Preparing session', 'Sharing is enabled; model loading is not confirmed.', 'available');
}
