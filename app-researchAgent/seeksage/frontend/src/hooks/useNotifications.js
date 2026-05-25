import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";

export function useNotifications() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setItems(await api.listNotifications());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const addNotification = useCallback((payload) => {
    return api.createNotification(payload).then((item) => {
      setItems((prev) => [item, ...prev]);
      return item;
    });
  }, []);

  const markRead = useCallback((id) => {
    return api.updateNotification(id, { read: true }).then((item) => {
      setItems((prev) => prev.map((n) => (n.id === id ? item : n)));
      return item;
    });
  }, []);

  const markAllRead = useCallback(() => {
    return api.markAllNotificationsRead().then(() => {
      setItems((prev) => prev.map((n) => ({ ...n, read: true })));
    });
  }, []);

  const removeNotification = useCallback((id) => {
    return api.deleteNotification(id).then(() => {
      setItems((prev) => prev.filter((n) => n.id !== id));
    });
  }, []);

  const unreadCount = useMemo(() => items.filter((n) => !n.read).length, [items]);

  return {
    notifications: items,
    loading,
    error,
    unreadCount,
    reload: load,
    addNotification,
    markRead,
    markAllRead,
    removeNotification,
  };
}
