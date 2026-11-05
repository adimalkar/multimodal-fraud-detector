import Link from "next/link";

const RULES = [
	{ title: "It won’t decide a claim", body: "Every result ends in human review. Nothing is approved, denied or blocked on its own." },
	{ title: "A score isn’t a probability", body: "Scores are uncalibrated heuristics for sorting a queue. They haven’t been measured against held-out fraud data." },
	{ title: "Missing data isn’t guilt", body: "An absent EXIF tag, an unsigned PDF or a low frame rate is a gap in the record, not evidence of fraud." },
];

const Limits = () => (
	<section id="limits" className="bg-uv-field py-16 text-[#e4e2ff] md:py-24">
		<div className="wrap">
			<h2 className="display max-w-3xl text-5xl text-paper md:text-7xl">Three things it will never tell you</h2>
			<dl className="mt-10 grid gap-8 md:grid-cols-3 md:gap-10">
				{RULES.map((rule) => (
					<div key={rule.title} className="border-t border-fluoro/50 pt-4">
						<dt className="text-xl font-bold text-fluoro">{rule.title}</dt>
						<dd className="mt-2 leading-relaxed">{rule.body}</dd>
					</div>
				))}
			</dl>
			<div className="mt-14 flex flex-wrap items-center gap-x-6 gap-y-3">
				<Link href="/analyze" className="btn bg-marker text-carbon hover:bg-paper">Screen a file</Link>
				<span>Start with a file from a closed claim and compare notes.</span>
			</div>
		</div>
	</section>
);

export default Limits;
