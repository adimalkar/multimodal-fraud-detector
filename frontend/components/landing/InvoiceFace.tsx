const LINES = [
	["Rear bumper, supply and fit", "1,180.00"],
	["Paint and finish", "860.00"],
	["Labour, 11 hours", "1,200.00"],
];

/**
 * One face of the fictional sample invoice. The paper and UV faces share this
 * layout so that everything lines up under the lens. On the UV face, Read draws
 * the dashed box an OCR pass puts around a word, with its read confidence.
 */
const InvoiceFace = ({ uv = false }: { uv?: boolean }) => {
	const Read = ({ children, conf }: { children: React.ReactNode; conf: number }) =>
		uv ? (
			<span className="relative inline-block outline-dashed outline-[0.16cqw] outline-offset-[0.5cqw] outline-fluoro/60">
				{children}
				<span className="absolute -top-[2.5cqw] right-0 font-data text-[1.5cqw] leading-none text-fluoro">{conf}%</span>
			</span>
		) : (
			<>{children}</>
		);

	return (
		<div
			aria-hidden="true"
			style={
				uv
					? {
							backgroundImage:
								"linear-gradient(rgba(168,255,230,.09) 1px, transparent 1px), linear-gradient(90deg, rgba(168,255,230,.09) 1px, transparent 1px)",
							backgroundSize: "5cqw 5cqw",
						}
					: undefined
			}
			className={`absolute inset-0 flex flex-col px-[6cqw] py-[5cqw] font-data text-[2.45cqw] leading-[1.45] ${
				uv ? "bg-uv-field text-[#e0ddff]" : "bg-paper text-carbon"
			}`}
		>
			<div className="flex items-start justify-between gap-[3cqw]">
				<div>
					<p className="font-display text-[5cqw] font-bold leading-none [font-stretch:80%]">
						<Read conf={98}>Harbour Road Auto Body</Read>
					</p>
					<p className={`mt-[1.2cqw] ${uv ? "" : "text-graphite"}`}>14 Harbour Road, Sample Town</p>
				</div>
				<div data-exhibit="C" className="text-right">
					{uv ? (
						<p className="max-w-[38cqw] text-[2.15cqw] leading-[1.4] text-fluoro">
							Last saved by: image editor
							<br />
							Created 14 Mar 2026
						</p>
					) : (
						<p>
							<span className="block font-display text-[3.8cqw] font-bold leading-none [font-stretch:80%]">Invoice</span>
							No. 20418
						</p>
					)}
				</div>
			</div>

			<div className={`mt-[4.5cqw] flex justify-between border-b pb-[1cqw] ${uv ? "border-[#e0ddff]/40" : "border-carbon"}`}>
				<span><Read conf={94}>Claim ref. CL-88213</Read></span>
				<span><Read conf={97}>12 Mar 2026</Read></span>
			</div>

			<div className="mt-[1.8cqw]">
				{LINES.map(([item, cost], index) => (
					<div key={item} className="flex justify-between py-[1cqw]">
						<span>{item}</span>
						<span><Read conf={97 - index}>{cost}</Read></span>
					</div>
				))}
			</div>

			<div className="ml-auto mt-[2.4cqw] w-[54%]">
				<div className="flex justify-between py-[0.8cqw]">
					<span>Subtotal</span>
					<span><Read conf={96}>3,240.00</Read></span>
				</div>
				<div className="flex justify-between py-[0.8cqw]">
					<span>Tax 8%</span>
					<span><Read conf={95}>259.20</Read></span>
				</div>
				<div data-exhibit="A">
				<div
					className={`mt-[0.8cqw] flex justify-between border-t py-[1cqw] font-bold ${uv ? "border-fluoro text-fluoro" : "border-carbon"}`}
				>
					<span>Total due</span>
					<span><Read conf={91}>3,699.20</Read></span>
				</div>
				{uv ? (
					<p className="mt-[0.6cqw] text-right text-[2.15cqw] leading-[1.35] text-fluoro">
						3,240.00 + 259.20 = 3,499.20
						<br />
						Off by 200.00
					</p>
				) : (
					<p className="mt-[0.6cqw] text-right text-[2.15cqw] leading-[1.35] text-graphite">Payment due in 30 days</p>
				)}
				</div>
			</div>

			<div className="mt-auto flex items-end justify-between gap-[3cqw]">
				<div data-exhibit="B" className="w-[40%]">
					<svg viewBox="0 0 200 60" className={`h-[8cqw] w-auto ${uv ? "text-fluoro" : "text-carbon"}`}>
						<path
							d="M6 42c18-34 30-38 34-28s-14 34-8 34 26-34 34-30-8 26 0 26 24-22 34-20-2 18 8 16 30-16 84-18"
							fill="none"
							stroke="currentColor"
							strokeWidth="2.4"
							strokeLinecap="round"
						/>
					</svg>
					<p className={`border-t pt-[0.6cqw] text-[2cqw] ${uv ? "border-[#e0ddff]/40" : "border-carbon text-graphite"}`}>
						Authorised signature
					</p>
				</div>
				{uv && (
					<p className="w-[52%] text-[2.15cqw] leading-[1.4] text-fluoro">
						Signature covers revision 1 of 2.
						<br />
						Revision 2 was saved afterwards.
					</p>
				)}
			</div>
		</div>
	);
};

export default InvoiceFace;
