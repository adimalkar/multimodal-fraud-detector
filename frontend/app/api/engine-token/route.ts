import { createHmac } from "node:crypto";
import { getToken } from "next-auth/jwt";
import { type NextRequest, NextResponse } from "next/server";

/**
 * Hands the signed-in visitor a short-lived token for the screening engine.
 * The engine checks it with the same WEB_AUTH_SECRET, so the browser never
 * holds anything that outlives ten minutes.
 */
export const dynamic = "force-dynamic";

const LIFETIME_SECONDS = 600;
const NO_STORE = { "Cache-Control": "no-store" };

const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");

export const GET = async (req: NextRequest) => {
	const session = await getToken({ req });
	const uid = typeof session?.uid === "string" ? session.uid : null;
	if (!uid) return NextResponse.json({ error: "Sign in first" }, { status: 401, headers: NO_STORE });

	const secret = process.env.WEB_AUTH_SECRET ?? "";
	// No secret means the engine is running without sign-in, so send no token.
	if (!secret) return NextResponse.json({ token: null }, { headers: NO_STORE });

	const now = Math.floor(Date.now() / 1000);
	const unsigned = `${encode({ alg: "HS256", typ: "JWT" })}.${encode({
		sub: uid,
		iss: "fraudsight-web",
		aud: "fraudsight-engine",
		iat: now,
		exp: now + LIFETIME_SECONDS,
	})}`;
	const signature = createHmac("sha256", secret).update(unsigned).digest("base64url");
	return NextResponse.json(
		{ token: `${unsigned}.${signature}`, expires_at: (now + LIFETIME_SECONDS) * 1000 },
		{ headers: NO_STORE },
	);
};
