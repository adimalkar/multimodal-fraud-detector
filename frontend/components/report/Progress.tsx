const STEPS = ["Received", "Screening", "Report ready"];

/** Only three steps are shown because those are the states the engine actually reports. */
const Progress = ({ value, label, elapsed, finished = false }: { value: number; label: string; elapsed?: number; finished?: boolean }) => (
	<div className="sheet p-6">
		<div className="flex items-baseline justify-between gap-4">
			<p className="text-lg font-medium" role="status">{label}</p>
			{typeof elapsed === "number" && <p className="shrink-0 font-data text-sm text-muted">{Math.round(elapsed)}s</p>}
		</div>
		<div
			role="progressbar"
			aria-label="Screening progress"
			aria-valuenow={value}
			aria-valuemin={0}
			aria-valuemax={100}
			className="mt-4 h-1 overflow-hidden rounded-full bg-raised"
		>
			<div className="h-1 rounded-full bg-gradient-to-r from-uv to-fluoro transition-[width] duration-500" style={{ width: `${value}%` }} />
		</div>
		<ol className="mt-6 grid gap-3">
			{STEPS.map((step, index) => {
				const done = finished || index === 0;
				const current = !finished && index === 1;
				return (
					<li key={step} className={`flex items-center gap-3 ${done || current ? "text-ink" : "text-muted"}`}>
						<span
							aria-hidden="true"
							className={`h-2 w-2 rounded-full ${done ? "bg-fluoro" : current ? "animate-pulse bg-uv" : "bg-line"}`}
						/>
						{step}
					</li>
				);
			})}
		</ol>
	</div>
);

export default Progress;
