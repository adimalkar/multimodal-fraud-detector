"use client";

import Link from "next/link";
import { useState } from "react";
import Notice from "@/components/desk/Notice";
import Page from "@/components/desk/Page";
import PageTitle from "@/components/desk/PageTitle";
import { type BatchItem, type BatchState, saveBlob } from "@/lib/api";
import { actionLabel, score100, TIER_BG, tierOf } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";
import Progress from "./Progress";
import ReportBody from "./ReportBody";

const STATUS_LABEL: Record<string, string> = {
	queued: "Waiting",
	pending: "Waiting",
	processing: "Screening",
	completed: "Done",
	failed: "Failed",
};

/* Highest scores first, so the queue starts where a reviewer's time matters most. */
const ranked = (items: BatchItem[]) =>
	[...items].sort((a, b) => (b.result?.multimodal_risk?.risk_score ?? -1) - (a.result?.multimodal_risk?.risk_score ?? -1));

const csvCell = (value: string) => {
	const safe = /^[=+\-@\t\r]/.test(value) ? `'${value}` : value;
	return `"${safe.replace(/"/g, '""')}"`;
};

const exportCsv = (items: BatchItem[], id: string) => {
	const header = ["File", "Type", "Status", "Score", "Band", "Suggested next step", "Reason"];
	const rows = items.map((item) => {
		const risk = item.result?.multimodal_risk;
		return [
			item.filename,
			item.media_type,
			STATUS_LABEL[item.status] ?? item.status,
			risk ? score100(risk.risk_score) : "",
			risk ? tierOf(risk.severity_tier).label : "",
			item.result ? actionLabel(risk?.recommended_action) : "",
			item.result?.reason ?? item.error ?? "",
		].map(csvCell);
	});
	const csv = [header.map(csvCell), ...rows].map((row) => row.join(",")).join("\n");
	saveBlob(new Blob([csv], { type: "text/csv;charset=utf-8" }), `fraudsight-batch-${id.slice(0, 8)}.csv`);
};

const Row = ({ item }: { item: BatchItem }) => {
	const [open, setOpen] = useState(false);
	const risk = item.result?.multimodal_risk;
	const tier = tierOf(risk?.severity_tier);
	const panelId = `item-${item.item_id}`;

	return (
		<li>
			<button
				type="button"
				disabled={!item.result && !item.error}
				aria-expanded={open}
				aria-controls={panelId}
				onClick={() => setOpen(!open)}
				className="grid w-full grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 px-4 py-3 text-left hover:bg-canvas/50 disabled:hover:bg-transparent md:grid-cols-[1fr_6rem_10rem_4rem]"
			>
				<span className="min-w-0 truncate font-data text-sm">{item.filename}</span>
				<span className="text-sm text-muted md:order-none">{STATUS_LABEL[item.status] ?? item.status}</span>
				<span className="flex items-center gap-2 text-sm">
					{risk && <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-sm ${TIER_BG[tier.key]}`} />}
					{risk ? tier.label : "–"}
				</span>
				<span className="text-right font-data text-lg font-bold">{risk ? score100(risk.risk_score) : ""}</span>
			</button>
			{open && (
				<div id={panelId} className="border-t border-line bg-surface px-4 py-5">
					{item.result ? <ReportBody result={item.result} /> : <Notice tone="error" title="This file failed">{item.error}</Notice>}
				</div>
			)}
		</li>
	);
};

const BatchReport = ({ id }: { id: string }) => {
	const { data, error } = usePoll<BatchState>(`/api/batch/${id}`);

	if (error) {
		return (
			<Page width="max-w-2xl">
				<PageTitle title={`Batch ${id.slice(0, 8)}`} />
				<Notice tone="error" title={error.status === 404 ? "This batch has expired" : "The batch couldn’t be loaded"}>
					{error.status === 404 ? "Live batches last one hour. Finished results stay in History." : error.message}
				</Notice>
				<Link href="/analytics" className="btn-quiet mt-5">Open History</Link>
			</Page>
		);
	}

	const running = !data || (data.status !== "completed" && data.status !== "failed");
	return (
		<Page width="max-w-5xl">
			<PageTitle
				title={running ? "Batch in progress" : "Batch report"}
				lede={data ? `${data.completed_items} of ${data.total_items} files finished, highest scores first. Files run one at a time.` : undefined}
				actions={
					data && !running ? (
						<button type="button" className="btn-quiet" onClick={() => exportCsv(data.items, id)}>Export CSV</button>
					) : undefined
				}
			/>
			{running && <div className="mb-5"><Progress value={data?.progress ?? 5} label={data?.stage || "Connecting to the engine"} elapsed={data?.elapsed_seconds} /></div>}
			{data?.error && <div className="mb-5"><Notice tone="error" title="The batch stopped early">{data.error}</Notice></div>}
			{data && (
				<ul className="sheet divide-y divide-line">
					{ranked(data.items).map((item) => <Row key={item.item_id} item={item} />)}
				</ul>
			)}
		</Page>
	);
};

export default BatchReport;
