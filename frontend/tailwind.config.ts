import type { Config } from "tailwindcss";
import plugin from "tailwindcss/plugin";

/*
 * The one source of truth for colour. Each value is also published as a CSS
 * variable of the same name.
 *
 * Colour carries meaning here:
 *   carbon  = people and their decisions
 *   uv      = anything the machine observed
 *   marker  = exhibit tags that cross-reference a finding
 * Score tiers are ordered, so they share one hue from light to dark.
 * Status colours describe the system, never a claim.
 */
const palette = {
	lightbox: "#e8eef1",
	paper: "#fbfcfb",
	carbon: "#121c2b",
	graphite: "#4a5866",
	rule: "#c3ced5",
	uv: "#4530d6",
	"uv-tint": "#ecebfd",
	"uv-field": "#17124f",
	fluoro: "#a8ffe6",
	marker: "#ffcb1f",
	"tier-low": "#cfcafa",
	"tier-elevated": "#9a8ff0",
	"tier-high": "#5a45dc",
	"tier-critical": "#231a8a",
	"status-good": "#0d6e66",
	"status-warn": "#ad430d",
	"status-bad": "#ab1138",
};

const config: Config = {
	content: ["./components/**/*.{ts,tsx}", "./app/**/*.{ts,tsx}"],
	theme: {
		extend: {
			colors: palette,
			fontFamily: {
				display: ["var(--font-display)", "system-ui", "sans-serif"],
				body: ["var(--font-body)", "system-ui", "sans-serif"],
				data: ["var(--font-data)", "ui-monospace", "monospace"],
			},
		},
	},
	plugins: [
		plugin(({ addBase }) => {
			addBase({
				":root": {
					colorScheme: "light",
					...Object.fromEntries(Object.entries(palette).map(([name, value]) => [`--${name}`, value])),
				},
			});
		}),
	],
};
export default config;
