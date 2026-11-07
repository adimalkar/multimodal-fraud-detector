"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SessionProvider } from "next-auth/react";
import AccountMenu from "@/components/auth/AccountMenu";
import { Wordmark } from "@/components/landing/Logo";
import EngineStatus from "./EngineStatus";
import { EngineProvider } from "./useEngine";

const LINKS = [
	{ href: "/analyze", label: "Screen" },
	{ href: "/analytics", label: "History" },
	{ href: "/signals", label: "Claim signals" },
];

const WorkspaceShell = ({ children }: { children: React.ReactNode }) => {
	const pathname = usePathname();

	return (
		<SessionProvider>
			<EngineProvider>
				<div className="flex min-h-screen flex-col">
					<header className="sticky top-0 z-30 border-b border-line bg-canvas/80 backdrop-blur-md">
						<div className="flex h-16 items-center justify-between gap-4 px-4 md:px-8">
							<Link href="/" aria-label="FraudSight home"><Wordmark /></Link>
							<nav aria-label="Workspace" className="hidden items-center gap-1 rounded-full border border-line p-1 md:flex">
								{LINKS.map((link) => {
									const current = pathname.startsWith(link.href);
									return (
										<Link
											key={link.href}
											href={link.href}
											aria-current={current ? "page" : undefined}
											className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${current ? "bg-raised text-ink" : "text-muted hover:text-ink"}`}
										>
											{link.label}
										</Link>
									);
								})}
							</nav>
							<div className="flex items-center gap-2">
								<EngineStatus />
								<AccountMenu />
							</div>
						</div>
						<nav aria-label="Workspace, small screens" className="flex gap-1 overflow-x-auto px-4 pb-2 md:hidden">
							{LINKS.map((link) => (
								<Link
									key={link.href}
									href={link.href}
									aria-current={pathname.startsWith(link.href) ? "page" : undefined}
									className={`whitespace-nowrap rounded-full px-3 py-1.5 text-sm font-medium ${pathname.startsWith(link.href) ? "bg-raised text-ink" : "text-muted"}`}
								>
									{link.label}
								</Link>
							))}
						</nav>
					</header>
					<main className="flex min-w-0 flex-1 flex-col">{children}</main>
				</div>
			</EngineProvider>
		</SessionProvider>
	);
};

export default WorkspaceShell;
