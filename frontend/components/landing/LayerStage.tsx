"use client";

import { motion, type MotionValue, useMotionValueEvent, useReducedMotion, useScroll, useTransform } from "framer-motion";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import StaticStack from "./StaticStack";

const EvidenceScene = dynamic(() => import("./three/EvidenceScene"), { ssr: false });

const CHAPTERS = [
	{ title: "Pixels", body: "A vision model looks for visual inconsistencies in photos, pages and sampled video frames.", from: 0.2, to: 0.36 },
	{ title: "Text", body: "OCR reads each word with its position and confidence, then checks that invoice totals add up.", tag: "Opt-in", from: 0.36, to: 0.52 },
	{ title: "Metadata", body: "Camera, software and creation tags come straight from the file.", from: 0.52, to: 0.68 },
	{ title: "Signatures", body: "Signatures and later revisions show whether a PDF changed after it was signed.", tag: "Opt-in", from: 0.68, to: 0.82 },
];

const Chapter = ({ chapter, progress }: { chapter: (typeof CHAPTERS)[number]; progress: MotionValue<number> }) => {
	const { from, to } = chapter;
	const opacity = useTransform(progress, [from, from + 0.03, to - 0.03, to], [0, 1, 1, 0]);
	const y = useTransform(progress, [from, from + 0.03, to - 0.03, to], [24, 0, 0, -24]);
	return (
		<motion.div style={{ opacity, y }} className="absolute inset-x-0 top-0">
			<h3 className="display text-5xl md:text-7xl">{chapter.title}</h3>
			<p className="mt-4 max-w-sm text-lg leading-relaxed text-muted">{chapter.body}</p>
			{chapter.tag && <p className="label mt-3 text-uv">{chapter.tag}</p>}
		</motion.div>
	);
};

const webglAvailable = () => {
	try {
		const canvas = document.createElement("canvas");
		return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
	} catch {
		return false;
	}
};

/**
 * One pinned scene: the file floats beside the headline, then comes apart into
 * the layers FraudSight reads as you scroll. The object is the explanation.
 */
const LayerStage = () => {
	const stage = useRef<HTMLElement>(null);
	const reduced = useReducedMotion() ?? false;
	const [webgl, setWebgl] = useState(false);
	const [visible, setVisible] = useState(true);
	const { scrollYProgress } = useScroll({ target: stage, offset: ["start start", "end end"] });
	const heroOpacity = useTransform(scrollYProgress, [0, 0.12], [1, 0]);
	const heroY = useTransform(scrollYProgress, [0, 0.12], [0, -40]);
	const closingOpacity = useTransform(scrollYProgress, [0.84, 0.9], [0, 1]);
	const [closingShown, setClosingShown] = useState(false);

	useMotionValueEvent(scrollYProgress, "change", (value) => setClosingShown(value > 0.84));
	useEffect(() => setWebgl(webglAvailable()), []);
	useEffect(() => {
		if (!stage.current) return;
		const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting));
		observer.observe(stage.current);
		return () => observer.disconnect();
	}, []);

	return (
		<section ref={stage} aria-label="How FraudSight reads a file" className="relative h-[520vh]">
			<div className="sticky top-0 h-screen overflow-hidden">
				<div aria-hidden="true" className="absolute inset-0 bg-[radial-gradient(60%_60%_at_70%_45%,rgba(154,140,255,.14),transparent_70%)]" />
				<div className="absolute inset-0">
					{webgl ? <EvidenceScene progress={scrollYProgress} still={reduced} active={visible} /> : <StaticStack />}
				</div>

				<div className="wrap pointer-events-none relative flex h-full flex-col justify-end pb-[9vh] lg:justify-center lg:pb-0">
					<motion.div style={{ opacity: heroOpacity, y: heroY }} className="pointer-events-auto max-w-[32rem]">
						<h1 className="display text-[clamp(3rem,7vw,5.75rem)]">Every file has layers</h1>
						<p className="mt-6 max-w-md text-lg leading-relaxed text-muted">
							FraudSight screens the photos, PDFs and video attached to a claim, and shows what it found, what it
							couldn’t check, and why. You make the call.
						</p>
						<div className="mt-8 flex flex-wrap gap-3">
							<Link href="/analyze" className="btn-primary">Screen a file</Link>
							<a href="#coverage" className="btn-quiet">See what it checks</a>
						</div>
					</motion.div>
				</div>

				<div className="pointer-events-none absolute inset-0">
					<div className="wrap relative h-full">
						<div className="absolute bottom-[10vh] left-5 right-5 h-52 md:left-8 md:right-auto md:w-[28rem] lg:bottom-auto lg:top-[38vh]">
							{CHAPTERS.map((chapter) => <Chapter key={chapter.title} chapter={chapter} progress={scrollYProgress} />)}
							<motion.div style={{ opacity: closingOpacity }} className={`absolute inset-x-0 top-0 ${closingShown ? "pointer-events-auto" : ""}`}>
								<h3 className="display text-5xl md:text-7xl">Then you decide</h3>
								<p className="mt-4 max-w-sm text-lg leading-relaxed text-muted">The report shows the evidence. The call stays with your team.</p>
							</motion.div>
						</div>
					</div>
				</div>
				<p className="label pointer-events-none absolute bottom-5 right-5 md:right-8">Sample invoice is fictional</p>
			</div>
		</section>
	);
};

export default LayerStage;
