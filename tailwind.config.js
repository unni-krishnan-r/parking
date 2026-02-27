/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/**/*.js"
  ],
  theme: {
    extend: {
      colors: {
        surface: '#1A1D21',
        border: '#2D3139',
        accent: '#F59E0B',
        primary: '#8B5CF6'
      }
    }
  },
  plugins: [],
}