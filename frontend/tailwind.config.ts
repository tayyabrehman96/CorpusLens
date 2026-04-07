import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      colors: {
        canvas: "#070709",
        surface: {
          DEFAULT: "rgba(16, 16, 20, 0.72)",
          solid: "#101014",
          raised: "#18181f",
          hover: "#1f1f28",
        },
        line: "rgba(255, 255, 255, 0.07)",
        lineStrong: "rgba(255, 255, 255, 0.12)",
        brand: {
          DEFAULT: "#2dd4bf",
          dim: "#14b8a6",
          muted: "#5eead4",
        },
        ink: { DEFAULT: "#fafafa", muted: "#a1a1aa", faint: "#71717a" },
        paper: { DEFAULT: "#18181f", card: "rgba(24, 24, 31, 0.85)", border: "rgba(255,255,255,0.08)" },
        accent: { DEFAULT: "#2dd4bf", hover: "#5eead4" },
      },
      boxShadow: {
        glow: "0 0 48px -12px rgba(45, 212, 191, 0.22)",
        lift: "0 24px 48px -16px rgba(0, 0, 0, 0.55)",
        inset: "inset 0 1px 0 0 rgba(255,255,255,0.06)",
      },
      backgroundImage: {
        "grid-faint":
          "linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)",
      },
      backgroundSize: {
        grid: "48px 48px",
      },
      animation: {
        pulseSoft: "pulseSoft 2s ease-in-out infinite",
      },
      keyframes: {
        pulseSoft: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.55" },
        },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
