import LogoIcon from "@/public/imgs/logo.svg";
import MenuIcon from "@/public/imgs/icon-menu.svg";
import Link from "next/link";
import Button from "../Button";

const Header = () => {
    return (
        <header className="py-4 border-b border-white/15 md:border-none sticky top-0 z-10">
            <div className="absolute inset-0 backdrop-blur -z-10 md:hidden" />
            <div className="container">
                <div className="relative flex items-center justify-between md:border border-white/15 md:p-2.5 rounded-xl max-w-2xl mx-auto">
                    <div className="absolute inset-0 backdrop-blur -z-10 hidden md:block" />
                    <Link href="/" className="flex items-center gap-2">
                        <div className="border h-10 w-10 rounded-lg inline-flex items-center justify-center border-white/15">
                            <LogoIcon className="w-8 h-8" />
                        </div>
                        <span className="font-bold text-lg tracking-tight">FraudSight</span>
                    </Link>
                    <div className="hidden md:block">
                        <nav className="flex gap-8 text-sm">
                            <Link href="/#pipeline" className="text-white/70 hover:text-white transition">Pipeline</Link>
                            <Link href="/analyze" className="text-white/70 hover:text-white transition">Analyze</Link>
                            <Link href="/#how-it-works" className="text-white/70 hover:text-white transition">How It Works</Link>
                        </nav>
                    </div>
                    <div className="flex gap-4 items-center">
                        <Link href="/analyze">
                            <Button>Start Scanning</Button>
                        </Link>
                        <MenuIcon className="md:hidden" />
                    </div>
                </div>
            </div>
        </header>
    );
};

export default Header;