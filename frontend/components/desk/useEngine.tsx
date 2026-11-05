"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, type Health, request } from "@/lib/api";

export type EngineState = "checking" | "waking" | "online" | "unconfigured" | "needs-token" | "offline";

interface Engine {
	state: EngineState;
	health: Health | null;
	refresh: () => void;
}

const EngineContext = createContext<Engine>({ state: "checking", health: null, refresh: () => undefined });

const WAKING_AFTER_MS = 4000;
const RECHECK_MS = 30000;

export const EngineProvider = ({ children }: { children: React.ReactNode }) => {
	const [state, setState] = useState<EngineState>("checking");
	const [health, setHealth] = useState<Health | null>(null);
	const sequence = useRef(0);

	const refresh = useCallback(async () => {
		const current = ++sequence.current;
		const waking = setTimeout(() => {
			setState((previous) => (previous === "checking" ? "waking" : previous));
		}, WAKING_AFTER_MS);
		try {
			const next = await request<Health>("/api/health");
			if (current !== sequence.current) return;
			setHealth(next);
			setState(next.providers_configured ? "online" : "unconfigured");
		} catch (error) {
			if (current !== sequence.current) return;
			setState((error as ApiError).status === 401 ? "needs-token" : "offline");
		} finally {
			clearTimeout(waking);
		}
	}, []);

	useEffect(() => {
		refresh();
		const timer = setInterval(refresh, RECHECK_MS);
		return () => clearInterval(timer);
	}, [refresh]);

	const value = useMemo(() => ({ state, health, refresh }), [state, health, refresh]);
	return <EngineContext.Provider value={value}>{children}</EngineContext.Provider>;
};

export const useEngine = () => useContext(EngineContext);
