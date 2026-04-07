'use client';

import React, { useEffect, useCallback, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';

export interface KeyboardShortcut {
  key: string;
  ctrl?: boolean;
  meta?: boolean;
  alt?: boolean;
  shift?: boolean;
  description: string;
  action: () => void;
}

export function useKeyboardShortcuts(shortcuts: KeyboardShortcut[], enabled = true) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!enabled) return;

      // Don't trigger shortcuts when typing in inputs
      const target = e.target as HTMLElement;
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable
      ) {
        return;
      }

      for (const shortcut of shortcuts) {
        const ctrlMatch = shortcut.ctrl ? e.ctrlKey : !e.ctrlKey;
        const metaMatch = shortcut.meta ? e.metaKey : !e.metaKey;
        const altMatch = shortcut.alt ? e.altKey : !e.altKey;
        const shiftMatch = shortcut.shift ? e.shiftKey : !e.shiftKey;
        const keyMatch = e.key.toLowerCase() === shortcut.key.toLowerCase();

        if (keyMatch && ctrlMatch && metaMatch && altMatch && shiftMatch) {
          e.preventDefault();
          shortcut.action();
          return;
        }
      }
    },
    [shortcuts, enabled]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
}

// Global navigation shortcuts
export function useGlobalShortcuts() {
  const router = useRouter();

  const shortcuts: KeyboardShortcut[] = [
    {
      key: 'h',
      meta: true,
      description: 'Go to Home',
      action: () => router.push('/'),
    },
    {
      key: 'i',
      meta: true,
      description: 'Go to Ingest',
      action: () => router.push('/ingest'),
    },
    {
      key: 'r',
      meta: true,
      description: 'Go to Review',
      action: () => router.push('/review'),
    },
    {
      key: 'c',
      meta: true,
      description: 'Go to Compliance',
      action: () => router.push('/compliance'),
    },
    {
      key: 'o',
      meta: true,
      description: 'Go to Opportunities',
      action: () => router.push('/opportunities'),
    },
    {
      key: 'a',
      meta: true,
      description: 'Go to Admin',
      action: () => router.push('/admin'),
    },
    {
      key: '/',
      meta: true,
      description: 'Show keyboard shortcuts',
      action: () => {
        // Dispatch custom event that can be listened to
        window.dispatchEvent(new CustomEvent('show-shortcuts-dialog'));
      },
    },
  ];

  useKeyboardShortcuts(shortcuts);

  return shortcuts;
}

// Keyboard shortcut dialog component
export function KeyboardShortcutsProvider({ children }: { children: React.ReactNode }) {
  const [showDialog, setShowDialog] = useState(false);
  const shortcuts = useGlobalShortcuts();

  useEffect(() => {
    const handleShowDialog = () => setShowDialog(true);
    window.addEventListener('show-shortcuts-dialog', handleShowDialog);
    return () => window.removeEventListener('show-shortcuts-dialog', handleShowDialog);
  }, []);

  return (
    <>
      {children}
      <KeyboardShortcutsDialog
        isOpen={showDialog}
        onClose={() => setShowDialog(false)}
        shortcuts={shortcuts}
      />
    </>
  );
}

interface KeyboardShortcutsDialogProps {
  isOpen: boolean;
  onClose: () => void;
  shortcuts: KeyboardShortcut[];
}

function KeyboardShortcutsDialog({ isOpen, onClose, shortcuts }: KeyboardShortcutsDialogProps) {
  useEffect(() => {
    if (!isOpen) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };

    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const isMac = typeof navigator !== 'undefined' && navigator.platform.toUpperCase().indexOf('MAC') >= 0;
  const modKey = isMac ? '⌘' : 'Ctrl';

  return (
    <>
      <div
        className="fixed inset-0 z-50 bg-black/50"
        onClick={onClose}
      />
      <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border bg-card p-6 shadow-2xl">
        <h2 className="text-xl font-semibold mb-4">Keyboard Shortcuts</h2>
        <div className="space-y-2">
          {shortcuts.map((shortcut) => (
            <div
              key={shortcut.key}
              className="flex items-center justify-between py-2 border-b last:border-0"
            >
              <span className="text-sm text-muted-foreground">
                {shortcut.description}
              </span>
              <kbd className="px-2 py-1 rounded bg-muted text-xs font-mono">
                {shortcut.meta && `${modKey}+`}
                {shortcut.ctrl && 'Ctrl+'}
                {shortcut.alt && 'Alt+'}
                {shortcut.shift && 'Shift+'}
                {shortcut.key.toUpperCase()}
              </kbd>
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs text-muted-foreground text-center">
          Press <kbd className="px-1 py-0.5 rounded bg-muted text-xs">Esc</kbd> to close
        </p>
      </div>
    </>
  );
}
