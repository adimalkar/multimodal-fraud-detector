import type { Metadata } from "next";
import ClaimSignals from "@/components/desk/ClaimSignals";

export const metadata: Metadata = { title: "Claim signals" };

const SignalsPage = () => <ClaimSignals />;

export default SignalsPage;
