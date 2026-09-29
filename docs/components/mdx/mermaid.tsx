'use client';

import { use, useId, useSyncExternalStore } from 'react';
import { useTheme } from 'next-themes';

export function Mermaid({ chart }: { chart: string }) {
  const isClient = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

  if (!isClient) return;
  return <MermaidContent chart={chart} />;
}

const cache = new Map<string, Promise<unknown>>();

function cachePromise<T>(key: string, setPromise: () => Promise<T>): Promise<T> {
  const cached = cache.get(key);
  if (cached) return cached as Promise<T>;

  const promise = setPromise();
  cache.set(key, promise);
  return promise;
}

function MermaidContent({ chart }: { chart: string }) {
  const id = useId();
  const { resolvedTheme } = useTheme();
  const { default: mermaid } = use(cachePromise('mermaid', () => import('mermaid')));

  const dark = resolvedTheme === 'dark';
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    fontFamily: 'inherit',
    themeCSS: 'margin: 1.5rem auto 0;',
    // bimai brand: amber on warm neutrals, readable in both themes
    theme: 'base',
    themeVariables: dark
      ? {
          darkMode: true,
          background: '#14100b',
          primaryColor: '#241c12',
          primaryTextColor: '#f5e6c8',
          primaryBorderColor: '#ffb000',
          secondaryColor: '#1d1710',
          tertiaryColor: '#1d1710',
          lineColor: '#ffb000',
          textColor: '#f5e6c8',
          clusterBkg: '#1d1710',
          clusterBorder: '#7a5400',
          edgeLabelBackground: '#241c12',
        }
      : {
          background: '#ffffff',
          primaryColor: '#fff4d6',
          primaryTextColor: '#2b2115',
          primaryBorderColor: '#b36b00',
          secondaryColor: '#fffaf0',
          tertiaryColor: '#fffaf0',
          lineColor: '#7a5400',
          textColor: '#2b2115',
          clusterBkg: '#fffaf0',
          clusterBorder: '#e0c080',
          edgeLabelBackground: '#fff4d6',
        },
  });

  const { svg, bindFunctions } = use(
    cachePromise(`${chart}-${resolvedTheme}`, () => {
      return mermaid.render(id, chart.replaceAll('\\n', '\n'));
    }),
  );

  return (
    <div
      className="not-prose overflow-x-auto"
      ref={(container) => {
        if (container) bindFunctions?.(container);
      }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
