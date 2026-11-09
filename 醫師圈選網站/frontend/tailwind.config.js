/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: '#1B2A38', soft: '#4A5A68', faint: '#7A8894' },
        paper: { DEFAULT: '#EEF2F1', deep: '#E2E8E7' },
        line: '#D3DCDB',
        steel: { DEFAULT: '#2E6A84', dark: '#1F4D61', wash: '#E3EEF2' },
        amber: { DEFAULT: '#A8661A', wash: '#FBF0DE' },
        ok: { DEFAULT: '#2F7A55', wash: '#E2F1E8' },
        alert: { DEFAULT: '#B03A2E', wash: '#F8E4E1' },
        viewer: { DEFAULT: '#12181C', panel: '#1A2228', line: '#2D3840', text: '#DCE4E8', soft: '#94A3AD' },
      },
      fontFamily: {
        sans: ['"Microsoft JhengHei UI"', '"Microsoft JhengHei"', '"Noto Sans TC"', '"PingFang TC"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
