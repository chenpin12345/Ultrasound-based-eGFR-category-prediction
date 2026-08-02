/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#17333a',
        clinical: {
          50: '#eef9f7',
          100: '#d7f1ec',
          200: '#afe3d9',
          300: '#7ccdbf',
          400: '#48ae9f',
          500: '#2d9184',
          600: '#22746b',
          700: '#1f5d57',
          800: '#1d4b47',
          900: '#193f3c'
        }
      },
      boxShadow: {
        panel: '0 10px 32px rgba(24, 57, 64, 0.07)',
      },
      fontFamily: {
        sans: ['Inter', 'Noto Sans TC', 'Microsoft JhengHei', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
