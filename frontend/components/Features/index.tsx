'use client';

import { DotLottieCommonPlayer, DotLottiePlayer } from "@dotlottie/react-player";
import productImage from "@/public/imgs/product-image.png";
import { ComponentPropsWithoutRef, useEffect, useRef, useState } from "react";
import { animate, motion, useMotionTemplate, useMotionValue, ValueAnimationTransition } from "framer-motion";

export type TabProps = {
    icon: string;
    title: string;
    isNew: boolean;
    backgroundPositionX: number;
    backgroundPositionY: number;
    backgroundSizeX: number;
};

const tabs: TabProps[] = [
    {
        icon: "/lottie/vroom.lottie",
        title: "Multi-Modal Support",
        isNew: false,
        backgroundPositionX: 0,
        backgroundPositionY: 0,
        backgroundSizeX: 150,
    },
    {
        icon: "/lottie/click.lottie",
        title: "Agentic Consensus",
        isNew: false,
        backgroundPositionX: 98,
        backgroundPositionY: 100,
        backgroundSizeX: 135,
    },
    {
        icon: "/lottie/stars.lottie",
        title: "Vision-Language Models",
        isNew: true,
        backgroundPositionX: 100,
        backgroundPositionY: 27,
        backgroundSizeX: 177,
    },
];

const FeatureTab = (props: typeof tabs[number] & ComponentPropsWithoutRef<'div'> & { selected: boolean }) => {
    const tabRef = useRef<HTMLDivElement>(null);
    const dotLottieRef = useRef<DotLottieCommonPlayer>(null);

    const xPercentage = useMotionValue(0);
    const yPercentage = useMotionValue(0);

    const maskImage = useMotionTemplate`radial-gradient(80px 80px at ${xPercentage}% ${yPercentage}%, black, transparent)`;

    const handleTabHover = () => {
        if (dotLottieRef.current === null) return;
        dotLottieRef.current.seek(0);
        dotLottieRef.current.play();
    };

    useEffect(() => {
        if (!tabRef.current || !props.selected) return;

        xPercentage.set(0);
        yPercentage.set(0);

        const { width, height } = tabRef.current.getBoundingClientRect();
        const circunference = 2 * (width + height);
        const times = [0, width / circunference, (width + height) / circunference, (width * 2 + height) / circunference, 1];

        const options: ValueAnimationTransition = {
            times,
            duration: 4,
            repeat: Infinity,
            ease: "linear",
            repeatType: "loop",
        };

        animate(xPercentage, [0, 100, 100, 0, 0], options);
        animate(yPercentage, [0, 0, 100, 100, 0], options);
    }, [props.selected, xPercentage, yPercentage]);

    return (
        <div
            ref={tabRef}
            className="relative flex lg:flex-1 items-center gap-2.5 border border-white/15 p-2.5 rounded-xl"
            onMouseEnter={handleTabHover}
            onClick={props.onClick}
        >
            {props.selected && (
                <motion.div 
                    className="absolute inset-0 -m-px border border-[#A369FF] rounded-xl" 
                    style={{
                        maskImage,
                    }}
                />
            )}
            <div className="inline-flex items-center justify-center h-12 w-12 border border-white/15 rounded-lg">
                <DotLottiePlayer
                    ref={dotLottieRef}
                    src={props.icon}
                    className="h-5 w-5"
                    autoplay
                />
            </div>
            <div className="font-medium">{props.title}</div>
            {props.isNew && (
                <div className="text-xs text-black font-semibold rounded-full px-2 py-0.5 bg-[#8c44ff]">
                    New
                </div>
            )}
        </div>
    );
};

const Features = () => {
    const [selectedTab, setSelectedTab] = useState<number>(0);

    const backgroundPositionX = useMotionValue(tabs[0].backgroundPositionX);
    const backgroundPositionY = useMotionValue(tabs[0].backgroundPositionY);
    const backgroundSizeX = useMotionValue(tabs[0].backgroundSizeX);

    const backgroundPosition = useMotionTemplate`${backgroundPositionX}% ${backgroundPositionY}%`;
    const backgroundSize = useMotionTemplate`${backgroundSizeX}% auto`;

    const handleSelectedTab = (index: number) => {
        setSelectedTab(index);

        const animateOptions: ValueAnimationTransition = {
            duration: 2,
            ease: "easeInOut",
        };

        animate(backgroundSizeX, [backgroundSizeX.get(), 100, tabs[index].backgroundSizeX], animateOptions);
        animate(backgroundPositionX, [backgroundPositionX.get(), tabs[index].backgroundPositionX], animateOptions);
        animate(backgroundPositionY, [backgroundPositionY.get(), tabs[index].backgroundPositionY], animateOptions);
    };


    return (
        <section className="py-20 md:py-24">
            <div className="container">
                <h2 className="text-5xl md:text-6xl font-medium text-center tracking-tighter">Expose fraud with precision.</h2>
                <p className="text-white/70 text-lg md:text-xl max-w-2xl mx-auto tracking-tight text-center mt-5">
                    From deepfakes to document forgery, our multi-agent architecture uses state-of-the-art vision models and critic agents to detect microscopic anomalies.
                </p>
                <div className="flex flex-col lg:flex-row gap-3 mt-10">
                    {tabs.map((tab, index) => (
                        <FeatureTab 
                            key={`${index}-${tab.title}`}
                            selected={selectedTab === index}
                            onClick={() => handleSelectedTab(index)}
                            {...tab} 
                        />
                    ))}
                </div>
                <div className="border border-white/20 p-2.5 rounded-xl mt-3">
                    <motion.div
                        className="aspect-video bg-cover border border-white/20 rounded-lg"
                        style={{ 
                            backgroundImage: `url(${productImage.src})`,
                            backgroundPosition,
                            backgroundSize,
                        }}
                    />
                </div>
            </div>
        </section>
    );
};

export default Features;