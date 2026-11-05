const STEPS = [
	{ handler: "Intake", did: "Checks the file type and size, then gives the file a job number." },
	{ handler: "Metadata reader", did: "Pulls camera, GPS, software and document tags from the file." },
	{ handler: "Vision model", did: "Makes one capped request. Video is sampled into frames first." },
	{ handler: "Evidence checks", did: "Where enabled: Content Credentials, PDF structure, signatures, OCR, invoice arithmetic and video structure. These make no model calls." },
	{ handler: "Scorer", did: "Adds up a provisional score and records the reasons behind it." },
];

const Custody = () => (
	<section id="steps" className="border-t border-rule py-16 md:py-24">
		<div className="wrap">
			<div className="grid gap-4 md:grid-cols-[1fr_1.1fr] md:items-end">
				<h2 className="display text-5xl md:text-7xl">What happens to a file, in order</h2>
				<p className="max-w-lg text-lg leading-relaxed text-graphite">
					Every file follows the same steps, and the report shows what came of them. The last step always belongs to
					a person.
				</p>
			</div>
			<ol className="sheet mt-10">
				{STEPS.map((step, index) => (
					<li key={step.handler} className="grid gap-1 border-b border-rule px-4 py-4 md:grid-cols-[3rem_13rem_1fr] md:items-baseline md:gap-4 md:px-6">
						<span className="font-data text-sm text-uv">{String(index + 1).padStart(2, "0")}</span>
						<span className="font-data text-[0.9375rem] font-bold text-uv">{step.handler}</span>
						<span className="leading-snug">{step.did}</span>
					</li>
				))}
				<li className="grid gap-1 bg-lightbox/40 px-4 py-5 md:grid-cols-[3rem_13rem_1fr] md:items-end md:gap-4 md:px-6">
					<span className="font-data text-sm">{String(STEPS.length + 1).padStart(2, "0")}</span>
					<span className="font-bold">Your reviewer</span>
					<span className="flex flex-wrap items-end gap-x-4 gap-y-3">
						<span>Opens the original, weighs the findings, decides.</span>
						<span aria-hidden="true" className="h-6 min-w-40 flex-1 border-b-2 border-carbon" />
					</span>
				</li>
			</ol>
		</div>
	</section>
);

export default Custody;
