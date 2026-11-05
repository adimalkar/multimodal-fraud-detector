"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Notice from "@/components/desk/Notice";
import Page from "@/components/desk/Page";
import PageTitle from "@/components/desk/PageTitle";
import { type JobState, saveBlob } from "@/lib/api";
import { previewFor } from "@/lib/session";
import { usePoll } from "@/lib/usePoll";
import Progress from "./Progress";
import ReportBody from "./ReportBody";

const Preview = ({ id, scanning = false }: { id: string; scanning?: boolean }) => {
	const [preview, setPreview] = useState<ReturnType<typeof previewFor>>();
	useEffect(() => setPreview(previewFor(id)), [id]);

	const media = !preview ? (
		<div className="aspect-[4/3] w-full bg-raised" />
	) : preview.type.startsWith("image/") ? (
		// A local object URL, so next/image has nothing to optimise.
		// eslint-disable-next-line @next/next/no-img-element
		<img src={preview.url} alt={`Preview of ${preview.name}`} className="max-h-[72vh] w-full object-contain" />
	) : preview.type.startsWith("video/") ? (
		<video src={preview.url} controls={!scanning} muted className="max-h-[72vh] w-full">
			<track kind="captions" />
		</video>
	) : (
		<object data={preview.url} type="application/pdf" aria-label={`Preview of ${preview.name}`} className="h-[72vh] w-full" />
	);

	if (!preview && !scanning) return null;
	return (
		<figure className="sheet self-start overflow-hidden lg:sticky lg:top-24">
			<div className={`relative overflow-hidden bg-canvas ${scanning ? "scanline" : ""}`}>{media}</div>
			{preview && <figcaption className="truncate p-3 font-data text-xs text-muted">Original: {preview.name}</figcaption>}
		</figure>
	);
};

const JobReport = ({ id }: { id: string }) => {
	const { data, error } = usePoll<JobState>(`/api/jobs/${id}`);
	const reference = `Job ${id.slice(0, 8)}`;

	if (error) {
		const expired = error.status === 404;
		return (
			<Page width="max-w-2xl">
				<PageTitle title={reference} />
				<Notice tone="error" title={expired ? "This report has expired" : "The report couldn’t be loaded"}>
					{expired
						? "Live reports last one hour. Finished results stay in History."
						: error.message}
				</Notice>
				<div className="mt-5 flex flex-wrap gap-3">
					<Link href="/analytics" className="btn-quiet">Open History</Link>
					<Link href="/analyze" className="btn-primary">Screen a file</Link>
				</div>
			</Page>
		);
	}

	if (!data || (data.status !== "completed" && data.status !== "failed")) {
		return (
			<Page>
				<PageTitle title="Screening in progress" lede="You can leave this page open. The report appears here when the checks finish." />
				<div className="grid gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,4fr)]">
					<Preview id={id} scanning />
					<div>
						<Progress value={data?.progress ?? 5} label={data?.stage || "Connecting to the engine"} elapsed={data?.elapsed_seconds} />
						<p className="mt-3 font-data text-sm text-muted">{reference}</p>
					</div>
				</div>
			</Page>
		);
	}

	if (data.status === "failed" || !data.result) {
		return (
			<Page width="max-w-2xl">
				<PageTitle title="Screening failed" />
				<Notice tone="error" title="No report was produced">{data.error || "The engine stopped before finishing. Try the file again."}</Notice>
				<Link href="/analyze" className="btn-primary mt-5">Screen a file</Link>
			</Page>
		);
	}

	const result = data.result;
	return (
		<Page width="max-w-7xl">
			<PageTitle
				title="Screening report"
				actions={
					<button
						type="button"
						className="btn-quiet"
						onClick={() =>
							saveBlob(
								new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
								`fraudsight-report-${id.slice(0, 8)}.json`,
							)
						}
					>
						Download report
					</button>
				}
			/>
			<dl className="mb-6 flex flex-wrap gap-x-8 gap-y-1 font-data text-sm">
				<div className="flex gap-2"><dt className="text-muted">Job</dt><dd>{id.slice(0, 8)}</dd></div>
				{result.media_type && <div className="flex gap-2"><dt className="text-muted">Type</dt><dd>{result.media_type}</dd></div>}
				{data.artifact_sha256 && (
					<div className="flex min-w-0 gap-2"><dt className="text-muted">SHA-256</dt><dd className="break-all">{data.artifact_sha256}</dd></div>
				)}
			</dl>
			<div className="grid gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] [&:has(>:only-child)]:lg:grid-cols-1">
				<Preview id={id} />
				<div className="sheet min-w-0 p-5 md:p-7">
					<ReportBody result={result} />
				</div>
			</div>
		</Page>
	);
};

export default JobReport;
