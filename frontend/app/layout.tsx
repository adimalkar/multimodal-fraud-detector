import type { Metadata } from "next";
import { Archivo, Atkinson_Hyperlegible, Sometype_Mono } from "next/font/google";
import "@/styles/globals.css";

const display = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--font-display" });
const body = Atkinson_Hyperlegible({
	subsets: ["latin"],
	weight: ["400", "700"],
	variable: "--font-body",
});
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
	<html lang="en" className={`${display.variable} ${body.variable} ${data.variable}`}>
		<body className="font-body antialiased">{children}</body>
	</html>
);

export default RootLayout;
