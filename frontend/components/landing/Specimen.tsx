"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import InvoiceFace from "./InvoiceFace";

type Point = { x: number; y: number };

const EXHIBITS = [
	{
		id: "A",
		title: "The total doesn’t add up",
		body: "Subtotal and tax come to 3,499.20. The invoice says 3,699.20.",
	},
	{
		id: "B",
		title: "Changed after signing",
		body: "A new revision was saved after the signature was applied.",
	},
	{
		id: "C",
		title: "Last saved in an image editor",
		body: "The file’s metadata names editing software. A reason to look, not proof.",
	},
] as const;

const STEP = 3;
const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));
const ease = (t: number) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);

const Specimen = () => {
	const stageRef = useRef<HTMLDivElement>(null);
	const position = useRef<Point>({ x: 34, y: 42 });
	const frame = useRef(0);
	const [active, setActive] = useState<string | null>(null);

	/* Exhibits are measured from the rendered invoice, so they can't drift from what they point at. */
	const anchor = useCallback((id: string): Point => {
		const stage = stageRef.current;
		const target = stage?.querySelector(`[data-exhibit="${id}"]`);
		if (!stage || !target) return { x: 50, y: 50 };
		const box = stage.getBoundingClientRect();
		const part = target.getBoundingClientRect();
		return {
			x: ((part.left + part.width / 2 - box.left) / box.width) * 100,
			y: ((part.top + part.height / 2 - box.top) / box.height) * 100,
		};
	}, []);

	const place = useCallback(
		({ x, y }: Point) => {
			position.current = { x, y };
			stageRef.current?.style.setProperty("--x", `${x}%`);
			stageRef.current?.style.setProperty("--y", `${y}%`);
			const near = EXHIBITS.find((item) => {
				const at = anchor(item.id);
				return Math.hypot(at.x - x, at.y - y) < 12;
			});
			setActive(near?.id ?? null);
		},
		[anchor],
	);

	const glide = useCallback(
		(target: Point, duration: number, then?: () => void) => {
			cancelAnimationFrame(frame.current);
			const from = position.current;
			const start = performance.now();
			const step = (now: number) => {
				const t = Math.min(1, (now - start) / duration);
				const eased = ease(t);
				place({ x: from.x + (target.x - from.x) * eased, y: from.y + (target.y - from.y) * eased });
				if (t < 1) frame.current = requestAnimationFrame(step);
				else then?.();
			};
			frame.current = requestAnimationFrame(step);
		},
		[place],
	);

	/* On load the lens walks the exhibits once, then rests on the clearest one. */
	useEffect(() => {
		if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
			place(anchor("A"));
			return;
		}
		place(position.current);
		const timers: ReturnType<typeof setTimeout>[] = [];
		const walk = (ids: string[]) => {
			const [next, ...rest] = ids;
			if (!next) return;
			glide(anchor(next), 950, () => timers.push(setTimeout(() => walk(rest), 450)));
		};
		timers.push(setTimeout(() => walk(["C", "B", "A"]), 500));
		const cancel = frame;
		return () => {
			timers.forEach(clearTimeout);
			cancelAnimationFrame(cancel.current);
		};
	}, [anchor, glide, place]);

	const fromPointer = (event: React.PointerEvent) => {
		const box = stageRef.current?.getBoundingClientRect();
		if (!box) return;
		cancelAnimationFrame(frame.current);
		place({
			x: clamp(((event.clientX - box.left) / box.width) * 100, 0, 100),
			y: clamp(((event.clientY - box.top) / box.height) * 100, 0, 100),
		});
	};

	const onKeyDown = (event: React.KeyboardEvent) => {
		const moves: Record<string, Point> = {
			ArrowLeft: { x: -STEP, y: 0 },
			ArrowRight: { x: STEP, y: 0 },
			ArrowUp: { x: 0, y: -STEP },
			ArrowDown: { x: 0, y: STEP },
		};
		const move = moves[event.key];
		if (!move) return;
		event.preventDefault();
		cancelAnimationFrame(frame.current);
		place({
			x: clamp(position.current.x + move.x, 0, 100),
			y: clamp(position.current.y + move.y, 0, 100),
		});
	};

	return (
		<figure className="min-w-0">
			<div>
				<div
					ref={stageRef}
					className="relative aspect-[1/0.94] w-full select-none overflow-hidden border border-rule bg-paper shadow-[0_2px_0_var(--rule),0_24px_48px_-28px_rgba(18,28,43,.45)] [container-type:inline-size]"
					style={{ "--x": "34%", "--y": "42%", "--r": "25cqw" } as React.CSSProperties}
					onPointerMove={(event) => {
						if (event.pointerType === "mouse") fromPointer(event);
					}}
				>
					<InvoiceFace />
					<div style={{ clipPath: "circle(var(--r) at var(--x) var(--y))" }} className="absolute inset-0">
						<InvoiceFace uv />
					</div>
					<div
						role="slider"
						tabIndex={0}
						aria-label="Examination lens. Use the arrow keys to move it across the sample invoice."
						aria-valuetext={
							active ? `Over exhibit ${active}` : "Over the sample invoice"
						}
						aria-valuenow={0}
						onKeyDown={onKeyDown}
						onPointerDown={(event) => {
							event.currentTarget.setPointerCapture(event.pointerId);
							fromPointer(event);
						}}
						onPointerMove={(event) => {
							if (event.currentTarget.hasPointerCapture(event.pointerId)) fromPointer(event);
						}}
						className="absolute h-[calc(var(--r)*2)] w-[calc(var(--r)*2)] -translate-x-1/2 -translate-y-1/2 cursor-grab touch-none rounded-full border-[3px] border-carbon shadow-[0_0_0_1px_var(--paper),0_10px_30px_rgba(23,18,79,.35)] active:cursor-grabbing"
						style={{ left: "var(--x)", top: "var(--y)" }}
					>
						<span className="absolute left-1/2 top-[-9px] h-3.5 w-[3px] -translate-x-1/2 bg-carbon" />
						<span className="absolute bottom-[-9px] left-1/2 h-3.5 w-[3px] -translate-x-1/2 bg-carbon" />
						<span className="absolute left-[-9px] top-1/2 h-[3px] w-3.5 -translate-y-1/2 bg-carbon" />
						<span className="absolute right-[-9px] top-1/2 h-[3px] w-3.5 -translate-y-1/2 bg-carbon" />
					</div>
				</div>
				<figcaption className="label mt-3 normal-case tracking-normal">
					Fictional sample invoice. Move the lens to see what screening can read. Signature and invoice checks are opt-in.
				</figcaption>
			</div>

			<ul className="mt-4 grid gap-2 md:grid-cols-3">
				{EXHIBITS.map((item) => (
					<li key={item.id}>
						<button
							type="button"
							onClick={() => glide(anchor(item.id), 650)}
							aria-pressed={active === item.id}
							className={`h-full w-full border-l-[3px] py-2.5 pl-3 pr-2 text-left transition-colors ${
								active === item.id ? "border-uv bg-paper" : "border-rule hover:bg-paper/60"
							}`}
						>
							<span className="flex items-center gap-2">
								<span className="tag">{item.id}</span>
								<span className="font-bold leading-snug">{item.title}</span>
							</span>
							<span className="mt-1.5 block text-[0.9375rem] leading-snug text-graphite">{item.body}</span>
						</button>
					</li>
				))}
			</ul>
		</figure>
	);
};

export default Specimen;
