/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        accent: "#1a73e8",
      },
      fontFamily: {
        sans: ["Google Sans Text", "Roboto", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
}
