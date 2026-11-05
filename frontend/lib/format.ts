/**
 * Plain-language labels for engine values. The engine's internal names sound
 * like decisions ("CRITICAL_FRAUD", "APPROVE_AUTOMATICALLY"). A screening score
 * is not a decision, so the interface never repeats them.
 */

export type TierKey = "low" | "elevated" | "high" | "critical" | "none";

const TIERS: Record<string, { key: TierKey; label: string }> = {
	LOW_RISK: { key: "low", label: "Low score" },
	SUSPICIOUS: { key: "elevated", label: "Elevated score" },
	HIGH_RISK: { key: "high", label: "High score" },
	CRITICAL_FRAUD: { key: "critical", label: "Very high score" },
};

export const tierOf = (tier?: string | null) => (tier && TIERS[tier]) || { key: "none" as TierKey, label: "Not scored" };

export const TIER_BG: Record<TierKey, string> = {
	low: "bg-tier-low",
	elevated: "bg-tier-elevated",
	high: "bg-tier-high",
	critical: "bg-tier-critical",
	none: "bg-graphite",
};

const ACTIONS: Record<string, string> = {
	BLOCK_TRANSACTION_AND_ALERT_SECURITY: "Hold the claim and alert your investigation unit",
	ESCALATE_TO_SENIOR_ANALYST_QUEUE: "Escalate to a senior analyst",
	REQUIRE_STEP_UP_MFA_AUTHENTICATION: "Ask the claimant for more evidence",
	APPROVE_AUTOMATICALLY: "Low priority for review",
	MANUAL_REVIEW: "Review manually",
};

export const actionLabel = (action?: string | null) => (action && ACTIONS[action]) || "Review manually";

export const percent = (value?: number | null, digits = 0) =>
	value === null || value === undefined ? "–" : `${(value * 100).toFixed(digits)}%`;

export const score100 = (value?: number | null) =>
	value === null || value === undefined ? "–" : (value * 100).toFixed(0);

export const bytes = (size: number) =>
	size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`;

export const titleCase = (value: string) =>
	value.replace(/_/g, " ").replace(/^\w/, (letter) => letter.toUpperCase());

export const dateTime = (value?: string | null) => {
	if (!value) return "–";
	const date = new Date(value.includes("T") ? value : `${value.replace(" ", "T")}Z`);
	return Number.isNaN(date.getTime())
		? value
		: date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
};
