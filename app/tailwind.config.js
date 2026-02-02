/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // YouWare Brand Colors
        'brand': '#55644A',
        green1: '#2e4226',
        green2: '#55644a',
        green3: '#e0e7d0',
        orange1: '#a55500',
        orange2: '#ffd15d',
        orange3: '#f8dfaa',

        // Semantic Colors
        success: '#50a14f',
        link: '#0077ff',
        error: '#d42727',
        warn: '#b68c37',
        tooltip: '#2c2c2c',

        // Surfaces
        'fill-secondary': '#f6f4f1',
        'sidebar-bg': '#F1EFEC',

        // Text hierarchy (for explicit use)
        primary: 'rgba(0, 0, 0, 0.95)',
        secondary: 'rgba(0, 0, 0, 0.60)',
        tertiary: 'rgba(0, 0, 0, 0.40)',
        disabled: 'rgba(0, 0, 0, 0.20)',

        // Editor-specific dark theme (keep dark for code readability)
        editor: {
          bg: '#1e1e2e',
          surface: '#282838',
          border: '#3d3d5c',
          text: '#cdd6f4',
          muted: '#6c7086',
          accent: '#89b4fa',
          success: '#a6e3a1',
          warning: '#f9e2af',
          error: '#f38ba8',
        },
      },
      fontFamily: {
        'youware-sans': ['Inter', 'system-ui', 'sans-serif'],
        'roboto-flex': ['Inter', 'system-ui', 'sans-serif'],
        'roboto-mono': ['JetBrains Mono', 'Fira Code', 'monospace'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      borderRadius: {
        'yw-sm': '4px',
        'yw-md': '6px',
        'yw-lg': '10px',
        'yw-xl': '16px',
        'yw-2xl': '24px',
      },
      boxShadow: {
        'modal': '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
        'card': '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
        'card-hover': '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
      },
      animation: {
        'fade-in-up': 'fadeInUp 0.2s ease-out',
        'fade-in-down': 'fadeInDown 0.2s ease-out',
        'spin-once': 'spin 0.5s ease-in-out',
      },
      keyframes: {
        fadeInUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeInDown: {
          '0%': { opacity: '0', transform: 'translateY(-10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
};
