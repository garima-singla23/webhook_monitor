/**
 * tailwind.config.js


/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./*.html", "./pages/*.html", "./js/**/*.js"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#0A0A0B",   // page background
          raised: "#111113",    // cards, sidebar
          overlay: "#18181B",   // modals, dropdowns
          hover: "#1F1F23",     // hover state on raised surfaces
        },
        border: {
          DEFAULT: "#27272A",
          subtle: "#1C1C1F",
        },
        ink: {
          DEFAULT: "#FAFAFA",   // primary text
          muted: "#A1A1AA",     // secondary text
          faint: "#71717A",     // labels, captions, placeholders
        },
        accent: {
          DEFAULT: "#3B82F6",
          hover: "#60A5FA",
          dim: "#1D4ED8",
          subtle: "rgba(59, 130, 246, 0.1)",
        },
        status: {
          up: "#22C55E",
          "up-dim": "rgba(34, 197, 94, 0.12)",
          down: "#EF4444",
          "down-dim": "rgba(239, 68, 68, 0.12)",
          degraded: "#F59E0B",
          "degraded-dim": "rgba(245, 158, 11, 0.12)",
          unknown: "#71717A",
          "unknown-dim": "rgba(113, 113, 122, 0.12)",
        },
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        xs: ["0.75rem", { lineHeight: "1.1rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.875rem", { lineHeight: "1.5rem" }],
        lg: ["1rem", { lineHeight: "1.5rem" }],
        xl: ["1.25rem", { lineHeight: "1.75rem" }],
        "2xl": ["1.75rem", { lineHeight: "2.125rem" }],
      },
      borderRadius: {
        sm: "6px",
        DEFAULT: "8px",
        lg: "10px",
      },
      boxShadow: {
        sm: "0 1px 2px rgba(0, 0, 0, 0.3)",
        DEFAULT: "0 4px 12px rgba(0, 0, 0, 0.4)",
        lg: "0 12px 32px rgba(0, 0, 0, 0.5)",
        focus: "0 0 0 3px rgba(59, 130, 246, 0.35)",
      },
      animation: {
        "pulse-slow": "pulse-slow 2.4s ease-in-out infinite",
        "fade-in": "fade-in 0.15s ease-out",
        "slide-up": "slide-up 0.2s ease-out",
      },
      keyframes: {
        "pulse-slow": {
          "0%, 100%": { opacity: "1", boxShadow: "0 0 0 0 rgba(34, 197, 94, 0.5)" },
          "50%": { opacity: "0.7", boxShadow: "0 0 0 4px rgba(34, 197, 94, 0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "slide-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};