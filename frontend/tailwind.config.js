/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        f1: {
          red: "#E10600",
          dark: "#0a0a0f",
          card: "rgba(255,255,255,0.04)",
          border: "rgba(255,255,255,0.08)",
          surface: "#111118",
          muted: "#888899",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      backdropBlur: {
        glass: "20px",
      },
    },
  },
  plugins: [],
};
