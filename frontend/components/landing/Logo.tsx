/** Stacked sheets seen edge-on: the file coming apart into layers. */
export const LogoMark = ({ className = "h-6 w-6" }: { className?: string }) => (
	<svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
		<path d="M12 2.5 22 8l-10 5.5L2 8z" fill="currentColor" />
		<path d="m4 12.2 8 4.4 8-4.4" stroke="var(--uv)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
		<path d="m4 16.2 8 4.4 8-4.4" stroke="var(--fluoro)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
	</svg>
);

export const Wordmark = () => (
	<span className="flex items-center gap-2 text-ink">
		<LogoMark />
		<span className="text-[1.0625rem] font-semibold tracking-tight">FraudSight</span>
	</span>
);
