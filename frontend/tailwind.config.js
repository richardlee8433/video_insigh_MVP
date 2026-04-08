/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          bg: "#0f1117",
          surface: "#1a1d27",
          border: "#2a2d3a",
          orange: "#f97316",
          "orange-dark": "#ea6c10",
        },
      },
    },
  },
  plugins: [],
};
