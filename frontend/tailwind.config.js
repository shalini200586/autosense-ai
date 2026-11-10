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
        ink: "#14202e",
        mute: "#6b7280",
        line: "#e6e0d4",
        paper: "#f6f3ed",
        navy: { DEFAULT: "#0e1a2b", soft: "#1a2b44" },
        gold: { DEFAULT: "#b8935a", soft: "#f3ead9", deep: "#8a6a3a" },
        accent: "#b8935a",
        emerald: { deep: "#1f7a5c", soft: "#e4f2ec" },
        wine: { deep: "#8c2f39", soft: "#f6e6e8" },
      },
      keyframes: {
        rise: { "0%": { opacity: "0", transform: "translateY(6px)" }, "100%": { opacity: "1", transform: "none" } },
        flash: { "0%": { backgroundColor: "#f3ead9" }, "100%": { backgroundColor: "transparent" } },
      },
      animation: { rise: "rise .25s ease-out both", flash: "flash 1.4s ease-out" },
    },
  },
  plugins: [],
};
