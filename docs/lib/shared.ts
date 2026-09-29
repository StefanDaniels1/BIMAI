import { createGetUrl } from 'fumadocs-core/source';

export const appName = 'bimai';
export const docsRoute = '/docs';
export const docsImageRoute = '/og/docs';
export const docsContentRoute = '/llms.mdx/docs';

/** Where the docs are published. Override per deployment, e.g. a project site. */
export const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://docs.bimai.nl';

/** The public bimai repository. Set BIMAI_GITHUB_REPO=org/repo when publishing. */
const [user, repo] = (process.env.BIMAI_GITHUB_REPO ?? 'bimai-nl/bimai').split('/');
export const gitConfig = {
  user,
  repo,
  branch: process.env.BIMAI_GITHUB_BRANCH ?? 'main',
  /** Path of the docs content inside the repository, for "edit this page" links. */
  contentPath: 'docs/content/docs',
};

const getContentUrl = createGetUrl(docsContentRoute);

export function getPageMarkdownUrl(page: { slugs: string[]; locale?: string }) {
  const segments = [...page.slugs, 'content.md'];

  return { segments, url: getContentUrl(segments, page.locale) };
}

const getImageUrl = createGetUrl(docsImageRoute);

export function getPageImageUrl(page: { slugs: string[]; locale?: string }) {
  const segments = [...page.slugs, 'image.png'];

  return { segments, url: getImageUrl(segments, page.locale) };
}
