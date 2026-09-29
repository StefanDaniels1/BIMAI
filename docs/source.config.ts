import { defineConfig } from 'fumadocs-mdx/config';
import { remarkMdxMermaid } from 'fumadocs-core/mdx-plugins';

// Global MDX options: ```mermaid code blocks render as diagrams.
export default defineConfig({
  mdxOptions: {
    remarkPlugins: (v) => [...v, remarkMdxMermaid],
  },
});
