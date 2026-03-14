import { useState, useCallback } from "react";

export function useApi() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const call = useCallback(async (url, options = {}) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(url, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Request failed");
      }
      const data = await res.json();
      return data;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { call, loading, error };
}
