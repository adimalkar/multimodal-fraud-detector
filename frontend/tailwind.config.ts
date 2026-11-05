import type { Config } from "tailwindcss";
import plugin from "tailwindcss/plugin";

/*
 * The one source of truth for colour. Each value is also published as a CSS
 * variable of the same name.
 *
 * Colour carries meaning here:
 *   ink     = people and their decisions
 *   uv      = anything the machine observed
 *   fluoro  = the scanning light
 *   marker  = exhibit tags that cross-reference a finding
 * Score tiers are ordered, so they share one hue, brighter as the score rises.
 * Status colours describe the system, never a claim.
 */
const palette = {
	canvas: "#07080b",
	surface: "#0f1115",
	raised: "#171a20",
	ink: "#f1f3f6",
	muted: "#9aa3b0",
	line: "#262a33",
	uv: "#9a8cff",
	"uv-tint": "#17143a",
	"uv-field": "#0c0a24",
	fluoro: "#7df5d8",
	marker: "#ffcb1f",
	"tier-low": "#3b3670",
	"tier-elevated": "#6358c4",
	"tier-high": "#9a8cff",
	"tier-critical": "#e2deff",
	"status-good": "#4adeb0",
	"status-warn": "#f5a35c",
	"status-bad": "#ff6b85",
};

const config: Config = {
	content: ["./components/**/*.{ts,tsx}", "./app/**/*.{ts,tsx}"],
	theme: {
		extend: {
			colors: palette,
			fontFamily: {
				sans: ["var(--font-sans)", "system-ui", "sans-serif"],
				data: ["var(--font-data)", "ui-monospace", "monospace"],
			},
			keyframes: {
				scan: {
					"0%": { transform: "translateY(-100%)" },
					"100%": { transform: "translateY(100vh)" },
				},
			},
		},
	},
	plugins: [
		plugin(({ addBase }) => {
			addBase({
				":root": {
					colorScheme: "dark",
					...Object.fromEntries(Object.entries(palette).map(([name, value]) => [`--${name}`, value])),
				},
			});
		}),
	],
};
export default config;
