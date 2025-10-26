/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        manrope: ['Manrope', 'sans-serif'],
        mulish: ['Mulish', 'sans-serif'],
      },
      colors: {
        background: '#F1FAEE',
        'text-primary': '#1D3557',
        'text-secondary': '#457B9D',
        'brand-primary': '#457B9D',
        'brand-light': '#A8DADC',
        'brand-text': '#F1FAEE',
      },
      keyframes: {
        fadeInDown: {
          from: {
            opacity: '0',
            transform: 'translateY(-20px)',
          },
          to: {
            opacity: '1',
            transform: 'translateY(0)',
          },
        },
      },
      animation: {
        'fade-in-down': 'fadeInDown 0.6s ease-out backwards',
      },
    },
  },
  plugins: [],
}
