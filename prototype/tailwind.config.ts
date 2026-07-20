/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        mono: ['"Berkeley Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
        sans: ['"Neue Haas Grotesk Display"', 'ui-sans-serif', 'system-ui'],
        serif: ['"GT Sectra"', 'ui-serif', 'Georgia', 'serif'],
      },
    },
  },
  plugins: [],
};
