/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "SF Pro Text", "Segoe UI", "Helvetica Neue", "Arial", "sans-serif"],
        mono: ["ui-monospace", "SF Mono", "Menlo", "Consolas", "monospace"],
      },
      colors: {
        ink: "#1d1d1f",
        mute: "#6e6e73",
        line: "#e5e5ea",
        paper: "#fbfbfd",
        accent: "#0071e3",
      },
      keyframes: {
        rise: { "0%": { opacity: "0", transform: "translateY(6px)" }, "100%": { opacity: "1", transform: "none" } },
        flash: { "0%": { backgroundColor: "#e8f1fd" }, "100%": { backgroundColor: "transparent" } },
      },
      animation: { rise: "rise .25s ease-out both", flash: "flash 1.4s ease-out" },
    },
  },
  plugins: [],
};
