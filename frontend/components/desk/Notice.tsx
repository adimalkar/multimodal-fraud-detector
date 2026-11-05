const TONE = {
	error: "border-status-bad",
	warn: "border-status-warn",
	info: "border-rule",
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
	<div role={tone === "error" ? "alert" : "status"} className={`border border-l-4 border-rule bg-paper p-4 ${TONE[tone]}`}>
		<p className="font-bold">{title}</p>
		{children && <div className="mt-1 leading-snug text-carbon">{children}</div>}
	</div>
);

export default Notice;
