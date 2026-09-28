import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import prettier from 'eslint-config-prettier';

/**
 * Layer boundaries are enforced here, not by convention.
 * The dependency direction is documented in architecture/dependency-rules.md.
 */
const boundary = (groups, message) => ({
  'no-restricted-imports': ['error', { patterns: [{ group: groups, message }] }],
});

const INFRASTRUCTURE = [
  'fastify',
  'fastify/*',
  'playwright',
  'playwright-core',
  'drizzle-orm',
  'drizzle-orm/*',
  'better-sqlite3',
  'react',
  'react-dom',
];

export default tseslint.config(
  {
    ignores: [
      '**/dist/**',
      '**/node_modules/**',
      '**/.vite/**',
      'data/**',
      'test-results/**',
      'playwright-report/**',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      eqeqeq: ['error', 'always'],
      'no-console': ['error', { allow: ['warn', 'error'] }],
    },
  },

  // packages/domain: pure. No infrastructure, no outer layer.
  {
    files: ['packages/domain/**/*.ts'],
    rules: boundary(
      [...INFRASTRUCTURE, '@fb/application', '@fb/database', '@fb/automation', '@fb/queue'],
      'domain may only depend on @fb/shared.',
    ),
  },

  // packages/application: domain + shared only. Infrastructure is reached through ports.
  {
    files: ['packages/application/**/*.ts'],
    rules: boundary(
      [...INFRASTRUCTURE, '@fb/database', '@fb/automation', '@fb/queue'],
      'application talks to infrastructure through ports, never to concrete packages.',
    ),
  },

  // apps/web: browser only. Never reach server-side infrastructure.
  {
    files: ['apps/web/**/*.{ts,tsx}'],
    ignores: ['apps/web/vite.config.ts'],
    rules: boundary(
      [
        'playwright',
        'drizzle-orm',
        'better-sqlite3',
        'fastify',
        'node:*',
        '@fb/database',
        '@fb/automation',
        '@fb/queue',
        '@fb/application',
        '@fb/domain',
      ],
      'the web app may only use @fb/shared and the HTTP/WebSocket API.',
    ),
  },

  {
    files: ['**/*.config.{js,ts}', 'scripts/**/*.ts', '**/scripts/**/*.mjs'],
    languageOptions: { globals: { console: 'readonly', process: 'readonly' } },
    rules: { 'no-console': 'off' },
  },
  prettier,
);
