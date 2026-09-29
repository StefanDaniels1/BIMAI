import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { appName, gitConfig } from './shared';

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: (
        <span className="inline-flex items-center gap-2 font-mono font-semibold tracking-tight">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo-mark.svg" alt="" width={24} height={24} />
          {appName}
        </span>
      ),
    },
    links: [
      { text: 'Get started', url: '/docs/start/install', active: 'nested-url' },
      { text: 'Why bimai', url: '/docs/why', active: 'nested-url' },
      { text: 'Example project', url: '/docs/example-project', active: 'nested-url' },
    ],
    githubUrl: `https://github.com/${gitConfig.user}/${gitConfig.repo}`,
  };
}
