import '@fontsource-variable/inter';
import '@fontsource-variable/jetbrains-mono';
import type { Metadata } from 'next';
import { Provider } from '@/components/provider';
import { appName, siteUrl } from '@/lib/shared';
import './global.css';

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: { default: `${appName} — a BIM team at your command`, template: `%s · ${appName}` },
  description: 'An open-source BIM team that lives in your editor: coordination, requirements, meetings and planning with AI agents that follow your BIM process.',
  icons: { icon: '/logo-mark.svg' },
};

export default function Layout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="flex flex-col min-h-screen">
        <Provider>{children}</Provider>
      </body>
    </html>
  );
}
