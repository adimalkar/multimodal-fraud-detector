'use client';

import { RefObject, useCallback, useEffect, useRef } from "react";
import { motion, useMotionTemplate, useMotionValue, useScroll, useTransform } from "framer-motion";
import Link from "next/link";
import Button from "../Button";
import starsBg from "@/public/imgs/stars.png";
import gridLines from "@/public/imgs/grid-lines.png";

const useRelativeMousePosition = (to: RefObject<HTMLElement>) => {
    const mouseX = useMotionValue(0);
    const mouseY = useMotionValue(0);

    const updateMousePosition = useCallback((e: MouseEvent) => {
        if (!to.current) return;

        const { top, left, width, height } = to.current.getBoundingClientRect();

        const xPos = ((e.clientX - left) / width) * 100;
        const yPos = ((e.clientY - top) / height) * 100;

        mouseX.set(xPos);
        mouseY.set(yPos);
    }, [mouseX, mouseY, to]);

    useEffect(() => {
        window.addEventListener("mousemove", updateMousePosition);

        return () => {
            window.removeEventListener("mousemove", updateMousePosition);
        }
    }, [updateMousePosition]);

    return [ mouseX, mouseY ];
};

const CTA = () => {
    const sectionRef = useRef<HTMLElement>(null);
    const borderedDivRef = useRef<HTMLDivElement>(null);

    const { scrollYProgress } = useScroll({
        target: sectionRef,
        offset: ["start end", "end start"],
    });

    const backgroundPositionY = useTransform(scrollYProgress, [0, 1], [-300, 300]);
    const [ mouseX, mouseY ] = useRelativeMousePosition(borderedDivRef);
    const maskImage = useMotionTemplate`radial-gradient(50% 50% at ${mouseX}% ${mouseY}%, black, transparent)`;

    return (
        <section ref={sectionRef} className="py-20 md:py-24">
            <div className="container">
                <motion.div
                    ref={borderedDivRef}
                    className="relative group border border-white/15 py-24 rounded-xl overflow-hidden"
                    animate={{ backgroundPositionX: starsBg.width }}
                    transition={{ duration: 60, repeat: Infinity, ease: "linear" }}
                    style={{ 
                        backgroundImage: `url(${starsBg.src})`,
                        backgroundPositionY,
                    }}
                >
                    <div 
                        className="absolute inset-0 bg-[rgb(74,32,138)] bg-blend-overlay [mask-image:radial-gradient(50%_50%_at_50%_35%,black,transparent)] group-hover:opacity-0 transition duration-700"
                        style={{
                            backgroundImage: `url(${gridLines.src})`,
                        }}
                    />
                    <motion.div 
                        className="absolute inset-0 bg-[rgb(74,32,138)] bg-blend-overlay opacity-0 group-hover:opacity-100 transition duration-700"
                        style={{
                            backgroundImage: `url(${gridLines.src})`,
                            maskImage,
                        }}
                    />
                    <div className="relative">
                        <h2 className="text-5xl md:text-6xl max-w-lg mx-auto tracking-tighter text-center font-medium">
                            Ready to verify your evidence?
                        </h2>
                        <p className="text-center text-lg md:text-xl max-w-xs mx-auto text-white/70 px-4 mt-5 tracking-tight">
                            Detect deepfakes, forged documents, and tampered videos instantly.
                        </p>
                        <div className="flex justify-center mt-8">
                            <Link href="/analyze">
                                <Button>Start Scanning Now</Button>
                            </Link>
                        </div>
                    </div>
                </motion.div>
            </div>
        </section>
    );
};

export default CTA;