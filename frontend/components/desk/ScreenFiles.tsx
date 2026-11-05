"use client";

import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { ApiError, request } from "@/lib/api";
import { bytes } from "@/lib/format";
import { rememberPreview } from "@/lib/session";
import Notice from "./Notice";
import PageTitle from "./PageTitle";
import { useEngine } from "./useEngine";

const EXTENSIONS = ["jpg", "jpeg", "png", "webp", "pdf", "mp4", "mov", "avi", "mkv", "webm"];
const MAX_MB = 50;
const MAX_FILES = 10;

const problemWith = (file: File): string | null => {
	const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
	if (!EXTENSIONS.includes(extension)) return "This file type can’t be screened.";
	if (file.size === 0) return "This file is empty.";
	if (file.size > MAX_MB * 1024 * 1024) return `This file is over the ${MAX_MB} MB limit.`;
	return null;
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
		<div className="max-w-3xl">
			<PageTitle title="Screen files" lede="Add the photos, PDFs or video from one claim. One file gets a report. Several get a batch you can sort." />

			<div
				onDragOver={(event) => {
					event.preventDefault();
					setDragging(true);
				}}
				onDragLeave={() => setDragging(false)}
				onDrop={(event) => {
					event.preventDefault();
					setDragging(false);
					add(event.dataTransfer.files);
				}}
				className={`border-2 border-dashed px-6 py-12 text-center transition-colors ${
					dragging ? "border-uv bg-uv-tint" : "border-graphite/50 bg-paper"
				}`}
			>
				<p className="text-lg font-bold">Drop files here</p>
				<button type="button" className="btn-quiet mt-4" onClick={() => inputRef.current?.click()}>
					Choose files
				</button>
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
				<p className="mt-4 text-sm text-graphite">
					JPG, PNG, WebP, PDF, MP4, MOV, AVI, MKV or WebM. Up to {MAX_MB} MB each, {MAX_FILES} files at a time.
				</p>
			</div>

			{files.length > 0 && (
				<ul className="sheet mt-4 divide-y divide-rule">
					{files.map((file, index) => (
						<li key={`${file.name}:${file.size}`} className="flex items-center gap-3 px-4 py-2.5">
							<div className="min-w-0 flex-1">
								<p className="truncate font-data text-sm">{file.name}</p>
								<p className={`text-sm ${problems[index] ? "font-bold text-status-bad" : "text-graphite"}`}>
									{problems[index] ?? bytes(file.size)}
								</p>
							</div>
							<button
								type="button"
								onClick={() => setFiles(files.filter((_, position) => position !== index))}
								aria-label={`Remove ${file.name}`}
								className="min-h-11 px-2 text-sm underline hover:text-uv"
							>
								Remove
							</button>
						</li>
					))}
				</ul>
			)}

			<div className="mt-4 grid gap-3">
				{tooMany && <Notice tone="error" title={`Remove ${files.length - MAX_FILES} of these files`}>A batch holds up to {MAX_FILES} files.</Notice>}
				{hasProblems && <Notice tone="error" title="Remove the marked files to continue" />}
				{error && <Notice tone="error" title="The screening didn’t start">{error}</Notice>}
				{state === "unconfigured" && (
					<Notice tone="warn" title="Screening is unavailable">The engine has no model key yet. Add OPENROUTER_API_KEY to the engine, then try again.</Notice>
				)}
				{state === "needs-token" && (
					<Notice tone="warn" title="Add your access token">This deployment needs a token. Add it under engine status.</Notice>
				)}
				{state === "offline" && <Notice tone="warn" title="The engine isn’t responding">It may be restarting. This page checks again every 30 seconds.</Notice>}
			</div>

			<div className="mt-5 flex flex-wrap items-center gap-4">
				<button type="button" className="btn-primary" disabled={!ready} onClick={submit}>
					{submitting ? "Uploading…" : files.length > 1 ? `Screen ${files.length} files` : "Screen file"}
				</button>
				<p className="text-sm text-graphite">Screening uses a paid model request for each file.</p>
			</div>
		</div>
	);
};

export default ScreenFiles;
