/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        profit: {
          high: '#16a34a',
          mid: '#ca8a04',
          low: '#dc2626',
        }
      }
    },
  },
  plugins: [],
}
