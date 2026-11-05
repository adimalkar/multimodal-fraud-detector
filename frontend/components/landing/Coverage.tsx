type Cell = "on" | "opt" | "no" | null;

const ROWS: Array<{ check: string; cells: [Cell, Cell, Cell] }> = [
	{ check: "Visual screening by a vision model", cells: ["on", "on", "on"] },
	{ check: "File metadata", cells: ["on", "on", "on"] },
	{ check: "Content Credentials (C2PA)", cells: ["opt", null, null] },
	{ check: "File and stream structure", cells: [null, "opt", "opt"] },
	{ check: "Digital signatures and later revisions", cells: [null, "opt", null] },
	{ check: "OCR with page and word citations", cells: [null, "opt", null] },
	{ check: "Invoice arithmetic", cells: [null, "opt", null] },
	{ check: "Timestamped scene sampling", cells: [null, null, "opt"] },
	{ check: "Pixel-level generated or edited image detection", cells: ["no", null, null] },
	{ check: "Generated video and face manipulation detection", cells: [null, null, "no"] },
];

const KEY = {
	on: { label: "On", className: "bg-uv text-paper" },
	opt: { label: "Opt-in", className: "border border-uv text-uv" },
	no: { label: "Not yet", className: "border border-dashed border-graphite text-graphite" },
};

const Coverage = () => (
	<section id="coverage" className="border-t border-rule bg-paper py-16 md:py-24">
		<div className="wrap">
			<h2 className="display max-w-3xl text-5xl md:text-7xl">What it checks, and what it doesn’t</h2>
			<p className="mt-5 max-w-2xl text-lg leading-relaxed text-graphite">
				Knowing what wasn’t examined matters as much as what was. Opt-in checks run on a private deployment with the
				worker and storage they need.
			</p>
			<div className="relative mt-10">
				<table className="w-full border-collapse text-left">
					<caption className="sr-only">Checks available for each type of evidence</caption>
					<thead>
						<tr className="border-b-2 border-carbon">
							<th scope="col" className="label py-2 pr-4 font-normal">Check</th>
							{["Photo", "PDF", "Video"].map((kind) => (
								<th key={kind} scope="col" className="label w-[3.75rem] py-2 text-center font-normal md:w-24">{kind}</th>
							))}
						</tr>
					</thead>
					<tbody>
						{ROWS.map((row) => (
							<tr key={row.check} className="border-b border-rule">
								<th scope="row" className="py-3 pr-3 font-normal leading-snug">{row.check}</th>
								{row.cells.map((cell, index) => (
									<td key={index} className="py-3 text-center">
										{cell ? (
											<span className={`inline-block whitespace-nowrap px-1 py-0.5 font-data text-[0.6875rem] md:min-w-[4.25rem] md:px-2 md:text-xs ${KEY[cell].className}`}>
												{KEY[cell].label}
											</span>
										) : (
											<span className="text-graphite"><span className="sr-only">Does not apply</span><span aria-hidden="true">·</span></span>
										)}
									</td>
								))}
							</tr>
						))}
					</tbody>
				</table>
			</div>
		</div>
	</section>
);

export default Coverage;
