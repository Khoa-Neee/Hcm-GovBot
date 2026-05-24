import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        civic: {
          ink: "#182230",
          muted: "#667085",
          line: "#D0D5DD",
          red: "#B42318",
          teal: "#0E9384",
          gold: "#B54708",
          paper: "#F8FAFC",
        },
      },
      boxShadow: {
        soft: "0 12px 30px rgba(16, 24, 40, 0.08)",
      },
    },
  },
  plugins: [],
} satisfies Config;
