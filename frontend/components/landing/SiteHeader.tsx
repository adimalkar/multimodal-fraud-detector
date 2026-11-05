import Link from "next/link";
import { Wordmark } from "./Logo";

const SiteHeader = () => (
	<header className="sticky top-0 z-30 border-b border-rule bg-lightbox/95 backdrop-blur-sm">
		<div className="wrap flex h-16 items-center justify-between gap-4">
			<Link href="/" aria-label="FraudSight home">
				<Wordmark />
			</Link>
			<nav aria-label="Page sections" className="hidden items-center gap-7 md:flex">
				<a href="#steps" className="hover:text-uv">How it works</a>
				<a href="#coverage" className="hover:text-uv">What it checks</a>
				<a href="#limits" className="hover:text-uv">Limits</a>
			</nav>
			<Link href="/analyze" className="btn-primary !min-h-10 !px-4 text-[0.9375rem]">
				Screen a file
			</Link>
		</div>
	</header>
);

export default SiteHeader;
