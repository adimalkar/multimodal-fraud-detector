import LogoIcon from "@/public/imgs/logo.svg";
import MenuIcon from "@/public/imgs/icon-menu.svg";
import Link from "next/link";
import Button from "../Button";

const  Header = () => {
    return (
        <header className="py-4 border-b border-white/15 md:border-none sticky top-0 z-10">
            <div className="absolute inset-0 backdrop-blur -z-10 md:hidden" />
            <div className="container">
                <div className="relative flex items-center justify-between md:border border-white/15 md:p-2.5 rounded-xl max-w-2xl mx-auto">
                    <div className="absolute inset-0 backdrop-blur -z-10 hidden md:block" />
                    <div>
                        <div className="border h-10 w-10 rounded-lg inline-flex items-center justify-center border-white/15">
                            <LogoIcon className="w-8 h-8" />
                        </div>
                    </div>
                    <div className="hidden md:block">
                        <nav className="flex gap-8 text-sm">
                            <Link href={`#`} className="text-white/70 hover:text-white transition">Features</Link>
                            <Link href={`#`} className="text-white/70 hover:text-white transition">Developers</Link>
                            <Link href={`#`} className="text-white/70 hover:text-white transition">Pricing</Link>
                            <Link href={`#`} className="text-white/70 hover:text-white transition">Changelog</Link>
                        </nav>
                    </div>
                    <div className="flex gap-4 items-center">
                        <Button>Join waitlist</Button>
                        <MenuIcon className="md:hidden" />
                    </div>
                </div>
            </div>
        </header>
    );
};

export default Header;