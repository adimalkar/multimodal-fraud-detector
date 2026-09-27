import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "@/styles/globals.css";
import { twMerge } from "tailwind-merge";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
	title: "FraudSight AI — Visual Evidence Screening",
	description: "Visual evidence screening for images, documents, and video. Every result requires human review.",
};

const RootLayout = ({
	children,
}: Readonly<{
	children: React.ReactNode;
}>) => {
	return (
		<html lang="en">
			<body
				className={twMerge(inter.className, "bg-black text-white antialiased")}
			>
				{children}
			</body>
		</html>
	);
};

export default RootLayout;
