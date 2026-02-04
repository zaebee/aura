import type { Config } from 'tailwindcss'
import forms from '@tailwindcss/forms'

const config: Config = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'cyberpunk-blue': '#00f2ff',
        'cyberpunk-purple': '#bc13fe',
        'card-bg': '#1a1a1a',
        'error': '#ff003c',
      },
      backgroundImage: {
        'cyberpunk-gradient': 'linear-gradient(90deg, #00f2ff 0%, #bc13fe 100%)',
      },
      boxShadow: {
        'card': '0 4px 20px rgba(0, 0, 0, 0.5)',
      }
    },
  },
  plugins: [
    forms,
  ],
}
export default config
