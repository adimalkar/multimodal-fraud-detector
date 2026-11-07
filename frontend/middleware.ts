import { withAuth } from "next-auth/middleware";
import { NextResponse } from "next/server";

/**
 * The workspace needs sign-in. Production always enforces it. Local
 * development enforces it once NEXTAUTH_SECRET is set, so the app still runs
 * without OAuth keys.
 */
const enforced = process.env.NODE_ENV === "production" || Boolean(process.env.NEXTAUTH_SECRET);

export default enforced ? withAuth({ pages: { signIn: "/signin" } }) : () => NextResponse.next();

export const config = { matcher: ["/analyze/:path*", "/analytics/:path*", "/signals/:path*"] };
