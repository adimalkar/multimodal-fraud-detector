"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Wordmark } from "@/components/landing/Logo";
import EngineStatus from "./EngineStatus";
import { EngineProvider } from "./useEngine";

const LINKS = [
	{ href: "/analyze", label: "Screen files" },
	{ href: "/analytics", label: "History" },
	{ href: "/signals", label: "Claim signals" },
];

const DeskShell = ({ children }: { children: React.ReactNode }) => {
	const pathname = usePathname();

	return (
		<EngineProvider>
			<div className="min-h-screen md:grid md:grid-cols-[232px_minmax(0,1fr)]">
				<aside className="border-b border-rule bg-paper md:sticky md:top-0 md:flex md:h-screen md:flex-col md:border-b-0 md:border-r">
					<div className="flex h-16 items-center px-4 md:px-5">
						<Link href="/" aria-label="FraudSight home"><Wordmark /></Link>
					</div>
					<nav aria-label="Workspace" className="flex gap-1 overflow-x-auto px-2 pb-2 md:block md:space-y-1 md:px-3 md:pb-0 md:pt-2">
						{LINKS.map((link) => {
							const current = pathname.startsWith(link.href);
							return (
								<Link
									key={link.href}
									href={link.href}
									aria-current={current ? "page" : undefined}
									className={`block whitespace-nowrap border-l-[3px] px-3 py-2.5 font-bold transition-colors ${
										current ? "border-carbon bg-lightbox" : "border-transparent text-graphite hover:text-carbon"
									}`}
								>
									{link.label}
								</Link>
							);
						})}
					</nav>
					<div className="border-t border-rule p-4 md:mt-auto md:p-5"><EngineStatus /></div>
				</aside>
				<main className="min-w-0 px-4 py-8 md:px-10 md:py-10">{children}</main>
			</div>
		</EngineProvider>
	);
};

export default DeskShell;
