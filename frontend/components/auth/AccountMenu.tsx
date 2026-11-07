"use client";

import { signOut, useSession } from "next-auth/react";
import { useEffect, useRef, useState } from "react";
import { forgetEngineToken } from "@/lib/api";

const initials = (name: string) =>
	name
		.split(/\s+/)
		.filter(Boolean)
		.slice(0, 2)
		.map((part) => part[0]?.toUpperCase())
		.join("") || "?";

const AccountMenu = () => {
	const { data: session } = useSession();
	const [open, setOpen] = useState(false);
	const box = useRef<HTMLDivElement>(null);

	useEffect(() => {
		if (!open) return;
		const close = (event: MouseEvent) => {
			if (!box.current?.contains(event.target as Node)) setOpen(false);
		};
		const escape = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
		document.addEventListener("mousedown", close);
		document.addEventListener("keydown", escape);
		return () => {
			document.removeEventListener("mousedown", close);
			document.removeEventListener("keydown", escape);
		};
	}, [open]);

	if (!session?.user) return null;
	const name = session.user.name || session.user.email || "Your account";

	return (
		<div ref={box} className="relative text-sm">
			<button
				type="button"
				onClick={() => setOpen(!open)}
				aria-expanded={open}
				aria-label={`Account: ${name}`}
				className="flex h-10 w-10 items-center justify-center overflow-hidden rounded-full border border-line bg-raised font-medium text-ink transition-colors hover:border-muted"
			>
				{session.user.image ? (
					// Provider avatars come from many hosts, so a plain img avoids an image-domain allowlist.
					// eslint-disable-next-line @next/next/no-img-element
					<img src={session.user.image} alt="" className="h-full w-full object-cover" referrerPolicy="no-referrer" />
				) : (
					<span aria-hidden="true">{initials(name)}</span>
				)}
			</button>
			{open && (
				<div className="sheet absolute right-0 top-12 z-40 w-64 p-4 shadow-2xl">
					<p className="truncate font-medium">{name}</p>
					{session.user.email && session.user.email !== name && (
						<p className="mt-0.5 truncate text-muted">{session.user.email}</p>
					)}
					<button
						type="button"
						onClick={() => {
							forgetEngineToken();
							void signOut({ callbackUrl: "/" });
						}}
						className="btn-quiet mt-4 w-full !min-h-9 text-sm"
					>
						Sign out
					</button>
				</div>
			)}
		</div>
	);
};

export default AccountMenu;
