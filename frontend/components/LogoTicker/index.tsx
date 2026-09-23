'use client';

import acmeLogo from "@/public/imgs/logo-acme.png";
import apexLogo from "@/public/imgs/logo-apex.png";
import celestialLogo from "@/public/imgs/logo-celestial.png";
import quantumLogo from "@/public/imgs/logo-quantum.png";
import pulseLogo from "@/public/imgs/logo-pulse.png";
import echoLogo from "@/public/imgs/logo-echo.png";
import Image from "next/image";
import { motion } from "framer-motion";

const LogoTicker = () => {
    return (
        <section className="py-20 md:py-24">
            <div className="container">
                <div className="flex items-center gap-5">
                    <div className="flex-1 md:flex-none">
                        <h2 className="">Trusted by top innovate teams</h2>
                    </div>
                    <div className="flex flex-1 [mask-image:linear-gradient(to_right,transparent,black_20%,black_80%,transparent)] overflow-hidden">
                        <motion.div 
                            className="flex flex-none gap-14 pr-14 -translate-x-1/2"
                            initial={{ translateX: "-50%" }}
                            animate={{ translateX: "0" }}
                            transition={{ duration: 30, repeat: Infinity, ease: "linear" }}
                        >
                            {[
                                acmeLogo, 
                                pulseLogo, 
                                echoLogo,
                                celestialLogo, 
                                apexLogo, 
                                quantumLogo, 
                                acmeLogo, 
                                pulseLogo, 
                                echoLogo,
                                celestialLogo, 
                                apexLogo, 
                                quantumLogo, 
                            ].map((logo, index) => (
                                <Image 
                                    key={`${index}-${logo.src}`}
                                    src={logo.src}
                                    className="h-6 w-auto flex-none"
                                    width={logo.width}
                                    height={logo.height}
                                    alt={`Logo ${index}`}
                                />
                            ))}
                        </motion.div>
                    </div>
                </div>
            </div>
        </section>
    );
};

export default LogoTicker;