/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        minecraft: {
          dark: '#0a0d14',
          stone: '#1a252c',
          warden: '#00ffff',
          redstone: '#ff0044',
          vault: '#2ecc71',
          gold: '#ffaa00',
        },
      },
      fontFamily: {
        mono: ['"Courier New"', 'Courier', 'monospace'],
      },
    },
  },
  plugins: [],
};
