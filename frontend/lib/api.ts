/** Typed client for the FraudSight FastAPI engine. */

export const API_URL = (
	process.env.NEXT_PUBLIC_API_URL || "https://multimodal-fraud-detector-1.onrender.com"
).replace(/\/$/, "");

const TOKEN_KEY = "fraudsight.accessToken";

export const getAccessToken = (): string => {
	try {
		return sessionStorage.getItem(TOKEN_KEY) ?? "";
	} catch {
		return "";
	}
};

export const setAccessToken = (token: string) => {
	try {
		if (token) sessionStorage.setItem(TOKEN_KEY, token);
		else sessionStorage.removeItem(TOKEN_KEY);
	} catch {
		/* Storage can be blocked. The token then lasts only for this request. */
	}
};

export class ApiError extends Error {
	constructor(
		message: string,
		readonly status: number,
	) {
		super(message);
		this.name = "ApiError";
	}
}

const detailMessage = (detail: unknown): string | null => {
	if (typeof detail === "string") return detail;
	if (Array.isArray(detail)) {
		const first = detail[0] as { loc?: unknown[]; msg?: string } | undefined;
		if (first?.msg) {
			const where = (first.loc ?? []).filter((part) => part !== "body").join(" › ");
			return where ? `${where}: ${first.msg}` : first.msg;
		}
	}
	if (detail && typeof detail === "object" && "message" in detail) {
		return String((detail as { message: unknown }).message);
	}
	return null;
};

const fallbackMessage = (status: number): string => {
	if (status === 401) return "This engine needs an access token. Add it under Engine status.";
	if (status === 429) return "Too many requests. Wait a minute, then try again.";
	if (status >= 500) return "The engine could not complete this request. Try again shortly.";
	return `The engine rejected this request (HTTP ${status}).`;
};

export const request = async <T>(path: string, init: RequestInit = {}): Promise<T> => {
	const token = getAccessToken();
	const headers = new Headers(init.headers);
	if (token) headers.set("Authorization", `Bearer ${token}`);

	let response: Response;
	try {
		response = await fetch(`${API_URL}${path}`, { ...init, headers });
	} catch {
		throw new ApiError("Could not reach the engine. Check your connection and try again.", 0);
	}
	if (!response.ok) {
		const body = await response.json().catch(() => null);
		throw new ApiError(
			detailMessage(body?.detail) ?? fallbackMessage(response.status),
			response.status,
		);
	}
	return response.json() as Promise<T>;
};

export const downloadFile = async (path: string, filename: string) => {
	const token = getAccessToken();
	const response = await fetch(`${API_URL}${path}`, {
		headers: token ? { Authorization: `Bearer ${token}` } : {},
	}).catch(() => null);
	if (!response?.ok) throw new ApiError("The export could not be downloaded. Try again.", response?.status ?? 0);
	saveBlob(await response.blob(), filename);
};

export const saveBlob = (blob: Blob, filename: string) => {
	const url = URL.createObjectURL(blob);
	const link = document.createElement("a");
	link.href = url;
	link.download = filename;
	link.click();
	URL.revokeObjectURL(url);
};

/* ---------- Contract ---------- */

export type JobStatus = "queued" | "pending" | "processing" | "completed" | "failed";

export interface RiskBreakdown {
	visual_contribution?: number;
	text_contribution?: number;
	metadata_contribution?: number;
	synergy_multiplier?: number;
}

export interface MultimodalRisk {
	/** null when nothing could score the file, for example an unreadable model answer. */
	risk_score: number | null;
	severity_tier: string | null;
	recommended_action: string;
	cross_modal_synergy_applied?: boolean;
	breakdown?: RiskBreakdown;
	metadata?: Record<string, unknown>;
	metadata_flags?: string[];
	metadata_flags_count?: number;
}

export interface TaskResult {
	task: string;
	status: string;
	finding?: string;
	state?: string;
	evidence?: unknown;
	coverage?: Record<string, unknown>;
	limitations?: string | string[];
	calibrated_score?: number | null;
}

export interface ProvenanceCheck {
	check: "content_credentials" | "embedded_tags" | "generator_metadata" | "visible_watermark" | string;
	state: string;
	signer?: string | null;
	ai_declared?: boolean;
	trust_list_configured?: boolean;
	reason?: string;
}

export interface Provenance {
	checks: ProvenanceCheck[];
	findings: Array<{ kind: string; strength: "strong" | "moderate"; summary: string; source: string }>;
	decisive: boolean;
	error?: string;
}

export interface ScreeningResult {
	classification: string;
	consensus?: string;
	visible_watermark?: string;
	provenance?: Provenance;
	confidence: number;
	reason?: string;
	vision_findings?: string;
	calibration?: string;
	risk_calibration?: string;
	needs_review?: boolean;
	elapsed_seconds?: number;
	media_type?: string;
	pipeline_version?: string;
	decision?: string;
	model_usage?: { cost?: number; calls?: number; [key: string]: unknown };
	votes?: Array<{ model: string; vote: string; conf: number }>;
	multimodal_risk?: MultimodalRisk;
	task_results?: TaskResult[];
}

export interface JobState {
	job_id: string;
	status: JobStatus;
	progress?: number;
	stage?: string;
	elapsed_seconds?: number;
	filename?: string;
	media_type?: string;
	pipeline_version?: string;
	artifact_sha256?: string;
	result: ScreeningResult | null;
	error: string | null;
}

export interface BatchItem {
	item_id: number;
	filename: string;
	media_type: string;
	status: JobStatus;
	result: ScreeningResult | null;
	error: string | null;
}

export interface BatchState {
	batch_id: string;
	status: JobStatus;
	stage: string;
	total_items: number;
	completed_items: number;
	progress: number;
	elapsed_seconds: number;
	summary: { total: number; processed: number; error_count: number };
	error: string | null;
	items: BatchItem[];
}

export interface Health {
	status: string;
	providers_configured: boolean;
	storage_configured: boolean;
	job_backend?: string;
	auth_configured?: boolean;
	worker_available?: boolean;
}

export interface Evaluation {
	id: number;
	filename: string;
	media_type: string;
	ai_prediction: string | null;
	confidence: number | null;
	risk_score?: number | null;
	severity_tier?: string | null;
	recommended_action?: string | null;
	final_reasoning: string | null;
	processing_time: number | null;
	processed_at: string | null;
}

export interface AnalyticsSummary {
	total_records: number;
	processed_records: number;
	flagged_rate_percentage: number;
	avg_processing_time_sec: number;
	database_engine?: string;
	media_counts: { images: number; documents: number; videos: number };
	severity_breakdown?: {
		critical_fraud: number;
		high_risk: number;
		suspicious: number;
		low_risk: number;
	};
	recent_evaluations: Evaluation[];
}

export interface ClaimEvent {
	claimant_id: string;
	timestamp: number;
	lat?: number;
	lon?: number;
	device_fingerprint?: string;
	is_vpn_or_datacenter?: boolean;
}

export interface ClaimEntity {
	entity_id: string;
	base_risk: number;
	attributes: Record<string, string>;
}

export interface ClaimSignalsRequest {
	events?: ClaimEvent[];
	entities?: ClaimEntity[];
	modality_scores?: Record<string, number>;
	prior_findings?: Array<{
		entity_id: string;
		risk_score: number;
		timestamp: number;
		clean_events_since?: number;
	}>;
	as_of?: number;
}

export interface ClaimSignals {
	persisted: boolean;
	notice: string;
	velocity:
		| null
		| Array<{
				claimant_id: string;
				events: number;
				peak_window_count: number;
				peak_rate_per_minute: number;
				velocity_multiplier: number;
				burst_flagged: boolean;
		  }>;
	travel:
		| null
		| Array<{
				user_id: string;
				geo_risk_score: number;
				severity_tier: string;
				impossible_travel_detected: boolean;
				calculated_speed_kmh: number;
				distance_km: number;
				time_delta_seconds: number;
				device_churn_detected: boolean;
				distinct_devices_count: number;
				anomaly_flags: string[];
		  }>;
	network: null | {
		rings: Array<{
			ring_id: string;
			size: number;
			entities: string[];
			shared_attributes: string[];
			max_base_risk: number;
			is_syndicate: boolean;
		}>;
		entities: Array<{
			entity_id: string;
			base_risk: number;
			propagated_risk: number;
			network_risk_boost: number;
			neighbor_count: number;
			shared_attributes: string[];
			syndicate_flagged: boolean;
		}>;
	};
	conflict: null | {
		max_divergence: number;
		conflict_detected: boolean;
		conflict_tier: string;
		conflict_penalty: number;
		linear_fused_risk: number;
		adjusted_fused_risk: number;
		divergence_pairs: Array<{
			modality_a: string;
			modality_b: string;
			score_a: number;
			score_b: number;
			divergence: number;
		}>;
	};
	history:
		| null
		| Array<{
				entity_id: string;
				original_peak_risk: number;
				decayed_risk_score: number;
				days_elapsed: number;
				half_life_days: number;
				clean_events_count: number;
				rehabilitation_complete: boolean;
		  }>;
}
