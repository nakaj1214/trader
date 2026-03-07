import type { Config } from 'tailwindcss';

export default {
	content: ['./src/**/*.{html,js,svelte,ts}'],
	theme: {
		extend: {
			colors: {
				bg: '#0B0F19',
				surface: '#141B2D',
				'surface-alt': '#1A2238',
				primary: '#00D4AA',
				'primary-dim': 'rgba(0, 212, 170, 0.12)',
				'primary-strong': '#00FFCC',
				success: '#34D399',
				danger: '#FB7185',
				warning: '#FBBF24',
				text: '#E2E8F0',
				'text-muted': '#64748B',
				border: '#1E293B',
				'border-highlight': 'rgba(0, 212, 170, 0.25)'
			},
			fontFamily: {
				display: ['Sora', 'sans-serif'],
				body: ['DM Sans', 'sans-serif'],
				mono: ['JetBrains Mono', 'monospace']
			},
			borderRadius: {
				DEFAULT: '12px',
				sm: '8px'
			},
			boxShadow: {
				DEFAULT: '0 2px 8px rgba(0, 0, 0, 0.4)',
				lg: '0 8px 32px rgba(0, 0, 0, 0.5)',
				glow: '0 0 20px rgba(0, 212, 170, 0.12)'
			}
		}
	},
	plugins: []
} satisfies Config;
