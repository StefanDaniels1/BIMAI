'use client';

import { Check, ClipboardCopy } from 'lucide-react';
import { useState } from 'react';
import { startPrompt } from '@/lib/prompts';

/** Copy text, also on plain-http pages where navigator.clipboard is unavailable. */
async function copyText(text: string): Promise<boolean> {
  try {
    if (window.isSecureContext && navigator.clipboard) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the fallback
  }
  const area = document.createElement('textarea');
  area.value = text;
  area.setAttribute('readonly', '');
  area.style.position = 'fixed';
  area.style.opacity = '0';
  document.body.appendChild(area);
  area.select();
  const ok = document.execCommand('copy');
  document.body.removeChild(area);
  return ok;
}

/** A large "Copy prompt" button with a preview of what gets copied. */
export function CopyPrompt({
  prompt,
  label = 'Copy prompt',
  hint = 'Then paste it into Claude Code, in your project folder.',
}: {
  prompt: string;
  label?: string;
  hint?: string;
}) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');

  async function onClick() {
    setState((await copyText(prompt)) ? 'copied' : 'failed');
    setTimeout(() => setState('idle'), 4000);
  }

  return (
    <div className="not-prose my-6 rounded-xl border border-fd-border bg-fd-card p-6 shadow-sm">
      <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center">
        <button
          type="button"
          onClick={onClick}
          className="inline-flex items-center gap-3 rounded-lg bg-fd-primary px-7 py-4 text-lg font-semibold text-fd-primary-foreground shadow transition hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fd-primary active:scale-[0.98]"
        >
          {state === 'copied' ? <Check className="size-6" /> : <ClipboardCopy className="size-6" />}
          {state === 'copied' ? 'Copied!' : label}
        </button>
        <p className="text-sm text-fd-muted-foreground" aria-live="polite">
          {state === 'copied'
            ? 'Now paste it into Claude Code (Ctrl+V or ⌘V) and press Enter.'
            : state === 'failed'
              ? 'Copying didn’t work in this browser. Open “Show the prompt” below and copy it from there.'
              : hint}
        </p>
      </div>
      <details className="mt-5 group">
        <summary className="cursor-pointer text-sm font-medium text-fd-muted-foreground hover:text-fd-foreground">
          Show the prompt
        </summary>
        <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap rounded-lg border border-fd-border bg-fd-secondary p-4 font-mono text-xs leading-relaxed">
          {prompt}
        </pre>
      </details>
    </div>
  );
}

/** The "Start with Claude" prompt, as used on the Get started page. */
export function StartPrompt() {
  return <CopyPrompt prompt={startPrompt} />;
}
