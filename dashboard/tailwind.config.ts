/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        navy: '#0A1628',
        indigo: '#4354D4',
        purple: '#8F35F5',
        slate: '#64748B',
        mist: '#EEF0FF',
        orchid: '#F0EDFF',
        hairline: '#E6E8F2',
        success: '#16A34A',
        danger: '#DC2626',
      },
    },
  },
  plugins: [],
};
