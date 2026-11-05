"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { type AnalyticsSummary, type Evaluation, request } from "@/lib/api";
import { dateTime, score100, TIER_BG, tierOf, titleCase } from "@/lib/format";

const SHOWN = 5;

const RecentScreenings = () => {
	const [rows, setRows] = useState<Evaluation[] | null>(null);
	const [unavailable, setUnavailable] = useState(false);

	useEffect(() => {
		let active = true;
		request<AnalyticsSummary>("/api/analytics/stats")
			.then((summary) => active && setRows(summary.recent_evaluations.slice(0, SHOWN)))
			.catch(() => active && setUnavailable(true));
		return () => {
			active = false;
		};
	}, []);

	return (
		<section aria-label="Recent screenings" className="sheet mt-4 p-4 md:p-5">
			<div className="flex items-baseline justify-between gap-4">
				<h2 className="font-medium">Recent screenings</h2>
				<Link href="/analytics" className="text-sm text-muted underline hover:text-ink">Open History</Link>
			</div>
			{unavailable && <p className="mt-2 text-sm text-muted">History isn’t available on this deployment.</p>}
			{!unavailable && rows === null && <p role="status" className="mt-2 text-sm text-muted">Loading…</p>}
			{rows?.length === 0 && <p className="mt-2 text-sm text-muted">Nothing screened yet. Your last {SHOWN} screenings will appear here.</p>}
			{rows && rows.length > 0 && (
				<ul className="mt-2 divide-y divide-line">
					{rows.map((row) => {
						const tier = tierOf(row.severity_tier);
						return (
							<li key={row.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 py-2.5 text-sm md:grid-cols-[minmax(0,1fr)_6rem_9rem_3rem_10rem]">
								<span className="truncate font-data text-xs">{row.filename}</span>
								<span className="hidden text-muted md:block">{titleCase(row.media_type || "–")}</span>
								<span className="hidden items-center gap-2 md:flex">
									<span aria-hidden="true" className={`h-2.5 w-2.5 rounded-sm ${TIER_BG[tier.key]}`} />
									{tier.label}
								</span>
								<span className="text-right font-data font-bold">{score100(row.risk_score)}</span>
								<span className="hidden text-right text-xs text-muted md:block">{dateTime(row.processed_at)}</span>
							</li>
						);
					})}
				</ul>
			)}
		</section>
	);
};

export default RecentScreenings;
