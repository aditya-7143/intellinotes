/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#f0f7f3',
          100: '#dceee2',
          200: '#bcddc8',
          300: '#8fc5a4',
          400: '#60a780',
          500: '#3e8960',
          600: '#286b49',
          700: '#21563d',
          800: '#1d4533',
          900: '#19392c',
        },
      },
    },
  },
  plugins: [],
};