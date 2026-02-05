import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

/**
 * Aura Hive Documentation Sidebar
 * Structured to guide users from high-level concepts to implementation details
 */
const sidebars: SidebarsConfig = {
  docs: [
    'intro',
    {
      type: 'category',
      label: 'Architecture',
      collapsed: false,
      items: [
        'architecture/overview',
        'architecture/atcg-metabolism',
        'architecture/binary-bloodstream',
        'architecture/protein-mesh',
      ],
    },
    {
      type: 'category',
      label: 'Protocols',
      collapsed: false,
      items: [
        'protocols/atcg-overview',
        'protocols/aggregator',
        'protocols/transformer',
        'protocols/connector',
        'protocols/generator',
        'protocols/membrane',
        'protocols/skill-protocol',
      ],
    },
    {
      type: 'category',
      label: 'Visual Guides',
      link: {type: 'doc', id: 'visual/index'},
      collapsed: false,
      items: [
        'visual/metabolism',
        {
          type: 'category',
          label: 'Hive Architecture',
          items: [
            'visual/hive/atcg-fractal',
            'visual/hive/geography',
          ],
        },
        {
          type: 'category',
          label: 'Components',
          items: [
            'visual/components/membrane-guards',
          ],
        },
        {
          type: 'category',
          label: 'Pipelines',
          items: [
            'visual/pipelines/nats-events',
          ],
        },
      ],
    },
    {
      type: 'category',
      label: 'API Reference',
      collapsed: true,
      items: [
        'api/dna-reference',
        'api/negotiation-reference',
      ],
    },
    {
      type: 'category',
      label: 'Interactive',
      collapsed: true,
      items: [
        'interactive/protocol-explorer',
        'interactive/negotiation-simulator',
        'interactive/protobuf-browser',
      ],
    },
  ],
};

export default sidebars;
