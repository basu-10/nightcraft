import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../api";

const POLL_INTERVAL_MS = 1500;
const TERMINAL_STATUSES = new Set(["done", "error"]);

/**
 * Poll a run until it reaches a terminal status (done / error).
 * Returns { run, events, polling }.
 */
export function useRunPoller(runId) {
  const [run, setRun] = useState(null);
  const [events, setEvents] = useState([]);
  const [polling, setPolling] = useState(false);
  const timerRef = useRef(null);
  const runIdRef = useRef(runId);

  const stop = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setPolling(false);
  }, []);

  const poll = useCallback(async () => {
    const id = runIdRef.current;
    if (!id) return;
    try {
      const [runData, eventsData] = await Promise.all([
        api.getRun(id),
        api.listRunEvents(id),
      ]);
      setRun(runData);
      setEvents(eventsData);
      if (TERMINAL_STATUSES.has(runData.status)) {
        stop();
        return;
      }
    } catch {
      // keep polling on transient errors
    }
    timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
  }, [stop]);

  useEffect(() => {
    runIdRef.current = runId;
    if (!runId) {
      stop();
      setRun(null);
      setEvents([]);
      return;
    }
    setPolling(true);
    poll();
    return stop;
  }, [runId, poll, stop]);

  return { run, events, polling };
}
