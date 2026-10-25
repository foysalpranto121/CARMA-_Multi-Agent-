import { useEffect, useRef, useState } from 'react';
import { useAuthStore } from '../store/authStore';

const MAX_CASES = 200;

/**
 * Live stream of one experiment run (`/ws/experiments/<id>/logs/`).
 *
 * The backend pushes a `progress` message and a `case_complete` message for
 * every finished case; `onEvent` is called with each message so the page can
 * refresh what it shows.  While the socket is closed the page falls back to
 * polling, so a dropped connection only makes the view slower, never stale.
 */
export function useRunStream(runId, { onEvent } = {}) {
  const token = useAuthStore((s) => s.accessToken);
  const [connected, setConnected] = useState(false);
  const [progress, setProgress] = useState(null);
  const [cases, setCases] = useState([]);
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    if (!runId || !token) return undefined;
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const socket = new WebSocket(
      `${scheme}://${window.location.host}/ws/experiments/${runId}/logs/`
      + `?token=${encodeURIComponent(token)}`,
    );
    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onmessage = ({ data }) => {
      let message;
      try {
        message = JSON.parse(data);
      } catch {
        return;
      }
      if (message.type === 'progress') setProgress(message);
      if (message.type === 'case_complete') {
        setCases((previous) => [message, ...previous].slice(0, MAX_CASES));
      }
      handler.current?.(message);
    };
    return () => socket.close();
  }, [runId, token]);

  return { connected, progress, cases };
}
