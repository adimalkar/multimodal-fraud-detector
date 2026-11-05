import type { ScreeningResult } from "@/lib/api";
import { actionLabel, percent, titleCase } from "@/lib/format";
import ScoreScale from "./ScoreScale";
import TaskResults from "./TaskResults";

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
	<section className="border-t border-rule pt-4">
		<h2 className="label mb-3">{title}</h2>
		{children}
	</section>
);

const exhibit = (index: number) => String.fromCharCode(65 + (index % 26));

const SHOWN_METADATA: Array<[string, string[]]> = [
	["Format", ["format"]],
	["Dimensions", ["dimensions"]],
	["Camera", ["camera_model", "camera_make"]],
	["Software", ["software", "creator", "producer"]],
	["Created", ["created", "datetime_original", "creation_date"]],
	["GPS", ["has_gps"]],
];

const metadataRows = (metadata: Record<string, unknown>) =>
	SHOWN_METADATA.flatMap(([label, keys]) => {
		const key = keys.find((name) => metadata[name] !== undefined && metadata[name] !== null && metadata[name] !== "");
		if (!key) return [];
		const value = metadata[key];
		return [[label, typeof value === "boolean" ? (value ? "Present" : "Not present") : String(value)]];
	});

const CONTRIBUTIONS = [
	["Visual screening", "visual_contribution"],
	["Text signals", "text_contribution"],
	["Metadata", "metadata_contribution"],
] as const;

/** Findings for one file. Used by the single report and by each batch row. */
const ReportBody = ({ result }: { result: ScreeningResult }) => {
	const risk = result.multimodal_risk;
	const flags = risk?.metadata_flags ?? [];
	const rows = metadataRows(risk?.metadata ?? {});

	return (
		<div className="grid gap-6">
			{risk ? (
				<ScoreScale score={risk.risk_score} tier={risk.severity_tier} />
			) : (
				<p className="text-lg">This path reports evidence only, with no score. Review the checks below.</p>
			)}

			<p className="border-l-4 border-carbon pl-3 leading-snug">
				<span className="font-bold">{actionLabel(result.decision === "manual_review" ? "MANUAL_REVIEW" : risk?.recommended_action)}.</span>{" "}
				This score is an uncalibrated screening aid. Open the original before you decide.
			</p>

			{result.reason && (
				<Section title="Why">
					<p className="max-w-prose leading-relaxed">{result.reason}</p>
				</Section>
			)}

			{result.vision_findings && (
				<Section title="What the vision model noticed">
					<p className="max-w-prose whitespace-pre-line leading-relaxed text-uv">{result.vision_findings}</p>
				</Section>
			)}

			{flags.length > 0 && (
				<Section title="Exhibits to review">
					<ul className="grid gap-2">
						{flags.map((flag, index) => (
							<li key={flag} className="flex items-start gap-2.5">
								<span className="tag shrink-0">{exhibit(index)}</span>
								<span className="leading-snug">{flag}</span>
							</li>
						))}
					</ul>
				</Section>
			)}

			{result.task_results && result.task_results.length > 0 && (
				<Section title="Checks run on this file">
					<TaskResults tasks={result.task_results} />
				</Section>
			)}

			{risk?.breakdown && (
				<Section title="How the score was built">
					<dl className="grid gap-2">
						{CONTRIBUTIONS.map(([label, key]) => {
							const share = risk.breakdown?.[key] ?? 0;
							return (
								<div key={key} className="grid grid-cols-[8.5rem_1fr_2.5rem] items-center gap-3">
									<dt>{label}</dt>
									<dd className="h-2 bg-lightbox">
										<div className="h-2 rounded-r bg-uv" style={{ width: `${Math.min(100, share * 100)}%` }} />
									</dd>
									<dd className="text-right font-data text-sm">{(share * 100).toFixed(0)}</dd>
								</div>
							);
						})}
					</dl>
				</Section>
			)}

			{rows.length > 0 && (
				<Section title="File metadata">
					<dl className="grid gap-x-8 gap-y-1 sm:grid-cols-2">
						{rows.map(([label, value]) => (
							<div key={label} className="flex justify-between gap-4 border-b border-rule py-1">
								<dt className="text-graphite">{label}</dt>
								<dd className="min-w-0 truncate text-right font-data text-sm">{value}</dd>
							</div>
						))}
					</dl>
				</Section>
			)}

			<Section title="Run details">
				<dl className="grid gap-x-8 gap-y-1 font-data text-sm sm:grid-cols-2">
					{result.classification && result.classification !== "Unknown" && (
						<div className="flex justify-between gap-4">
							<dt className="text-graphite">Model label</dt>
							<dd>{titleCase(result.classification)} at {percent(result.confidence)}</dd>
						</div>
					)}
					{result.votes?.map((vote) => (
						<div key={vote.model} className="flex justify-between gap-4">
							<dt className="min-w-0 truncate text-graphite">{vote.model}</dt>
							<dd>{vote.vote}</dd>
						</div>
					))}
					{typeof result.elapsed_seconds === "number" && (
						<div className="flex justify-between gap-4">
							<dt className="text-graphite">Time taken</dt>
							<dd>{result.elapsed_seconds}s</dd>
						</div>
					)}
					{result.pipeline_version && (
						<div className="flex justify-between gap-4">
							<dt className="text-graphite">Pipeline</dt>
							<dd>{result.pipeline_version}</dd>
						</div>
					)}
					{result.model_usage?.calls !== undefined && (
						<div className="flex justify-between gap-4">
							<dt className="text-graphite">Model calls</dt>
							<dd>{result.model_usage.calls}</dd>
						</div>
					)}
				</dl>
			</Section>
		</div>
	);
};

export default ReportBody;
