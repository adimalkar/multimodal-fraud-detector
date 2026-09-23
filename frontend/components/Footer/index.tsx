import Logo from "@/public/imgs/logo.svg";
import Link from "next/link";

const Footer = () => {
    return (
        <footer className="py-5 border-t border-white/15">
            <div className="container">
                <div className="flex flex-col lg:flex-row items-center gap-8">
                    <div className="flex items-center gap-2 lg:flex-1">
                        <Logo className="h-6 w-6" />
                        <div className="font-medium">FraudSight AI</div>
                    </div>
                    <nav className="flex flex-col lg:flex-row gap-5 lg:gap-7 lg:flex-1 lg:justify-center">
                        <Link
                            href="#pipeline"
                            className="text-white/70 hover:text-white text-xs md:text-sm transition"
                        >
                            Pipeline
                        </Link>
                        <Link
                            href="/analyze"
                            className="text-white/70 hover:text-white text-xs md:text-sm transition"
                        >
                            Analyze
                        </Link>
                        <Link
                            href="/analytics"
                            className="text-white/70 hover:text-white text-xs md:text-sm transition"
                        >
                            Analytics
                        </Link>
                        <Link
                            href="#how-it-works"
                            className="text-white/70 hover:text-white text-xs md:text-sm transition"
                        >
                            How It Works
                        </Link>
                        <Link
                            href="https://github.com/adimalkar/multimodal-fraud-detector"
                            target="_blank"
                            className="text-white/70 hover:text-white text-xs md:text-sm transition"
                        >
                            GitHub
                        </Link>
                    </nav>
                    <div className="lg:flex-1 lg:text-right">
                        <p className="text-white/40 text-xs">Built for the Databricks AI Hackathon</p>
                    </div>
                </div>
            </div>
        </footer>
    );
};

export default Footer;