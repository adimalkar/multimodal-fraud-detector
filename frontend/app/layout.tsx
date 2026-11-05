import type { Metadata } from "next";
import { Instrument_Sans, Sometype_Mono } from "next/font/google";
import "@/styles/globals.css";

const sans = Instrument_Sans({ subsets: ["latin"], axes: ["wdth"], variable: "--font-sans" });
const data = Sometype_Mono({ subsets: ["latin"], variable: "--font-data" });

export const metadata: Metadata = {
	title: {
		default: "FraudSight: claim evidence screening for human review",
		template: "%s · FraudSight",
	},
	description:
		"Screen the photos, PDFs and video attached to an insurance claim. See what was found, what could not be checked, and decide for yourself.",
};

const RootLayout = ({ children }: Readonly<{ children: React.ReactNode }>) => (
	<html lang="en" className={`${sans.variable} ${data.variable}`}>
		<body className="font-sans antialiased">{children}</body>
	</html>
);

export default RootLayout;
