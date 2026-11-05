"use client";

import { useState } from "react";
import { API_URL, getAccessToken, setAccessToken } from "@/lib/api";
import { type EngineState, useEngine } from "./useEngine";

const COPY: Record<EngineState, { dot: string; title: string; hint?: string }> = {
	checking: { dot: "bg-graphite", title: "Checking engine" },
	waking: {
		dot: "bg-marker",
		title: "Waking the engine",
		hint: "A sleeping engine can take up to a minute to start.",
	},
	online: { dot: "bg-status-good", title: "Engine online" },
	unconfigured: {
		dot: "bg-status-warn",
		title: "Engine has no model key",
		hint: "Add OPENROUTER_API_KEY to the engine to run screenings.",
	},
	"needs-token": {
		dot: "bg-status-warn",
		title: "Access token needed",
		hint: "This deployment only accepts signed-in tenants.",
	},
	offline: {
		dot: "bg-status-bad",
		title: "Engine not responding",
		hint: "It may be restarting. This page keeps checking.",
	},
};

const EngineStatus = () => {
	const { state, health, refresh } = useEngine();
	const [token, setToken] = useState("");
	const [open, setOpen] = useState(false);
	const copy = COPY[state];
	const durable = health?.job_backend === "durable" || state === "needs-token";

	return (
		<div className="text-sm">
			<p className="flex items-center gap-2 font-bold" role="status">
				<span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${copy.dot}`} />
				{copy.title}
			</p>
			{copy.hint && <p className="mt-1 leading-snug text-graphite">{copy.hint}</p>}
			{durable && (
				<div className="mt-2">
					<button type="button" className="underline hover:text-uv" onClick={() => setOpen(!open)} aria-expanded={open}>
						{getAccessToken() ? "Change access token" : "Add access token"}
					</button>
					{open && (
						<form
							className="mt-2 grid gap-2"
							onSubmit={(event) => {
								event.preventDefault();
								setAccessToken(token.trim());
								setToken("");
								setOpen(false);
								refresh();
							}}
						>
							<label className="label" htmlFor="engine-token">Access token</label>
							<input
								id="engine-token"
								type="password"
								autoComplete="off"
								value={token}
								onChange={(event) => setToken(event.target.value)}
								className="field"
							/>
							<button type="submit" className="btn-quiet !min-h-9 text-sm">Save for this tab</button>
						</form>
					)}
				</div>
			)}
			<p className="mt-2 break-all font-data text-xs text-graphite">{API_URL.replace(/^https?:\/\//, "")}</p>
		</div>
	);
};

export default EngineStatus;
