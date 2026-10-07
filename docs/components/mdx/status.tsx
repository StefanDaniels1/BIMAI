import { Callout } from 'fumadocs-ui/components/callout';

/**
 * Honest build status for a page. bimai is pre-alpha: pages describe the
 * target experience unless marked "available".
 */
export function Status({ state = 'planned', children }: { state?: 'available' | 'beta' | 'planned' | 'design'; children?: React.ReactNode }) {
  const text = {
    available: 'Available now.',
    beta: 'Built and installable, but not yet verified inside the real program.',
    planned: 'Planned for v0.1. This page describes the target experience; commands may not exist yet.',
    design: 'Design stage. This describes how the feature is intended to work and may still change.',
  }[state];
  return (
    <Callout type={state === 'available' ? 'success' : 'warn'} title={state === 'available' ? 'Available' : state === 'beta' ? 'Beta' : 'Not built yet'}>
      {text} {children}
    </Callout>
  );
}
