import type { TaskResult } from "@/lib/api";
import { titleCase } from "@/lib/format";

const TASK_NAMES: Record<string, string> = {
	provenance: "Content Credentials",
	synthetic_image: "Generated image detection",
	document_structure: "PDF structure",
	document_integrity: "Signatures and revisions",
	document_ocr: "Page OCR",
	document_field_consistency: "Field consistency",
	video_structure: "Video structure",
	video_sampling: "Scene sampling",
	synthetic_video: "Generated video detection",
	face_manipulation: "Face manipulation detection",
};

const STATUS: Record<string, { label: string; className: string }> = {
	supported: { label: "Checked", className: "bg-uv text-canvas" },
	completed: { label: "Checked", className: "bg-uv text-canvas" },
	partial: { label: "Partly checked", className: "border border-uv text-uv" },
	inconclusive: { label: "Inconclusive", className: "border border-muted text-muted" },
	not_checked: { label: "Not checked", className: "border border-dashed border-muted text-muted" },
};

const display = (value: unknown): string => {
	if (typeof value === "boolean") return value ? "Yes" : "No";
	if (value === null || value === undefined) return "–";
	return typeof value === "object" ? JSON.stringify(value) : String(value);
};

const TaskResults = ({ tasks }: { tasks: TaskResult[] }) => (
	<ul className="divide-y divide-line border-y border-line">
		{tasks.map((task) => {
			const status = STATUS[task.state === "not_checked" ? "not_checked" : task.status] ?? {
				label: titleCase(task.status),
				className: "border border-muted text-muted",
			};
			const limits = Array.isArray(task.limitations) ? task.limitations.join(" ") : task.limitations;
			const coverage = Object.entries(task.coverage ?? {});
			const hasEvidence = Array.isArray(task.evidence) ? task.evidence.length > 0 : Boolean(task.evidence);
			return (
				<li key={task.task} className="py-3">
					<div className="flex flex-wrap items-center justify-between gap-2">
						<h3 className="font-bold">{TASK_NAMES[task.task] ?? titleCase(task.task)}</h3>
						<span className={`px-2 py-0.5 font-data text-xs ${status.className}`}>{status.label}</span>
					</div>
					{limits && <p className="mt-1 leading-snug text-muted">{limits}</p>}
					{coverage.length > 0 && (
						<dl className="mt-2 grid gap-x-6 gap-y-0.5 font-data text-xs sm:grid-cols-2">
							{coverage.map(([key, value]) => (
								<div key={key} className="flex justify-between gap-3">
									<dt className="text-muted">{titleCase(key)}</dt>
									<dd className="min-w-0 truncate text-right">{display(value)}</dd>
								</div>
							))}
						</dl>
					)}
					{hasEvidence && (
						<details className="mt-2">
							<summary className="cursor-pointer text-sm underline hover:text-uv">Show raw evidence</summary>
							<pre className="mt-2 max-h-64 overflow-auto bg-canvas p-3 font-data text-xs">
								{JSON.stringify(task.evidence, null, 2)}
							</pre>
						</details>
					)}
				</li>
			);
		})}
	</ul>
);

export default TaskResults;
