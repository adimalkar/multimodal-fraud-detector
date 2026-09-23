import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "@/styles/globals.css";
import { twMerge } from "tailwind-merge";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
	title: "AI Startup Landing Page",
	description: "A landing page for an AI startup created with Frontend Tribe",
};

const RootLayout = ({
	children,
}: Readonly<{
	children: React.ReactNode;
}>) => {
	return (
		<html lang="pt-BR">
			<body
				className={twMerge(inter.className, "bg-black text-white antialiased")}
			>
				{children}
			</body>
		</html>
	);
};

export default RootLayout;