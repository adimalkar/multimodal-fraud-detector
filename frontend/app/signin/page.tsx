import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getServerSession } from "next-auth";
import SignInButtons from "@/components/auth/SignInButtons";
import Notice from "@/components/desk/Notice";
import { Wordmark } from "@/components/landing/Logo";
import { authOptions, signInProviders } from "@/lib/auth";

export const metadata: Metadata = { title: "Sign in" };

const ERRORS: Record<string, string> = {
	OAuthAccountNotLinked: "That email already signed in with the other option. Use the one you used first.",
	AccessDenied: "Sign-in was cancelled or refused.",
	Configuration: "Sign-in isn't set up correctly on this deployment.",
	SessionRequired: "Sign in to open the workspace.",
};

/** Only same-site paths, so the sign-in page can't be used to bounce visitors elsewhere. */
const safePath = (value: unknown) =>
	typeof value === "string" && value.startsWith("/") && !value.startsWith("//") ? value : "/analyze";

const SignInPage = async ({ searchParams }: { searchParams: Record<string, string | string[] | undefined> }) => {
	const callbackUrl = safePath(searchParams.callbackUrl);
	if (await getServerSession(authOptions)) redirect(callbackUrl);

	const errorCode = typeof searchParams.error === "string" ? searchParams.error : null;
	const error = errorCode ? (ERRORS[errorCode] ?? "Sign-in didn't work. Try again.") : null;

	return (
		<div className="dots flex min-h-screen flex-col">
			<header className="px-5 py-5 md:px-8">
				<Link href="/" aria-label="FraudSight home" className="inline-block"><Wordmark /></Link>
			</header>
			<main className="flex flex-1 items-center justify-center px-4 pb-16">
				<div className="sheet w-full max-w-md p-6 shadow-2xl md:p-8">
					<p className="label">Workspace</p>
					<h1 className="display mt-2 text-4xl">Sign in to screen files</h1>
					<p className="mt-3 leading-relaxed text-muted">
						Your screenings and history are visible only to your account. Each account has a daily file
						limit so the service can stay free.
					</p>
					<div className="mt-6 grid gap-4">
						{error && <Notice tone="error" title={error} />}
						{signInProviders.length > 0 ? (
							<SignInButtons providers={signInProviders} callbackUrl={callbackUrl} />
						) : (
							<Notice tone="warn" title="Sign-in isn't set up yet">
								Add Google or GitHub OAuth keys to this deployment. The README lists them.
							</Notice>
						)}
					</div>
					<p className="mt-6 text-sm leading-snug text-muted">
						FraudSight keeps your provider account id to separate your screenings from everyone
						else&apos;s. It doesn&apos;t post anything or read your repositories or mail.
					</p>
				</div>
			</main>
		</div>
	);
};

export default SignInPage;
