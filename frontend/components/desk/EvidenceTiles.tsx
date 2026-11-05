const PhotoArt = () => (
	<div aria-hidden="true" className="scanline relative h-full overflow-hidden bg-gradient-to-b from-[#232838] to-[#12141c]">
		<svg viewBox="0 0 320 170" className="absolute inset-0 h-full w-full" preserveAspectRatio="xMidYMid meet" fill="none">
			<path d="M0 138h320" stroke="#3a4050" />
			<path d="M58 124c-4-24 8-30 34-34l34-30c6-5 13-8 22-8h48c9 0 16 3 22 9l26 29c24 3 40 9 42 34H58Z" fill="#a9b2c4" />
			<path d="m128 90 26-23c3-3 7-4 11-4h17v27h-54Zm62 0V63h13c5 0 8 1 11 4l21 23h-45Z" fill="#232838" />
			<circle cx="108" cy="126" r="19" fill="#0d0f15" stroke="#3a4050" strokeWidth="5" />
			<circle cx="228" cy="126" r="19" fill="#0d0f15" stroke="#3a4050" strokeWidth="5" />
			<rect x="238" y="82" width="58" height="42" rx="2" stroke="#ffcb1f" strokeWidth="1.6" />
		</svg>
		<span className="absolute left-2 top-2 rounded bg-canvas/80 px-1.5 py-0.5 font-data text-[0.625rem] text-muted">GPS · camera · software</span>
	</div>
);

const PdfArt = () => (
	<div aria-hidden="true" className="relative flex h-full items-end justify-center overflow-hidden bg-gradient-to-b from-[#1c1a38] to-[#12141c]">
		<div className="relative flex h-[92%] w-[62%] flex-col rounded-t-md bg-[#eef0f4] p-3 font-data text-[0.5625rem] leading-[1.7] text-[#14161b]">
			<p className="text-[0.6875rem] font-semibold">Invoice 20418</p>
			<div className="mt-1 h-px bg-[#14161b]" />
			<div className="mt-1 flex justify-between"><span>Subtotal</span><span className="outline-dashed outline-1 outline-offset-1 outline-[#0f9d80]">3,240.00</span></div>
			<div className="mt-1 flex justify-between"><span>Tax 8%</span><span className="outline-dashed outline-1 outline-offset-1 outline-[#0f9d80]">259.20</span></div>
			<div className="mt-1.5 flex justify-between rounded-sm bg-marker/50 px-0.5 font-bold outline outline-1 outline-marker"><span>Total</span><span>3,699.20</span></div>
			<p className="mt-1 text-right font-bold text-[#a3123a]">Off by 200.00</p>
			<div className="mt-auto hidden pt-2 [@media(min-height:560px)]:block">
				<svg viewBox="0 0 200 60" className="h-7 w-auto" fill="none"><path d="M6 42c18-34 30-38 34-28s-14 34-8 34 26-34 34-30-8 26 0 26 24-22 34-20-2 18 8 16 30-16 84-18" stroke="#14161b" strokeWidth="3" strokeLinecap="round" /></svg>
				<div className="h-px w-1/2 bg-[#14161b]" />
				<p className="text-[#59616e]">Authorised signature</p>
			</div>
		</div>
	</div>
);

const VideoArt = () => (
	<div aria-hidden="true" className="relative flex h-full flex-col justify-center gap-3 overflow-hidden py-3 bg-gradient-to-b from-[#142a2a] to-[#12141c] px-3">
		<div className="grid flex-1 grid-cols-3 content-center gap-1.5">
			{["00:02", "00:07", "00:12"].map((time, index) => (
				<div key={time} className="overflow-hidden rounded border border-line bg-canvas">
					<div className="aspect-[4/3]" style={{ background: `linear-gradient(${110 + index * 30}deg,#2a3a4a,#7d8aa0 ${40 + index * 12}%,#1a1f28)` }} />
					<p className="py-0.5 text-center font-data text-[0.625rem] text-muted">{time}</p>
				</div>
			))}
		</div>
		<div className="relative h-1 shrink-0 rounded-full bg-line">
			<span className="absolute left-[14%] top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full bg-fluoro" />
			<span className="absolute left-[47%] top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full bg-fluoro" />
			<span className="absolute left-[80%] top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full bg-fluoro" />
		</div>
	</div>
);

const TILES = [
	{ title: "Photos", formats: "JPG, PNG, WebP", art: PhotoArt, checks: ["Visual screening", "Camera, GPS and software tags"], optIn: "Content Credentials" },
	{ title: "PDFs", formats: "Up to 3 pages screened", art: PdfArt, checks: ["Visual screening", "Creator and software tags"], optIn: "Signatures, OCR, invoice sums" },
	{ title: "Video", formats: "MP4, MOV, AVI, MKV, WebM", art: VideoArt, checks: ["3 sampled frames screened", "File metadata"], optIn: "Scene sampling" },
];

/** Shows what each kind of evidence gets, before anything is uploaded. */
const EvidenceTiles = ({ onPick, lifted }: { onPick: () => void; lifted: boolean }) => (
	<div className="grid flex-1 gap-3 md:grid-cols-3">
		{TILES.map((tile, index) => {
			const Art = tile.art;
			return (
				<button
					key={tile.title}
					type="button"
					onClick={onPick}
					aria-label={`Add ${tile.title.toLowerCase()}`}
					style={{ transitionDelay: `${index * 40}ms` }}
					className={`group flex flex-col overflow-hidden rounded-2xl border bg-canvas text-left transition duration-300 hover:-translate-y-1 hover:border-muted ${lifted ? "-translate-y-1 border-uv" : "border-line"}`}
				>
					<div className="relative min-h-44 flex-1"><div className="absolute inset-0"><Art /></div></div>
					<div className="p-4">
						<div className="flex items-baseline justify-between gap-2">
							<h2 className="text-lg font-medium">{tile.title}</h2>
							<span className="text-right font-data text-[0.6875rem] text-muted">{tile.formats}</span>
						</div>
						<ul className="mt-2 grid gap-1 text-sm">
							{tile.checks.map((check) => (
								<li key={check} className="flex items-center gap-2 text-ink">
									<span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-uv" />
									{check}
								</li>
							))}
							<li className="flex items-center gap-2 text-muted">
								<span aria-hidden="true" className="h-1.5 w-1.5 rounded-full border border-uv" />
								{tile.optIn} (opt-in)
							</li>
						</ul>
					</div>
				</button>
			);
		})}
	</div>
);

export default EvidenceTiles;
