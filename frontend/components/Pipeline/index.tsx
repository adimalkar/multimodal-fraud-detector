'use client';

import { motion } from "framer-motion";

const stages = [
    {
        name: "Prepare evidence",
        role: "Input boundary",
        description: "Resize one image, render up to three PDF pages, or sample three video frames.",
        color: "from-blue-500/20 to-blue-600/5",
        borderColor: "border-blue-500/30",
        dotColor: "bg-blue-400",
        icon: "📥",
    },
    {
        name: "Visual screening",
        role: "One model request",
        description: "A low-cost vision model reports observable details and an uncertain Real or Fake label.",
        color: "from-purple-500/20 to-purple-600/5",
        borderColor: "border-purple-500/30",
        dotColor: "bg-purple-400",
        icon: "👁️",
    },
    {
        name: "Metadata signals",
        role: "Heuristic context",
        description: "Available file metadata contributes to a provisional score; missing metadata is not proof of forgery.",
        color: "from-emerald-500/20 to-emerald-600/5",
        borderColor: "border-emerald-500/30",
        dotColor: "bg-emerald-400",
        icon: "🔬",
    },
    {
        name: "Human review",
        role: "Decision boundary",
        description: "Every screening result needs a person to review the evidence before any claim decision.",
        color: "from-amber-500/20 to-amber-600/5",
        borderColor: "border-amber-500/30",
        dotColor: "bg-amber-400",
        icon: "👤",
    },
];

const Pipeline = () => {
    return (
        <section id="pipeline" className="py-20 md:py-24">
            <div className="container">
                <div className="text-center mb-16">
                    <p className="text-sm font-semibold uppercase tracking-widest text-purple-400 mb-3">Screening pipeline</p>
                    <h2 className="text-4xl md:text-6xl font-medium tracking-tighter">From evidence to review</h2>
                    <p className="text-white/60 text-lg md:text-xl max-w-2xl mx-auto tracking-tight mt-5">
                        A bounded visual check and a clear handoff to a human reviewer.
                    </p>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 max-w-6xl mx-auto">
                    {stages.map((stage, i) => (
                        <motion.div
                            key={stage.name}
                            initial={{ opacity: 0, y: 30 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ delay: i * 0.15, duration: 0.5 }}
                            className={`relative border ${stage.borderColor} rounded-2xl bg-gradient-to-b ${stage.color} p-6 backdrop-blur-sm`}
                        >
                            <div className="text-3xl mb-4">{stage.icon}</div>
                            <div className="flex items-center gap-2 mb-1">
                                <div className={`h-2 w-2 rounded-full ${stage.dotColor} animate-pulse`} />
                                <span className="text-xs font-semibold uppercase tracking-wider text-white/50">{stage.role}</span>
                            </div>
                            <h3 className="text-lg font-bold text-white mb-2">{stage.name}</h3>
                            <p className="text-sm text-white/60 leading-relaxed">{stage.description}</p>
                        </motion.div>
                    ))}
                </div>
                <p className="mt-8 max-w-xl mx-auto text-center text-sm text-white/50">
                    Model confidence and the risk heuristic have not been calibrated against a labeled evaluation set.
                </p>
            </div>
        </section>
    );
};

export default Pipeline;
