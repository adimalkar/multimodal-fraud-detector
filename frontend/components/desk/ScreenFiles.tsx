"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, request } from "@/lib/api";
import { bytes } from "@/lib/format";
import { rememberPreview } from "@/lib/session";
import EvidenceTiles from "./EvidenceTiles";
import Notice from "./Notice";
import RecentScreenings from "./RecentScreenings";
import { useEngine } from "./useEngine";

const IMAGE = ["jpg", "jpeg", "png", "webp"];
const VIDEO = ["mp4", "mov", "avi", "mkv", "webm"];
const EXTENSIONS = [...IMAGE, "pdf", ...VIDEO];
const MAX_MB = 50;
const MAX_FILES = 10;

const extensionOf = (file: File) => file.name.split(".").pop()?.toLowerCase() ?? "";

const problemWith = (file: File): string | null => {
	if (!EXTENSIONS.includes(extensionOf(file))) return "This file type can’t be screened.";
	if (file.size === 0) return "This file is empty.";
	if (file.size > MAX_MB * 1024 * 1024) return `This file is over the ${MAX_MB} MB limit.`;
	return null;
};

const Thumb = ({ file }: { file: File }) => {
	const extension = extensionOf(file);
	const [url, setUrl] = useState<string | null>(null);

	useEffect(() => {
		if (!IMAGE.includes(extension) && !VIDEO.includes(extension)) return;
		const made = URL.createObjectURL(file);
		setUrl(made);
		return () => URL.revokeObjectURL(made);
	}, [file, extension]);

	if (url && IMAGE.includes(extension)) {
		// A local object URL, so next/image has nothing to optimise.
		// eslint-disable-next-line @next/next/no-img-element
		return <img src={url} alt="" className="h-full w-full object-cover" />;
	}
	if (url && VIDEO.includes(extension)) {
		return <video src={url} muted preload="metadata" className="h-full w-full object-cover" />;
	}
	return (
		<div className="flex h-full items-center justify-center bg-raised">
			<span className="font-data text-sm uppercase text-muted">{extension || "file"}</span>
		</div>
	);
};

const ALWAYS = [
	{ check: "Visual screening", detail: "One capped request to a vision model" },
	{ check: "File metadata", detail: "Camera, GPS, software and document tags" },
	{ check: "Provisional score", detail: "Uncalibrated, with the reasons behind it" },
];

const PlanPanel = ({ files }: { files: File[] }) => {
	const kinds = useMemo(() => new Set(files.map(extensionOf)), [files]);
	const hasPdf = kinds.has("pdf");
	const hasVideo = VIDEO.some((kind) => kinds.has(kind));

	return (
		<aside className="flex flex-col gap-6 border-t border-line p-5 md:p-8 lg:border-l lg:border-t-0">
			<div>
				<h2 className="label">What will run</h2>
				<ul className="mt-3 grid gap-3">
					{ALWAYS.map((item) => (
						<li key={item.check}>
							<p className="font-medium">{item.check}</p>
							<p className="text-sm leading-snug text-muted">{item.detail}</p>
						</li>
					))}
					{hasPdf && (
						<li>
							<p className="font-medium">PDF pages</p>
							<p className="text-sm leading-snug text-muted">The first 3 pages are rendered for screening</p>
						</li>
					)}
					{hasVideo && (
						<li>
							<p className="font-medium">Video frames</p>
							<p className="text-sm leading-snug text-muted">3 frames are sampled for screening</p>
						</li>
					)}
				</ul>
			</div>
			<div className="border-t border-line pt-5">
				<p className="font-medium">Then a person decides</p>
				<p className="text-sm leading-snug text-muted">The report is evidence for your review, not a verdict.</p>
			</div>
			<Link href="/signals" className="rounded-2xl border border-line p-4 transition-colors hover:border-muted">
				<p className="font-medium">Looking at a whole claim?</p>
				<p className="mt-0.5 text-sm leading-snug text-muted">Claim signals checks timing, travel, shared identifiers and past findings.</p>
			</Link>
			<p className="mt-auto text-sm leading-snug text-muted">
				{EXTENSIONS.length} file types. Up to {MAX_MB} MB each, {MAX_FILES} files at a time. Each file uses a paid model request.
			</p>
		</aside>
	);
};

const ScreenFiles = () => {
	const router = useRouter();
	const { state } = useEngine();
	const inputRef = useRef<HTMLInputElement>(null);
	const [files, setFiles] = useState<File[]>([]);
	const [dragging, setDragging] = useState(false);
	const [submitting, setSubmitting] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const add = useCallback((incoming: FileList | null) => {
		if (!incoming) return;
		// A FileList is live and empties when the input resets, so copy it now.
		const added = Array.from(incoming);
		setError(null);
		setFiles((current) => {
			const known = new Set(current.map((file) => `${file.name}:${file.size}`));
			return [...current, ...added.filter((file) => !known.has(`${file.name}:${file.size}`))];
		});
	}, []);

	const problems = files.map(problemWith);
	const hasProblems = problems.some(Boolean);
	const tooMany = files.length > MAX_FILES;
	const blocked = state === "unconfigured" || state === "offline" || state === "needs-token";
	const ready = files.length > 0 && !hasProblems && !tooMany && !blocked && !submitting;

	const submit = async () => {
		setSubmitting(true);
		setError(null);
		try {
			const form = new FormData();
			if (files.length === 1) {
				form.append("file", files[0]);
				const { job_id } = await request<{ job_id: string }>("/api/analyze", { method: "POST", body: form });
				rememberPreview(job_id, files[0]);
				router.push(`/analyze/job/${job_id}`);
			} else {
				files.forEach((file) => form.append("files", file));
				const { batch_id } = await request<{ batch_id: string }>("/api/batch/analyze", { method: "POST", body: form });
				router.push(`/analyze/batch/${batch_id}`);
			}
		} catch (caught) {
			setError((caught as ApiError).message);
			setSubmitting(false);
		}
	};

	return (
		<div className="grid flex-1 lg:grid-cols-[minmax(0,1fr)_340px]">
			<section
				aria-label="Add evidence"
				onDragOver={(event) => {
					event.preventDefault();
					setDragging(true);
				}}
				onDragLeave={(event) => {
					if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false);
				}}
				onDrop={(event) => {
					event.preventDefault();
					setDragging(false);
					add(event.dataTransfer.files);
				}}
				className="dots flex min-w-0 flex-col p-4 md:p-8"
			>
				<div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
					<h1 className="display text-4xl md:text-6xl">Screen evidence</h1>
					<p className="max-w-sm text-sm leading-snug text-muted md:text-right">One file gets a report. Several get a batch ranked by score.</p>
				</div>

				{files.length === 0 ? (
					<div className={`relative mt-6 flex flex-1 flex-col rounded-3xl border p-3 transition-colors duration-300 md:p-4 ${dragging ? "border-transparent bg-uv-tint" : "border-line bg-surface/70"}`}>
						{dragging && <span aria-hidden="true" className="beam" />}
						<div className="flex flex-wrap items-center justify-between gap-3 px-1 pb-4 pt-1">
							<p className="text-xl font-medium tracking-tight md:text-2xl">{dragging ? "Drop to add" : "Drop a claim’s files anywhere here"}</p>
							<button type="button" className="btn-primary" onClick={() => inputRef.current?.click()}>Choose files</button>
						</div>
						<EvidenceTiles onPick={() => inputRef.current?.click()} lifted={dragging} />
					</div>
				) : (
					<div className={`relative mt-6 flex-1 rounded-3xl border p-3 transition-colors md:p-4 ${dragging ? "border-transparent bg-uv-tint" : "border-line bg-surface/70"}`}>
						{dragging && <span aria-hidden="true" className="beam" />}
						<ul className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
							{files.map((file, index) => (
								<li key={`${file.name}:${file.size}`} className={`overflow-hidden rounded-2xl border bg-canvas ${problems[index] ? "border-status-bad" : "border-line"}`}>
									<div className="aspect-[4/3] overflow-hidden"><Thumb file={file} /></div>
									<div className="flex items-start gap-2 p-3">
										<div className="min-w-0 flex-1">
											<p className="truncate font-data text-xs">{file.name}</p>
											<p className={`mt-0.5 text-xs ${problems[index] ? "font-medium text-status-bad" : "text-muted"}`}>{problems[index] ?? bytes(file.size)}</p>
										</div>
										<button
											type="button"
											onClick={() => setFiles(files.filter((_, position) => position !== index))}
											aria-label={`Remove ${file.name}`}
											className="-m-1 min-h-8 rounded px-1.5 text-xs text-muted underline hover:text-ink"
										>
											Remove
										</button>
									</div>
								</li>
							))}
							<li>
								<button
									type="button"
									onClick={() => inputRef.current?.click()}
									className="flex h-full min-h-40 w-full items-center justify-center rounded-2xl border border-dashed border-line text-sm text-muted transition-colors hover:border-muted hover:text-ink"
								>
									Add more files
								</button>
							</li>
						</ul>
					</div>
				)}

				<input
					ref={inputRef}
					type="file"
					multiple
					className="sr-only"
					aria-label="Choose files to screen"
					tabIndex={-1}
					accept={EXTENSIONS.map((extension) => `.${extension}`).join(",")}
					onChange={(event) => {
						add(event.target.files);
						event.target.value = "";
					}}
				/>

				<div className="mt-4 grid gap-3 empty:hidden">
					{tooMany && <Notice tone="error" title={`Remove ${files.length - MAX_FILES} of these files`}>A batch holds up to {MAX_FILES} files.</Notice>}
					{hasProblems && <Notice tone="error" title="Remove the marked files to continue" />}
					{error && <Notice tone="error" title="The screening didn’t start">{error}</Notice>}
					{state === "unconfigured" && <Notice tone="warn" title="Screening is unavailable">The engine has no model key yet. Add OPENROUTER_API_KEY to the engine, then try again.</Notice>}
					{state === "needs-token" && <Notice tone="warn" title="Add your access token">This deployment needs a token. Open engine status at the top of the page to add it.</Notice>}
					{state === "offline" && <Notice tone="warn" title="The engine isn’t responding">It may be restarting. This page checks again every 30 seconds.</Notice>}
				</div>

				{files.length > 0 && (
					<div className="sticky bottom-4 mt-4 flex justify-end">
						<button type="button" className="btn-primary !min-h-12 !px-7 text-base shadow-2xl" disabled={!ready} onClick={submit}>
							{submitting ? "Uploading…" : files.length > 1 ? `Screen ${files.length} files` : "Screen file"}
						</button>
					</div>
				)}

				<RecentScreenings />
			</section>
			<PlanPanel files={files} />
		</div>
	);
};

export default ScreenFiles;
