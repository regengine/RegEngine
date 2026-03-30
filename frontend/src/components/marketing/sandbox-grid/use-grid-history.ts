'use client';

import { useState, useCallback } from 'react';

interface HistoryState<T> {
  past: T[];
  present: T;
  future: T[];
}

/**
 * Undo/redo hook for the grid data.
 * Stores snapshots as string[][] (rows x columns).
 * Max 50 undo levels to bound memory.
 */
export function useGridHistory(initialData: string[][]) {
  const [state, setState] = useState<HistoryState<string[][]>>({
    past: [],
    present: initialData,
    future: [],
  });

  const push = useCallback((newData: string[][]) => {
    setState((s) => ({
      past: [...s.past.slice(-49), s.present],
      present: newData,
      future: [],
    }));
  }, []);

  const undo = useCallback(() => {
    setState((s) => {
      if (s.past.length === 0) return s;
      const prev = s.past[s.past.length - 1];
      return {
        past: s.past.slice(0, -1),
        present: prev,
        future: [s.present, ...s.future],
      };
    });
  }, []);

  const redo = useCallback(() => {
    setState((s) => {
      if (s.future.length === 0) return s;
      const next = s.future[0];
      return {
        past: [...s.past, s.present],
        present: next,
        future: s.future.slice(1),
      };
    });
  }, []);

  const reset = useCallback((data: string[][]) => {
    setState({ past: [], present: data, future: [] });
  }, []);

  return {
    data: state.present,
    push,
    undo,
    redo,
    reset,
    canUndo: state.past.length > 0,
    canRedo: state.future.length > 0,
  };
}
