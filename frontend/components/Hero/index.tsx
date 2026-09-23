'use client';

import { useRef } from "react";
import Link from "next/link";
import Button from "../Button";
import starsBg from "@/public/imgs/stars.png";
import { motion, useScroll, useTransform } from "framer-motion";

const Hero = () => {
    const sectionRef = useRef<HTMLElement>(null);
    const { scrollYProgress } = useScroll({
        target: sectionRef,
        offset: ['start end', 'end start'],
    });

    const backgroundPositionY = useTransform(scrollYProgress, [0, 1], [-300, 300]);

    return (
        <motion.section
            ref={sectionRef}
            className="relative h-[492px] md:h-[800px] flex items-center [mask-image:linear-gradient(to_bottom,transparent,black_10%,black_90%,transparent)] overflow-hidden"
            animate={{ backgroundPositionX: starsBg.width }}
            transition={{ duration: 120, repeat: Infinity, ease: 'linear' }}
            style={{ backgroundImage: `url(${starsBg.src})`, backgroundPositionY }}
        >
            <div className="absolute inset-0 bg-[radial-gradient(75%_75%_at_center_center,rgb(140,69,255,.5)_15%,rgb(14,0,36,.5)_78%,transparent)]" />
            <div className="absolute h-64 w-64 md:h-96 md:w-96 bg-purple-500 rounded-full border border-white/20 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-[radial-gradient(50%_50%_at_16.8%_18.3%,white,rgb(184,148,255)_37.7%,rgb(24,0,66))] shadow-[-20px_-20px_50px_rgb(255,255,255,.5),-20px_-20px_80px_rgb(255,255,255,.1),0_0_50px_rgb(140,69,255)]" />
            <motion.div 
                className="absolute h-[344px] w-[344px] md:h-[580px] md:w-[580px] border border-white opacity-20 rounded-full top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2"
                animate={{ rotate: '1turn' }}
                transition={{ duration: 60, repeat: Infinity, ease: 'linear' }}
                style={{ translateX: '-50%', translateY: '-50%' }}
            >
                <div className="absolute h-2 w-2 left-0 bg-white rounded-full top-1/2 -translate-x-1/2 -translate-y-1/2" />
                <div className="absolute h-2 w-2 left-1/2 bg-white rounded-full top-0 -translate-x-1/2 -translate-y-1/2" />
                <div className="absolute h-5 w-5 left-full border border-white rounded-full top-1/2 -translate-x-1/2 -translate-y-1/2 inline-flex items-center justify-center">
                    <div className="h-2 w-2 bg-white rounded-full" />
                </div>
            </motion.div>
            <motion.div 
                className="absolute h-[444px] w-[444px] md:h-[780px] md:w-[780px] rounded-full border border-white/20 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 border-dashed"
                animate={{ rotate: '-1turn' }}
                transition={{ duration: 60, repeat: Infinity, ease: 'linear' }}
                style={{ translateX: '-50%', translateY: '-50%' }}
            />
            <motion.div 
                className="absolute h-[544px] w-[544px] md:h-[980px] md:w-[980px] rounded-full border border-white opacity-20 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 border-dashed"
                animate={{ rotate: '1turn' }}
                transition={{ duration: 90, repeat: Infinity, ease: 'linear' }}
                style={{ translateX: '-50%', translateY: '-50%' }}
            >
                <div className="absolute h-2 w-2 left-0 bg-white rounded-full top-1/2 -translate-x-1/2 -translate-y-1/2" />
                <div className="absolute h-2 w-2 left-full bg-white rounded-full top-1/2 -translate-x-1/2 -translate-y-1/2" />
            </motion.div>
            <div className="relative container mt-16">
                <h1 className="text-8xl md:text-[168px] md:leading-none font-semibold tracking-tighter bg-white bg-[radial-gradient(100%_100%_at_top_left,white,rgb(74,32,138,.5))] text-transparent bg-clip-text text-center" style={{ letterSpacing: "-0.04em", fontSize: "110px" }}>FraudSight AI</h1>
                <p className="text-lg md:text-xl text-white/70 mt-5 text-center max-w-xl mx-auto">
                    Multi-Agent Insurance Fraud Detection. Zero-trust pipeline powered by Qwen and DeepSeek for Images, Documents, and Video.
                </p>
                <div className="flex justify-center mt-5">
                    <Link href="/analyze">
                        <Button>Start Scanning</Button>
                    </Link>
                </div>
            </div>
        </motion.section>
    );
};

export default Hero;