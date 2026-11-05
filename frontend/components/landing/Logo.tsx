/** An examiner's corner scale with a lens resting on it. */
export const LogoMark = ({ className = "h-7 w-7" }: { className?: string }) => (
	<svg viewBox="0 0 32 32" className={className} aria-hidden="true">
		<path d="M3 3h5v21h21v5H3z" fill="currentColor" />
		<path d="M3 8h2.5M3 13h2.5M3 18h2.5M13 29v-2.5M18 29v-2.5M23 29v-2.5" stroke="var(--paper)" strokeWidth="1.4" />
		<circle cx="20" cy="12" r="7" fill="var(--uv)" />
		<circle cx="20" cy="12" r="3" fill="var(--fluoro)" />
	</svg>
);

export const Wordmark = () => (
	<span className="flex items-center gap-2.5 text-carbon">
		<LogoMark />
		<span className="display text-2xl leading-none">FraudSight</span>
	</span>
);
