/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // To sprawia, że Tailwind wszędzie użyje fontu Inter
        sans: ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
}