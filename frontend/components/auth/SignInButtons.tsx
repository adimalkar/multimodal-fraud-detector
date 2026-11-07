"use client";

import { signIn } from "next-auth/react";
import { useState } from "react";

const GoogleMark = () => (
	<svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true">
		<path fill="#4285F4" d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5a5.6 5.6 0 0 1-2.4 3.6v3h3.9c2.2-2.1 3.5-5.1 3.5-8.8z" />
		<path fill="#34A853" d="M12 24c3.2 0 6-1.1 8-2.9l-3.9-3a7.2 7.2 0 0 1-10.8-3.8h-4v3.1A12 12 0 0 0 12 24z" />
		<path fill="#FBBC05" d="M5.3 14.3a7.2 7.2 0 0 1 0-4.6V6.6h-4a12 12 0 0 0 0 10.8z" />
		<path fill="#EA4335" d="M12 4.8c1.8 0 3.3.6 4.6 1.8l3.4-3.4A12 12 0 0 0 1.3 6.6l4 3.1A7.2 7.2 0 0 1 12 4.8z" />
	</svg>
);

const GitHubMark = () => (
	<svg viewBox="0 0 16 16" className="h-5 w-5" fill="currentColor" aria-hidden="true">
		<path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
	</svg>
);

const MARKS: Record<string, () => JSX.Element> = { google: GoogleMark, github: GitHubMark };

const SignInButtons = ({
	providers,
	callbackUrl,
}: {
	providers: { id: string; name: string }[];
	callbackUrl: string;
}) => {
	const [pending, setPending] = useState<string | null>(null);

	return (
		<div className="grid gap-3">
			{providers.map((provider) => {
				const Mark = MARKS[provider.id];
				return (
					<button
						key={provider.id}
						type="button"
						disabled={pending !== null}
						onClick={() => {
							setPending(provider.id);
							void signIn(provider.id, { callbackUrl });
						}}
						className="btn-quiet w-full !min-h-12 bg-canvas"
					>
						{Mark && <Mark />}
						{pending === provider.id ? `Opening ${provider.name}…` : `Continue with ${provider.name}`}
					</button>
				);
			})}
		</div>
	);
};

export default SignInButtons;
