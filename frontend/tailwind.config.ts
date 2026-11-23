import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17231f",
        forest: { 50: "#f0f7f3", 100: "#dcece2", 500: "#287453", 600: "#1f6045", 700: "#194d39", 900: "#123429" },
        ember: { 100: "#ffe7d2", 500: "#ed6b35", 600: "#d45224" },
        sand: "#f5f2ea"
      },
      boxShadow: {
        panel: "0 1px 2px rgba(18,52,41,.04), 0 12px 32px rgba(18,52,41,.06)"
      }
    },
  },
  plugins: [],
};

export default config;
