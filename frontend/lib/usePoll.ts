"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, request } from "./api";

const INTERVAL_MS = 2000;
const MAX_TRANSIENT_FAILURES = 5;

/** Poll a job until it finishes. Stops on unmount, on a final state, and on errors that retrying cannot fix. */
export const usePoll = <T extends { status: string }>(path: string) => {
	const [data, setData] = useState<T | null>(null);
	const [error, setError] = useState<ApiError | null>(null);
	const failures = useRef(0);

	useEffect(() => {
		let stopped = false;
		let timer: ReturnType<typeof setTimeout>;
		failures.current = 0;

		const tick = async () => {
			try {
				const next = await request<T>(path);
				if (stopped) return;
				failures.current = 0;
				setError(null);
				setData(next);
				if (next.status === "completed" || next.status === "failed") return;
			} catch (caught) {
				if (stopped) return;
				const failure = caught as ApiError;
				const retryable = failure.status === 0 || failure.status >= 500 || failure.status === 429;
				failures.current += 1;
				if (!retryable || failures.current >= MAX_TRANSIENT_FAILURES) {
					setError(failure);
					return;
				}
			}
			timer = setTimeout(tick, INTERVAL_MS);
		};

		tick();
		return () => {
			stopped = true;
			clearTimeout(timer);
		};
	}, [path]);

	return { data, error };
};
