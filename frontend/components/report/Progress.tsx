const Progress = ({ value, label, elapsed }: { value: number; label: string; elapsed?: number }) => (
	<div className="sheet p-5">
		<div className="flex items-baseline justify-between gap-4">
			<p className="font-bold" role="status">{label}</p>
			{typeof elapsed === "number" && <p className="shrink-0 font-data text-sm text-graphite">{Math.round(elapsed)}s</p>}
		</div>
		<div
			role="progressbar"
			aria-label="Screening progress"
			aria-valuenow={value}
			aria-valuemin={0}
			aria-valuemax={100}
			className="mt-3 h-2 bg-lightbox"
		>
			<div className="h-2 rounded-r bg-uv transition-[width] duration-500" style={{ width: `${value}%` }} />
		</div>
	</div>
);

export default Progress;
