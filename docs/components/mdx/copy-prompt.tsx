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
const messages = {
  copied: 'Now paste it into Claude Code (Ctrl+V or ⌘V) and press Enter.',
  failed: 'Copying didn’t work in this browser. Open the prompt and copy it from there.',
};

export function CopyPrompt({
  prompt,
  label = 'Copy prompt',
  hint = 'Then paste it into Claude Code, in your project folder.',
  variant = 'card',
  promptHref = '/docs/start/install',
}: {
  prompt: string;
  label?: string;
  hint?: string;
  /** "card" inside a docs page; "hero" on the dark landing page header. */
  variant?: 'card' | 'hero';
  /** Hero only: where people can read the prompt. */
  promptHref?: string;
}) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');

  async function onClick() {
    setState((await copyText(prompt)) ? 'copied' : 'failed');
    setTimeout(() => setState('idle'), 4000);
  }

  const icon = state === 'copied' ? <Check className="size-6" /> : <ClipboardCopy className="size-6" />;
  const text = state === 'copied' ? 'Copied!' : label;
  const message = state === 'idle' ? hint : messages[state];

  if (variant === 'hero') {
    return (
      <div className="flex flex-col items-center gap-3" style={{ textShadow: 'none' }}>
        <button
          type="button"
          onClick={onClick}
          className="inline-flex items-center gap-3 rounded-lg bg-[#ffb000] px-8 py-4 text-lg font-semibold text-[#14100b] shadow-[0_0_24px_rgb(255_176_0/0.35)] transition hover:bg-[#ffc233] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#ffb000] active:scale-[0.98]"
        >
          {icon}
          {text}
        </button>
        <p className="text-sm" style={{ color: '#f5e6c8' }} aria-live="polite">
          {message}{' '}
          {state === 'idle' && (
            <a href={promptHref} className="underline underline-offset-4 opacity-80 hover:opacity-100">
              Read the prompt first
            </a>
          )}
        </p>
      </div>
    );
  }

  return (
    <div className="not-prose my-6 rounded-xl border border-fd-border bg-fd-card p-6 shadow-sm">
      <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center">
        <button
          type="button"
          onClick={onClick}
          className="inline-flex items-center gap-3 rounded-lg bg-fd-primary px-7 py-4 text-lg font-semibold text-fd-primary-foreground shadow transition hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fd-primary active:scale-[0.98]"
        >
          {icon}
          {text}
        </button>
        <p className="text-sm text-fd-muted-foreground" aria-live="polite">
          {message}
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

/** The start prompt: installs bimai and sets up the team. On the install page and the landing page. */
export function StartPrompt({ variant = 'card' }: { variant?: 'card' | 'hero' }) {
  return variant === 'hero' ? (
    <CopyPrompt
      prompt={startPrompt}
      variant="hero"
      label="Copy prompt to start"
      hint="Paste it into Claude Code in your project folder, and your BIM team is set up."
    />
  ) : (
    <CopyPrompt prompt={startPrompt} />
  );
}
