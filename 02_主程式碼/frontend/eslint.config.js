import js from '@eslint/js'
import parser from '@typescript-eslint/parser'
import tsPlugin from '@typescript-eslint/eslint-plugin'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'

export default [
  { ignores: ['dist', 'coverage'] },
  js.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      parser,
      parserOptions: { ecmaVersion: 'latest', sourceType: 'module', ecmaFeatures: { jsx: true } },
      globals: {
        window: 'readonly', document: 'readonly', navigator: 'readonly', fetch: 'readonly', console: 'readonly',
        FormData: 'readonly', File: 'readonly', Blob: 'readonly', URL: 'readonly', URLSearchParams: 'readonly',
        Headers: 'readonly', Request: 'readonly', Response: 'readonly', Intl: 'readonly', Node: 'readonly',
        Event: 'readonly', MessageEvent: 'readonly', KeyboardEvent: 'readonly', EventSource: 'readonly',
        AbortController: 'readonly', setTimeout: 'readonly', clearTimeout: 'readonly', setInterval: 'readonly', clearInterval: 'readonly',
        process: 'readonly', JSON: 'readonly', Promise: 'readonly', Map: 'readonly', Set: 'readonly',
      },
    },
    plugins: { '@typescript-eslint': tsPlugin, 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      'no-undef': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
]
