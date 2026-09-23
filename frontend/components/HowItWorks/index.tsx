'use client';

import { motion } from "framer-motion";

const steps = [
    {
        step: "01",
        title: "Upload Evidence",
        description: "Drag and drop an image, PDF document, or video file. Supports JPEG, PNG, PDF, MP4, AVI, and MOV.",
        icon: "📤",
    },
    {
        step: "02",
        title: "Vision Analysis",
        description: "Qwen-VL-Plus extracts microscopic anomalies — impossible reflections, AI texture patterns, metadata inconsistencies.",
        icon: "🔍",
    },
    {
        step: "03",
        title: "Critic Cross-Examination",
        description: "Three independent LLM critics (Qwen Turbo, DeepSeek R1, GLM 4.6) challenge and verify the vision findings.",
        icon: "⚔️",
    },
    {
        step: "04",
        title: "Consensus Verdict",
        description: "Majority vote determines the final classification with a calibrated confidence score and executive summary.",
        icon: "✅",
    },
];

const HowItWorks = () => {
    return (
        <section id="how-it-works" className="py-20 md:py-24">
            <div className="container">
                <div className="text-center mb-16">
                    <p className="text-sm font-semibold uppercase tracking-widest text-purple-400 mb-3">Process</p>
                    <h2 className="text-4xl md:text-6xl font-medium tracking-tighter">
                        How It Works
                    </h2>
                    <p className="text-white/60 text-lg md:text-xl max-w-xl mx-auto tracking-tight mt-5">
                        From upload to verdict in under 3 minutes.
                    </p>
                </div>

                <div className="max-w-3xl mx-auto relative">
                    {/* Vertical connector line */}
                    <div className="absolute left-8 top-0 bottom-0 w-px bg-gradient-to-b from-purple-500/50 via-purple-500/20 to-transparent hidden md:block" />

                    <div className="space-y-8">
                        {steps.map((item, i) => (
                            <motion.div
                                key={item.step}
                                initial={{ opacity: 0, x: -30 }}
                                whileInView={{ opacity: 1, x: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: i * 0.15, duration: 0.5 }}
                                className="flex gap-6 items-start"
                            >
                                <div className="relative flex-shrink-0 h-16 w-16 rounded-2xl bg-gradient-to-b from-purple-500/20 to-purple-900/10 border border-purple-500/20 flex items-center justify-center text-2xl">
                                    {item.icon}
                                    <div className="absolute -bottom-1 -right-1 bg-black text-[10px] font-bold text-purple-400 border border-purple-500/30 rounded px-1">{item.step}</div>
                                </div>
                                <div>
                                    <h3 className="text-xl font-bold text-white mb-1">{item.title}</h3>
                                    <p className="text-white/60 text-sm leading-relaxed">{item.description}</p>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                </div>
            </div>
        </section>
    );
};

export default HowItWorks;
