import Link from "next/link";

const RULES = [
	{ title: "It won’t decide a claim", body: "Every result ends in human review. Nothing is approved, denied or blocked on its own." },
	{ title: "A score isn’t a probability", body: "Scores are uncalibrated heuristics for sorting a queue. They haven’t been measured against held-out fraud data." },
	{ title: "Missing data isn’t guilt", body: "An absent EXIF tag, an unsigned PDF or a low frame rate is a gap in the record, not evidence of fraud." },
];

const Closing = () => (
	<section id="limits" className="border-t border-line py-20 md:py-32">
		<div className="wrap">
			<h2 className="display max-w-3xl text-5xl md:text-7xl">Three things it will never tell you</h2>
			<dl className="mt-12 grid gap-8 md:grid-cols-3 md:gap-10">
				{RULES.map((rule) => (
					<div key={rule.title} className="border-t border-line pt-5">
						<dt className="text-lg font-medium">{rule.title}</dt>
						<dd className="mt-2 leading-relaxed text-muted">{rule.body}</dd>
					</div>
				))}
			</dl>
			<div className="mt-20 flex flex-col items-start gap-5 md:mt-28">
				<p className="display max-w-2xl text-4xl md:text-5xl">Start with a file from a closed claim, and compare notes.</p>
				<Link href="/analyze" className="btn-primary">Screen a file</Link>
			</div>
		</div>
	</section>
);

export default Closing;
