const TONE = {
	error: "border-status-bad",
	warn: "border-status-warn",
	info: "border-line",
};

const Notice = ({
	tone = "info",
	title,
	children,
}: {
	tone?: keyof typeof TONE;
	title: string;
	children?: React.ReactNode;
}) => (
	<div role={tone === "error" ? "alert" : "status"} className={`border border-l-4 border-line bg-surface p-4 ${TONE[tone]}`}>
		<p className="font-bold">{title}</p>
		{children && <div className="mt-1 leading-snug text-ink">{children}</div>}
	</div>
);

export default Notice;
