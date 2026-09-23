import Link from "next/link";
import Logo from "@/public/imgs/logo.svg";
import XSocial from "@/public/imgs/social-x.svg";
import InstaSocial from "@/public/imgs/social-instagram.svg";
import YTSocial from "@/public/imgs/social-youtube.svg";

const Footer = () => {
    return (
        <footer className="py-5 border-t border-white/15">
            <div className="container">
                <div className="flex flex-col lg:flex-row items-center gap-8">
                    <div className="flex items-center gap-2 lg:flex-1">
                        <Logo className="h-6 w-6" />
                        <div className="font-medium">AI Startup Landing Page</div>
                    </div>
                    <nav className="flex flex-col lg:flex-row gap-5 lg:gap-7 lg:flex-1 lg:justify-center">
                        <Link 
                            href={`#`} 
                            className="text-white/70 hover:text-white text-xs md:text-sm transition"
                        >
                            Features
                        </Link>
                        <Link 
                            href={`#`} 
                            className="text-white/70 hover:text-white text-xs md:text-sm transition"
                        >
                            Developers
                        </Link>
                        <Link 
                            href={`#`} 
                            className="text-white/70 hover:text-white text-xs md:text-sm transition"
                        >
                            Company
                        </Link>
                        <Link 
                            href={`#`} 
                            className="text-white/70 hover:text-white text-xs md:text-sm transition"
                        >
                            Blog
                        </Link>
                        <Link 
                            href={`#`} 
                            className="text-white/70 hover:text-white text-xs md:text-sm transition"
                        >
                            Changelog
                        </Link>
                    </nav>
                    <div className="flex gap-5 lg:flex-1 lg:justify-end">
                        <XSocial className="text-white/40 hover:text-white transition" />
                        <InstaSocial className="text-white/40 hover:text-white transition" />
                        <YTSocial className="text-white/40 hover:text-white transition" />
                    </div>
                </div>
            </div>
        </footer>
    );
};

export default Footer;