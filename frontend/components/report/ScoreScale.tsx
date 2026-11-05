import { tierOf } from "@/lib/format";

const BANDS = [
	{ from: 0, to: 35, tier: "LOW_RISK", className: "bg-tier-low" },
	{ from: 35, to: 60, tier: "SUSPICIOUS", className: "bg-tier-elevated" },
	{ from: 60, to: 80, tier: "HIGH_RISK", className: "bg-tier-high" },
	{ from: 80, to: 100, tier: "CRITICAL_FRAUD", className: "bg-tier-critical" },
];

/** A single score read against the engine's real tier cut-offs (35, 60 and 80). */
const ScoreScale = ({ score, tier }: { score: number; tier: string }) => {
	const value = Math.round(score * 100);
	return (
		<div>
			<div className="flex items-baseline gap-3">
				<span className="display text-6xl md:text-7xl">{value}</span>
				<span className="font-bold">{tierOf(tier).label}</span>
			</div>
			<div
				role="img"
				aria-label={`Screening score ${value} out of 100, ${tierOf(tier).label}. Bands start at 35, 60 and 80.`}
				className="relative mt-5"
			>
				<div
					className="absolute -top-2 bottom-5 z-10 w-[3px] -translate-x-1/2 bg-ink shadow-[0_0_0_2px_var(--surface)]"
					style={{ left: `${Math.min(99.5, Math.max(0.5, value))}%` }}
				/>
				<div className="flex gap-0.5 overflow-hidden rounded-full">
					{BANDS.map((band) => (
						<div key={band.tier} className={`h-3 ${band.className}`} style={{ width: `${band.to - band.from}%` }} />
					))}
				</div>
				<div className="relative mt-1 h-5 font-data text-xs text-muted">
					{[0, 35, 60, 80].map((tick) => (
						<span key={tick} className="absolute" style={{ left: `${tick}%` }}>{tick}</span>
					))}
					<span className="absolute right-0">100</span>
				</div>
			</div>
		</div>
	);
};

export default ScoreScale;
