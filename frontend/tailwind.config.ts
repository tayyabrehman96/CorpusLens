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
        canvas: "#f8fafc",
        surface: {
          DEFAULT: "rgba(255, 255, 255, 0.92)",
          solid: "#ffffff",
          raised: "#f1f5f9",
          hover: "#e2e8f0",
        },
        line: "#e2e8f0",
        lineStrong: "#cbd5e1",
        brand: {
          DEFAULT: "#2563eb",
          dim: "#1d4ed8",
          muted: "#3b82f6",
        },
        ink: { DEFAULT: "#0f172a", muted: "#475569", faint: "#64748b" },
        paper: { DEFAULT: "#f8fafc", card: "#ffffff", border: "#e2e8f0" },
        accent: { DEFAULT: "#2563eb", hover: "#1d4ed8" },
      },
      boxShadow: {
        glow: "0 4px 20px -4px rgba(37, 99, 235, 0.35)",
        lift: "0 4px 24px -4px rgba(15, 23, 42, 0.08), 0 12px 32px -8px rgba(15, 23, 42, 0.06)",
        inset: "inset 0 1px 0 0 rgba(255, 255, 255, 0.8)",
      },
      backgroundImage: {
        "grid-faint":
          "linear-gradient(rgba(15, 23, 42, 0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(15, 23, 42, 0.06) 1px, transparent 1px)",
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
