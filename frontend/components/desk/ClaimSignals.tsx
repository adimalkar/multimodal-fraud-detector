"use client";

import { useState } from "react";
import {
	ApiError,
	type ClaimEntity,
	type ClaimEvent,
	type ClaimSignals as Signals,
	type ClaimSignalsRequest,
	type DocumentHashInput,
	type IdentityProfileInput,
	type TimelineInput,
	request,
} from "@/lib/api";
import { percent } from "@/lib/format";
import Notice from "./Notice";
import Page from "./Page";
import PageTitle from "./PageTitle";
import { useEngine } from "./useEngine";

/* Rows are entered one per line, so an adjuster can paste from a spreadsheet. */
const EVENT_HEADER = "claimant, time, latitude, longitude, device";
const ENTITY_HEADER = "party, score 0-1, identifier=value, identifier=value";
const HISTORY_HEADER = "party, score 0-1, date, clean claims since";
const IDENTITY_HEADER = "party, name, email, carrier, account age days";
const TIMELINE_HEADER = "evidence id, type (PHOTO|INVOICE), time, latitude, longitude";
const HASH_HEADER = "party, document id, hex phash, time";

const SAMPLE = {
	events: [
		"CL-1042, 2026-03-12T09:00:00Z, 53.35, -6.26, phone-a",
		"CL-1042, 2026-03-12T09:02:00Z, 1.35, 103.82, phone-b",
		"CL-1042, 2026-03-12T09:03:30Z, 1.35, 103.82, laptop-c",
		"CL-2077, 2026-03-12T11:00:00Z, 51.90, -8.47, phone-d",
	].join("\n"),
	entities: [
		"CL-1042, 0.8, bank=IE29-0001, phone=+353-555-0101",
		"CL-2077, 0.1, bank=IE29-0001, address=14 Harbour Road",
		"CL-3310, 0.2, address=14 Harbour Road",
		"CL-4001, 0.1, bank=IE29-0999",
	].join("\n"),
	history: ["CL-1042, 0.9, 2026-02-20T00:00:00Z, 0", "CL-2077, 0.7, 2025-11-01T00:00:00Z, 3"].join("\n"),
	identities: [
		"CL-1042, Jordan Lee, z8q2x9k@mailinator.com, VOIP, 1",
		"CL-2077, Morgan Hayes, morgan.hayes@gmail.com, MOBILE, 420",
	].join("\n"),
	incidentTime: "2026-03-12T08:00:00Z",
	filingTime: "2026-03-12T10:00:00Z",
	timelineEvents: [
		"doc-1, PHOTO, 2026-02-01T12:00:00Z, 40.71, -74.01",
		"inv-1, INVOICE, 2026-03-11T17:00:00Z",
	].join("\n"),
	hashes: [
		"CL-2077, doc-1, 0f0f0f0f0f0f0f0f, 2026-03-12T08:30:00Z",
		"CL-1042, doc-9, 0f0f0f0f0f0f0f0e, 2026-03-12T09:05:00Z",
	].join("\n"),
	asOf: "2026-03-12",
	visual: 0.9,
	text: 0.1,
	metadata: 0.15,
};

class RowError extends Error {}

const rows = (text: string) =>
	text
		.split("\n")
		.map((line, index) => ({ cells: line.split(",").map((cell) => cell.trim()), line: index + 1, blank: !line.trim() }))
		.filter((row) => !row.blank);

const seconds = (value: string, where: string) => {
	const parsed = Date.parse(value);
	if (Number.isNaN(parsed)) throw new RowError(`${where}: “${value}” isn’t a date. Use a format like 2026-03-12T09:00:00Z.`);
	return parsed / 1000;
};

const number = (value: string | undefined, where: string) => {
	const parsed = Number(value);
	if (value === undefined || value === "" || Number.isNaN(parsed)) throw new RowError(`${where}: “${value ?? ""}” isn’t a number.`);
	return parsed;
};

const parseEvents = (text: string): ClaimEvent[] =>
	rows(text).map(({ cells, line }) => {
		const where = `Claim events, line ${line}`;
		const [claimant_id, time, lat, lon, device] = cells;
		if (!claimant_id || !time) throw new RowError(`${where}: add a claimant and a time.`);
		return {
			claimant_id,
			timestamp: seconds(time, where),
			...(lat && lon ? { lat: number(lat, where), lon: number(lon, where) } : {}),
			...(device ? { device_fingerprint: device } : {}),
		};
	});

const parseEntities = (text: string): ClaimEntity[] =>
	rows(text).map(({ cells, line }) => {
		const where = `Parties, line ${line}`;
		const [entity_id, score, ...pairs] = cells;
		if (!entity_id) throw new RowError(`${where}: add a party.`);
		const attributes: Record<string, string> = {};
		pairs.forEach((pair) => {
			const [key, ...value] = pair.split("=");
			if (!key || value.length === 0) throw new RowError(`${where}: “${pair}” should look like bank=IE29-0001.`);
			attributes[key.trim()] = value.join("=").trim();
		});
		return { entity_id, base_risk: number(score, where), attributes };
	});

const parseHistory = (text: string) =>
	rows(text).map(({ cells, line }) => {
		const where = `Past findings, line ${line}`;
		const [entity_id, score, date, clean] = cells;
		if (!entity_id || !date) throw new RowError(`${where}: add a party, a score and a date.`);
		return {
			entity_id,
			risk_score: number(score, where),
			timestamp: seconds(date, where),
			clean_events_since: clean ? number(clean, where) : 0,
		};
	});

const parseIdentities = (text: string): IdentityProfileInput[] =>
	rows(text).map(({ cells, line }) => {
		const where = `Identities, line ${line}`;
		const [entity_id, name, email, carrier, age] = cells;
		if (!entity_id || !name || !email) {
			throw new RowError(`${where}: add a party, name and email.`);
		}
		return {
			entity_id,
			name,
			email,
			phone_carrier: carrier || "MOBILE",
			...(age ? { account_age_days: Math.round(number(age, where)) } : {}),
		};
	});

const parseTimeline = (incident: string, filing: string, text: string): TimelineInput | undefined => {
	const evidenceRows = rows(text);
	if (!incident.trim() && evidenceRows.length === 0) return undefined;
	if (!incident.trim()) {
		throw new RowError("Timeline audit: enter an incident date/time to audit evidence events.");
	}
	const evidence_events = evidenceRows.map(({ cells, line }) => {
		const where = `Timeline events, line ${line}`;
		const [event_id, event_type, time, lat, lon] = cells;
		if (!event_id || !event_type || !time) {
			throw new RowError(`${where}: add an evidence id, type and time.`);
		}
		if ((lat && !lon) || (!lat && lon)) {
			throw new RowError(`${where}: provide both latitude and longitude together.`);
		}
		return {
			event_id,
			event_type,
			timestamp: seconds(time, where),
			...(lat && lon ? { lat: number(lat, where), lon: number(lon, where) } : {}),
		};
	});
	return {
		incident_time: seconds(incident.trim(), "Timeline incident time"),
		...(filing.trim() ? { filing_time: seconds(filing.trim(), "Timeline filing time") } : {}),
		evidence_events,
	};
};

const parseHashes = (text: string): DocumentHashInput[] =>
	rows(text).map(({ cells, line }) => {
		const where = `Document hashes, line ${line}`;
		const [entity_id, image_id, phash, time] = cells;
		if (!entity_id || !image_id || !phash) {
			throw new RowError(`${where}: add a party, document id and perceptual hash.`);
		}
		return {
			entity_id,
			image_id,
			phash,
			...(time ? { timestamp: seconds(time, where) } : {}),
		};
	});

const Rows = ({
	id,
	title,
	hint,
	header,
	value,
	onChange,
}: {
	id: string;
	title: string;
	hint: string;
	header: string;
	value: string;
	onChange: (value: string) => void;
}) => (
	<div>
		<label htmlFor={id} className="font-bold">{title}</label>
		<p className="text-muted">{hint}</p>
		<p className="mt-2 font-data text-xs text-muted">{header}</p>
		<textarea
			id={id}
			rows={5}
			spellCheck={false}
			value={value}
			onChange={(event) => onChange(event.target.value)}
			className="field mt-1 resize-y py-2 leading-relaxed"
		/>
	</div>
);

const Slider = ({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) => (
	<label className="grid grid-cols-[6rem_1fr_3rem] items-center gap-3">
		<span>{label}</span>
		<input
			type="range"
			min={0}
			max={1}
			step={0.05}
			value={value}
			onChange={(event) => onChange(Number(event.target.value))}
			className="min-h-11 accent-[var(--uv)]"
		/>
		<span className="text-right font-data">{percent(value)}</span>
	</label>
);

const CONFLICT_LABELS: Record<string, string> = {
	CRITICAL_MODAL_MASKING: "One signal stands far above the rest",
	HIGH_CONFLICT: "Signals disagree",
	MILD_DISCREPANCY: "Signals differ slightly",
	CONGRUENT: "Signals agree",
};

const Result = ({ title, skipped, children }: { title: string; skipped: boolean; children?: React.ReactNode }) => (
	<section className="sheet p-5">
		<h3 className="text-lg font-bold">{title}</h3>
		{skipped ? <p className="mt-1 text-muted">Not checked. No input for this section.</p> : <div className="mt-3">{children}</div>}
	</section>
);

const Flag = ({ on, yes, no }: { on: boolean; yes: string; no: string }) => (
	<span className={`inline-block px-2 py-0.5 font-data text-xs ${on ? "bg-marker text-[#14161b]" : "border border-line text-muted"}`}>
		{on ? yes : no}
	</span>
);

const Table = ({ heads, children }: { heads: string[]; children: React.ReactNode }) => (
	<div className="overflow-x-auto">
		<table className="w-full min-w-[440px] border-collapse text-left text-sm">
			<thead>
				<tr className="border-b border-ink">
					{heads.map((head) => <th key={head} scope="col" className="label py-1.5 pr-3 font-normal">{head}</th>)}
				</tr>
			</thead>
			<tbody className="[&_td]:py-2 [&_td]:pr-3 [&_tr]:border-b [&_tr]:border-line">{children}</tbody>
		</table>
	</div>
);

const Results = ({ data }: { data: Signals }) => (
	<div className="grid gap-4">
		<Notice title="Signals, not findings">{data.notice} Nothing you enter here is stored.</Notice>

		<Result title="Claim timing" skipped={!data.velocity}>
			<Table heads={["Claimant", "Events", "Most in 5 min", "Pattern"]}>
				{data.velocity?.map((item) => (
					<tr key={item.claimant_id}>
						<td className="font-data">{item.claimant_id}</td>
						<td>{item.events}</td>
						<td>{item.peak_window_count}</td>
						<td><Flag on={item.burst_flagged} yes="Burst" no="Steady" /></td>
					</tr>
				))}
			</Table>
		</Result>

		<Result title="Travel and devices" skipped={!data.travel}>
			<Table heads={["Claimant", "Fastest move", "Devices", "Pattern"]}>
				{data.travel?.map((item) => (
					<tr key={item.user_id}>
						<td className="font-data">{item.user_id}</td>
						<td>{item.calculated_speed_kmh ? `${item.calculated_speed_kmh.toLocaleString()} km/h` : "–"}</td>
						<td>{item.distinct_devices_count || "–"}</td>
						<td className="space-x-1">
							<Flag on={item.impossible_travel_detected} yes="Impossible travel" no="Plausible" />
							{item.device_churn_detected && <Flag on yes="Many devices" no="" />}
						</td>
					</tr>
				))}
			</Table>
		</Result>

		<Result title="Shared identifiers" skipped={!data.network}>
			{data.network?.rings.length === 0 ? (
				<p>No parties share an identifier.</p>
			) : (
				<ul className="grid gap-3">
					{data.network?.rings.map((ring) => (
						<li key={ring.ring_id} className="border-l-[3px] border-uv pl-3">
							<p className="font-bold">{ring.size} linked parties <Flag on={ring.is_syndicate} yes="Review together" no="Weak link" /></p>
							<p className="font-data text-sm">{ring.entities.join(", ")}</p>
							<p className="text-sm text-muted">Sharing {ring.shared_attributes.map((attribute) => attribute.replace(":", " ")).join("; ")}</p>
						</li>
					))}
				</ul>
			)}
			{data.network && data.network.entities.length > 0 && (
				<div className="mt-4">
					<Table heads={["Party", "Own score", "With links", "Linked to"]}>
						{data.network.entities.map((item) => (
							<tr key={item.entity_id}>
								<td className="font-data">{item.entity_id}</td>
								<td>{percent(item.base_risk)}</td>
								<td className="font-bold">{percent(item.propagated_risk)}</td>
								<td>{item.neighbor_count}</td>
							</tr>
						))}
					</Table>
				</div>
			)}
		</Result>

		<Result title="Signal conflict" skipped={!data.conflict}>
			{data.conflict && (
				<>
					<p>
						<Flag
							on={data.conflict.conflict_detected}
							yes={CONFLICT_LABELS[data.conflict.conflict_tier] ?? "Signals disagree"}
							no={CONFLICT_LABELS[data.conflict.conflict_tier] ?? "Signals agree"}
						/>
					</p>
					<dl className="mt-3 grid gap-1 font-data text-sm sm:grid-cols-3 sm:gap-6">
						<div><dt className="text-muted">Largest gap</dt><dd className="text-lg font-bold">{percent(data.conflict.max_divergence)}</dd></div>
						<div><dt className="text-muted">Simple average</dt><dd className="text-lg font-bold">{percent(data.conflict.linear_fused_risk)}</dd></div>
						<div><dt className="text-muted">Adjusted score</dt><dd className="text-lg font-bold">{percent(data.conflict.adjusted_fused_risk)}</dd></div>
					</dl>
					{data.conflict.conflict_detected && (
						<p className="mt-2 text-muted">One strong signal can be hidden by quiet ones in an average, so the adjusted score keeps it visible.</p>
					)}
				</>
			)}
		</Result>

		<Result title="Past findings over time" skipped={!data.history}>
			<Table heads={["Party", "Peak", "Still counts", "Days since", "Clean claims"]}>
				{data.history?.map((item) => (
					<tr key={item.entity_id}>
						<td className="font-data">{item.entity_id}</td>
						<td>{percent(item.original_peak_risk)}</td>
						<td className="font-bold">{percent(item.decayed_risk_score)}</td>
						<td>{item.days_elapsed}</td>
						<td>{item.clean_events_count}</td>
					</tr>
				))}
			</Table>
		</Result>

		<Result title="Synthetic identities" skipped={!data.identities}>
			<Table heads={["Party", "Name", "Domain & carrier", "Score", "Signals"]}>
				{data.identities?.map((item, idx) => (
					<tr key={`${item.entity_id ?? item.identity_metadata.email_handle}-${idx}`}>
						<td className="font-data">{item.entity_id ?? "–"}</td>
						<td>{item.identity_metadata.name}</td>
						<td className="font-data text-xs">
							{item.identity_metadata.email_domain || "unknown"} ({item.identity_metadata.phone_carrier})
						</td>
						<td className="font-bold">{percent(item.synthetic_risk_score)}</td>
						<td className="space-x-1">
							<Flag on={item.synthetic_risk_score >= 0.55} yes={item.risk_tier} no={item.risk_tier} />
						</td>
					</tr>
				))}
			</Table>
		</Result>

		<Result title="Incident timeline audit" skipped={!data.timeline}>
			{data.timeline && (
				<>
					<p className="flex flex-wrap items-center gap-3">
						<Flag
							on={data.timeline.total_anomalies > 0}
							yes={`${data.timeline.total_anomalies} anomaly findings (${data.timeline.severity_tier})`}
							no="Timeline coherent"
						/>
						<span className="font-data text-sm">Risk {percent(data.timeline.timeline_risk_score)}</span>
					</p>
					{data.timeline.flags.length > 0 && (
						<ul className="mt-3 grid gap-1.5 font-data text-xs text-muted">
							{data.timeline.flags.map((flag) => (
								<li key={flag} className="border-l-2 border-uv pl-2">{flag}</li>
							))}
						</ul>
					)}
				</>
			)}
		</Result>

		<Result title="Document hash collisions" skipped={!data.hashes}>
			<Table heads={["Party", "Document", "Perceptual hash", "Min distance", "Score", "Status"]}>
				{data.hashes?.map((item) => (
					<tr key={`${item.entity_id}-${item.image_id}`}>
						<td className="font-data">{item.entity_id}</td>
						<td className="font-data">{item.image_id}</td>
						<td className="font-data text-xs">{item.phash_hex}</td>
						<td>{item.nearest_collision_distance ?? "–"}</td>
						<td className="font-bold">{percent(item.duplicate_risk_score)}</td>
						<td>
							<Flag on={item.duplicate_detected} yes={item.severity_tier} no="UNIQUE" />
						</td>
					</tr>
				))}
			</Table>
		</Result>
	</div>
);

const ClaimSignals = () => {
	const { state } = useEngine();
	const [events, setEvents] = useState("");
	const [entities, setEntities] = useState("");
	const [history, setHistory] = useState("");
	const [identities, setIdentities] = useState("");
	const [incidentTime, setIncidentTime] = useState("");
	const [filingTime, setFilingTime] = useState("");
	const [timelineEvents, setTimelineEvents] = useState("");
	const [hashes, setHashes] = useState("");
	const [asOf, setAsOf] = useState(() => new Date().toISOString().slice(0, 10));
	const [useScores, setUseScores] = useState(false);
	const [visual, setVisual] = useState(0.5);
	const [text, setText] = useState(0.5);
	const [metadata, setMetadata] = useState(0.5);
	const [result, setResult] = useState<Signals | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [running, setRunning] = useState(false);

	const empty =
		!events.trim() &&
		!entities.trim() &&
		!history.trim() &&
		!identities.trim() &&
		!incidentTime.trim() &&
		!timelineEvents.trim() &&
		!hashes.trim() &&
		!useScores;

	const loadSample = () => {
		setEvents(SAMPLE.events);
		setEntities(SAMPLE.entities);
		setHistory(SAMPLE.history);
		setIdentities(SAMPLE.identities);
		setIncidentTime(SAMPLE.incidentTime);
		setFilingTime(SAMPLE.filingTime);
		setTimelineEvents(SAMPLE.timelineEvents);
		setHashes(SAMPLE.hashes);
		setAsOf(SAMPLE.asOf);
		setUseScores(true);
		setVisual(SAMPLE.visual);
		setText(SAMPLE.text);
		setMetadata(SAMPLE.metadata);
		setResult(null);
		setError(null);
	};

	const run = async (event: React.FormEvent) => {
		event.preventDefault();
		setError(null);
		setResult(null);
		let body: ClaimSignalsRequest;
		try {
			const timeline = parseTimeline(incidentTime, filingTime, timelineEvents);
			body = {
				events: parseEvents(events),
				entities: parseEntities(entities),
				prior_findings: parseHistory(history),
				identities: parseIdentities(identities),
				...(timeline ? { timeline } : {}),
				hashes: parseHashes(hashes),
				as_of: seconds(asOf, "Measure history as of"),
				...(useScores ? { modality_scores: { visual, text, metadata } } : {}),
			};
		} catch (caught) {
			if (caught instanceof RowError) {
				setError(caught.message);
				return;
			}
			throw caught;
		}
		setRunning(true);
		try {
			setResult(
				await request<Signals>("/api/claims/signals", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify(body),
				}),
			);
		} catch (caught) {
			setError((caught as ApiError).message);
		} finally {
			setRunning(false);
		}
	};

	return (
		<Page>
			<PageTitle
				title="Claim signals"
				lede="Look across a claim’s activity for timing bursts, impossible travel, shared identifiers, synthetic identities, timeline causality and duplicate hashes. Fill in what you have. Empty sections are skipped."
				actions={<button type="button" className="btn-quiet" onClick={loadSample}>Load sample data</button>}
			/>
			<form onSubmit={run} className="grid gap-6">
				<div className="grid gap-6 lg:grid-cols-2">
					<Rows id="events" title="Claim events" hint="One per line. Location and device are optional." header={EVENT_HEADER} value={events} onChange={setEvents} />
					<Rows id="entities" title="Parties" hint="One per line, with any identifiers they hold." header={ENTITY_HEADER} value={entities} onChange={setEntities} />
					<div>
						<Rows id="history" title="Past findings" hint="See how much an old finding still counts." header={HISTORY_HEADER} value={history} onChange={setHistory} />
						<label className="mt-2 flex items-center gap-3">
							<span>Measure as of</span>
							<input type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} className="field !w-auto" />
						</label>
					</div>
					<fieldset>
						<legend className="font-bold">Signal conflict</legend>
						<label className="mt-1 flex min-h-11 items-center gap-3">
							<input type="checkbox" checked={useScores} onChange={(event) => setUseScores(event.target.checked)} className="h-5 w-5 accent-[var(--uv)]" />
							Compare scores for this claim
						</label>
						{useScores && (
							<div className="mt-1 grid gap-1">
								<Slider label="Visual" value={visual} onChange={setVisual} />
								<Slider label="Text" value={text} onChange={setText} />
								<Slider label="Metadata" value={metadata} onChange={setMetadata} />
							</div>
						)}
					</fieldset>
					<Rows id="identities" title="Identity profiles" hint="Check email randomness, disposable domains and carrier risk." header={IDENTITY_HEADER} value={identities} onChange={setIdentities} />
					<Rows id="hashes" title="Document hashes" hint="Detect reused or near-duplicate document hashes across parties." header={HASH_HEADER} value={hashes} onChange={setHashes} />
					<div className="lg:col-span-2">
						<Rows id="timeline" title="Incident timeline audit" hint="Check photo capture and invoice timestamps against the incident and filing dates." header={TIMELINE_HEADER} value={timelineEvents} onChange={setTimelineEvents} />
						<div className="mt-2 flex flex-wrap gap-4">
							<label className="flex items-center gap-2">
								<span>Incident time</span>
								<input type="text" placeholder="2026-03-12T08:00:00Z" value={incidentTime} onChange={(event) => setIncidentTime(event.target.value)} className="field !w-56 font-data text-sm" />
							</label>
							<label className="flex items-center gap-2">
								<span>Filing time (optional)</span>
								<input type="text" placeholder="2026-03-12T10:00:00Z" value={filingTime} onChange={(event) => setFilingTime(event.target.value)} className="field !w-56 font-data text-sm" />
							</label>
						</div>
					</div>
				</div>
				{error && <Notice tone="error" title="The checks didn’t run">{error}</Notice>}
				{state === "offline" && <Notice tone="warn" title="The engine isn’t responding">It may be restarting. This page checks again every 30 seconds.</Notice>}
				<div>
					<button type="submit" className="btn-primary" disabled={empty || running}>
						{running ? "Running checks…" : "Run checks"}
					</button>
				</div>
			</form>
			{result && <div className="mt-8"><Results data={result} /></div>}
		</Page>
	);
};

export default ClaimSignals;
