import Link from "next/link";
import { API_URL } from "@/lib/api";
import { Wordmark } from "./Logo";

const SiteFooter = () => (
	<footer className="border-t border-rule py-8">
		<div className="wrap flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
			<Wordmark />
			<p className="text-sm text-graphite">Screening support for claims teams. Every result needs human review.</p>
			<nav aria-label="Footer" className="flex gap-5 text-sm">
				<Link href="/analyze" className="hover:text-uv">Workspace</Link>
				<a href={`${API_URL}/docs`} className="hover:text-uv">API docs</a>
				<a href="https://github.com/adimalkar/multimodal-fraud-detector" className="hover:text-uv">GitHub</a>
			</nav>
		</div>
	</footer>
);

export default SiteFooter;
