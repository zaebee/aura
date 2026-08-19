import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

const config: Config = {
  title: 'Aura Hive Documentation',
  tagline: 'Punk-Sovereign AI Infrastructure',
  favicon: 'img/favicon.ico',

  // Future flags, see https://docusaurus.io/docs/api/docusaurus-config#future
  future: {
    v4: true, // Improve compatibility with the upcoming Docusaurus v4
  },

  // Set the production url of your site here
  url: 'https://zaebee.github.io',
  // Set the /<baseUrl>/ pathname under which your site is served
  // For GitHub pages deployment, it is often '/<projectName>/'
  baseUrl: '/aura/',

  // GitHub pages deployment config.
  // If you aren't using GitHub pages, you don't need these.
  organizationName: 'zaebee',
  projectName: 'aura',
  deploymentBranch: 'gh-pages',
  trailingSlash: false,

  onBrokenLinks: 'throw',

  // Even if you don't use internationalization, you can use this field to set
  // useful metadata like html lang. For example, if your site is Chinese, you
  // may want to replace "en" with "zh-Hans".
  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  markdown: {
    mermaid: true,
  },

  themes: ['@docusaurus/theme-mermaid'],

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/zaebee/aura/tree/main/docs-site/',
        },
        blog: false, // Disable blog for now
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  plugins: [
    // TypeDoc disabled for now - causes issues with Vite types
    // Will enable once we have dedicated type definition files
    // [
    //   'docusaurus-plugin-typedoc',
    //   {
    //     entryPoints: ['../frontend/src/hive/dna.ts'],
    //     tsconfig: '../frontend/tsconfig.json',
    //     out: 'api/typescript-types',
    //   },
    // ],
  ],

  themeConfig: {
    image: 'img/aura-social-card.jpg',
    colorMode: {
      defaultMode: 'dark',
      disableSwitch: false,
      respectPrefersColorScheme: false,
    },
    navbar: {
      title: 'Aura Hive',
      logo: {
        alt: 'Aura Hive Logo',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docs',
          position: 'left',
          label: 'Docs',
        },
        {
          to: '/docs/visual',
          label: 'Visual',
          position: 'left',
        },
        {
          to: '/docs/api/dna-reference',
          label: 'API',
          position: 'left',
        },
        {
          href: 'https://github.com/zaebee/aura',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            {
              label: 'Getting Started',
              to: '/docs',
            },
            {
              label: 'Architecture',
              to: '/docs/architecture/overview',
            },
            {
              label: 'Visual Guides',
              to: '/docs/visual',
            },
          ],
        },
        {
          title: 'Protocols',
          items: [
            {
              label: 'ATCG-M Pattern',
              to: '/docs/protocols/atcg-overview',
            },
            {
              label: 'Aggregator',
              to: '/docs/protocols/aggregator',
            },
            {
              label: 'Transformer',
              to: '/docs/protocols/transformer',
            },
          ],
        },
        {
          title: 'More',
          items: [
            {
              label: 'API Reference',
              to: '/docs/api/dna-reference',
            },
            {
              label: 'GitHub',
              href: 'https://github.com/zaebee/aura',
            },
          ],
        },
      ],
      copyright: `Built with Docusaurus. For the glory of the Hive. 🐝`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.vsDark,
      additionalLanguages: ['protobuf', 'rust', 'python', 'typescript', 'bash'],
    },
    mermaid: {
      theme: {light: 'neutral', dark: 'dark'},
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
