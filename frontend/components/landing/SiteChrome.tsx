import Link from "next/link";
import { API_URL } from "@/lib/api";
import { Wordmark } from "./Logo";

export const SiteHeader = () => (
	<header className="fixed inset-x-0 top-4 z-30 px-4">
		<div className="mx-auto flex h-14 max-w-[1000px] items-center justify-between gap-4 rounded-full border border-line bg-canvas/70 pl-5 pr-2 backdrop-blur-md">
			<Link href="/" aria-label="FraudSight home"><Wordmark /></Link>
			<nav aria-label="Page sections" className="hidden items-center gap-7 text-sm text-muted md:flex">
				<a href="#coverage" className="hover:text-ink">What it checks</a>
				<a href="#limits" className="hover:text-ink">Limits</a>
				<Link href="/analytics" className="hover:text-ink">History</Link>
			</nav>
			<Link href="/analyze" className="btn-primary !min-h-10 !px-4 text-sm">Screen a file</Link>
		</div>
	</header>
);

export const SiteFooter = () => (
	<footer className="border-t border-line py-8">
		<div className="wrap flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
			<Wordmark />
			<p className="text-sm text-muted">Screening support for claims teams. Every result needs human review.</p>
			<nav aria-label="Footer" className="flex gap-5 text-sm text-muted">
				<Link href="/analyze" className="hover:text-ink">Workspace</Link>
				<a href={`${API_URL}/docs`} className="hover:text-ink">API docs</a>
				<a href="https://github.com/adimalkar/multimodal-fraud-detector" className="hover:text-ink">GitHub</a>
			</nav>
		</div>
	</footer>
);
