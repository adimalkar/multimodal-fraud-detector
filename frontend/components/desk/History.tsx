"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { type AnalyticsSummary, ApiError, downloadFile, request } from "@/lib/api";
import { dateTime, score100, TIER_BG, type TierKey, tierOf, titleCase } from "@/lib/format";
import Notice from "./Notice";
import Page from "./Page";
import PageTitle from "./PageTitle";

const BANDS: Array<{ key: TierKey; label: string; field: keyof NonNullable<AnalyticsSummary["severity_breakdown"]> }> = [
	{ key: "low", label: "Low", field: "low_risk" },
	{ key: "elevated", label: "Elevated", field: "suspicious" },
	{ key: "high", label: "High", field: "high_risk" },
	{ key: "critical", label: "Very high", field: "critical_fraud" },
];

const TierBar = ({ counts }: { counts: NonNullable<AnalyticsSummary["severity_breakdown"]> }) => {
	const total = BANDS.reduce((sum, band) => sum + counts[band.field], 0);
	return (
		<div>
			<h2 className="label mb-3">Files by score band</h2>
			{total === 0 ? (
				<p className="text-muted">No scored files yet.</p>
			) : (
				<>
					<div className="flex h-5 gap-0.5" role="img" aria-label={BANDS.map((band) => `${band.label}: ${counts[band.field]}`).join(", ")}>
						{BANDS.filter((band) => counts[band.field] > 0).map((band) => (
							<div
								key={band.key}
								title={`${band.label}: ${counts[band.field]} of ${total}`}
								className={TIER_BG[band.key]}
								style={{ width: `${(counts[band.field] / total) * 100}%` }}
							/>
						))}
					</div>
					<ul className="mt-3 flex flex-wrap gap-x-6 gap-y-1">
						{BANDS.map((band) => (
							<li key={band.key} className="flex items-center gap-2">
								<span aria-hidden="true" className={`h-3 w-3 rounded-sm ${TIER_BG[band.key]}`} />
								{band.label}
								<span className="font-data font-bold">{counts[band.field]}</span>
							</li>
						))}
					</ul>
				</>
			)}
		</div>
	);
};

const History = () => {
	const [data, setData] = useState<AnalyticsSummary | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [exporting, setExporting] = useState(false);
	const [exportError, setExportError] = useState<string | null>(null);

	useEffect(() => {
		let active = true;
		request<AnalyticsSummary>("/api/analytics/stats")
			.then((summary) => active && setData(summary))
			.catch((caught: ApiError) => active && setError(caught.message));
		return () => {
			active = false;
		};
	}, []);

	const exportAll = async () => {
		setExporting(true);
		setExportError(null);
		try {
			await downloadFile("/api/analytics/export-csv", "fraudsight-history.csv");
		} catch (caught) {
			setExportError((caught as ApiError).message);
		} finally {
			setExporting(false);
		}
	};

	return (
		<Page>
			<PageTitle
				title="History"
				lede="The 25 most recent screenings, newest first. Export the CSV for the full record."
				actions={
					<button type="button" onClick={exportAll} disabled={exporting || !data?.total_records} className="btn-quiet">
						{exporting ? "Exporting…" : "Export CSV"}
					</button>
				}
			/>
			{exportError && <div className="mb-5"><Notice tone="error" title="The export failed">{exportError}</Notice></div>}
			{error && <Notice tone="error" title="History couldn’t be loaded">{error}</Notice>}
			{!data && !error && <p role="status" className="text-muted">Loading history…</p>}
			{data && data.total_records === 0 && (
				<div className="sheet p-8">
					<p className="text-xl font-bold">Nothing screened yet</p>
					<p className="mt-1 text-muted">Finished screenings appear here.</p>
					<Link href="/analyze" className="btn-primary mt-4">Screen a file</Link>
				</div>
			)}
			{data && data.total_records > 0 && (
				<>
					<div className="sheet grid gap-6 p-5 md:grid-cols-[3fr_2fr] md:p-7">
						{data.severity_breakdown && <TierBar counts={data.severity_breakdown} />}
						<dl className="grid grid-cols-2 gap-x-6 gap-y-2 font-data text-sm">
							{[
								["Files screened", data.processed_records],
								["Photos", data.media_counts.images],
								["PDFs", data.media_counts.documents],
								["Videos", data.media_counts.videos],
								["Average time", `${data.avg_processing_time_sec}s`],
								["Storage", data.database_engine ?? "–"],
							].map(([label, value]) => (
								<div key={label} className="flex justify-between gap-3 border-b border-line pb-1">
									<dt className="text-muted">{label}</dt>
									<dd className="font-bold">{value}</dd>
								</div>
							))}
						</dl>
					</div>
					<div className="sheet relative mt-5 overflow-x-auto">
						<table className="w-full min-w-[720px] border-collapse text-left">
							<caption className="sr-only">The 25 most recent screenings</caption>
							<thead>
								<tr className="border-b border-line">
									{["File", "Type", "Score", "Band", "Screened"].map((heading) => (
										<th key={heading} scope="col" className="label px-4 py-2.5 font-normal">{heading}</th>
									))}
								</tr>
							</thead>
							<tbody>
								{data.recent_evaluations.map((row) => {
									const tier = tierOf(row.severity_tier);
									return (
										<tr key={row.id} className="border-b border-line align-top">
											<th scope="row" className="max-w-xs px-4 py-3 font-normal">
												<span className="block truncate font-data text-sm">{row.filename}</span>
												{row.final_reasoning && <span className="mt-0.5 line-clamp-2 block text-sm leading-snug text-muted">{row.final_reasoning}</span>}
											</th>
											<td className="px-4 py-3">{titleCase(row.media_type || "–")}</td>
											<td className="px-4 py-3 font-data font-bold">{score100(row.risk_score)}</td>
											<td className="whitespace-nowrap px-4 py-3">
												<span className="flex items-center gap-2">
													<span aria-hidden="true" className={`h-2.5 w-2.5 rounded-sm ${TIER_BG[tier.key]}`} />
													{tier.label}
												</span>
											</td>
											<td className="whitespace-nowrap px-4 py-3 text-sm text-muted">{dateTime(row.processed_at)}</td>
										</tr>
									);
								})}
							</tbody>
						</table>
					</div>
				</>
			)}
		</Page>
	);
};

export default History;
