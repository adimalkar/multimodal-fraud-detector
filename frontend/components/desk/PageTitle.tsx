const PageTitle = ({ title, lede, actions }: { title: string; lede?: string; actions?: React.ReactNode }) => (
	<header className="mb-8 flex flex-wrap items-end justify-between gap-4">
		<div className="min-w-0">
			<h1 className="display break-words text-4xl md:text-6xl">{title}</h1>
			{lede && <p className="mt-3 max-w-2xl text-lg leading-relaxed text-graphite">{lede}</p>}
		</div>
		{actions}
	</header>
);

export default PageTitle;
