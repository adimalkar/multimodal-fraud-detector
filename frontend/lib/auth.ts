import type { NextAuthOptions } from "next-auth";
import GitHubProvider from "next-auth/providers/github";
import GoogleProvider from "next-auth/providers/google";

/** Sign-in options. A provider appears only once both of its keys are set. */
const providers: NextAuthOptions["providers"] = [];

if (process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET) {
	providers.push(
		GoogleProvider({ clientId: process.env.AUTH_GOOGLE_ID, clientSecret: process.env.AUTH_GOOGLE_SECRET }),
	);
}
if (process.env.AUTH_GITHUB_ID && process.env.AUTH_GITHUB_SECRET) {
	providers.push(
		GitHubProvider({ clientId: process.env.AUTH_GITHUB_ID, clientSecret: process.env.AUTH_GITHUB_SECRET }),
	);
}

export const signInProviders = providers.map((provider) => ({ id: provider.id, name: provider.name }));

export const authOptions: NextAuthOptions = {
	providers,
	pages: { signIn: "/signin", error: "/signin" },
	session: { strategy: "jwt", maxAge: 7 * 24 * 60 * 60 },
	callbacks: {
		jwt({ token, account }) {
			// The provider's own account id is stable; an email can change or be shared.
			if (account) token.uid = `${account.provider}:${account.providerAccountId}`;
			return token;
		},
	},
};
