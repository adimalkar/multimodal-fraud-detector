'use client';

import { motion } from "framer-motion";

const agents = [
    {
        name: "Qwen-VL-Plus",
        role: "Vision Agent",
        description: "Extracts forensic visual features — lighting inconsistencies, texture anomalies, metadata artifacts.",
        color: "from-blue-500/20 to-blue-600/5",
        borderColor: "border-blue-500/30",
        dotColor: "bg-blue-400",
        icon: "👁️",
    },
    {
        name: "Qwen Turbo",
        role: "Critic Agent #1",
        description: "Cross-examines vision findings with logical reasoning. Challenges weak evidence.",
        color: "from-purple-500/20 to-purple-600/5",
        borderColor: "border-purple-500/30",
        dotColor: "bg-purple-400",
        icon: "⚖️",
    },
    {
        name: "DeepSeek R1-0528",
        role: "Critic Agent #2",
        description: "Deep reasoning chain-of-thought analysis. Provides independent forensic opinion.",
        color: "from-emerald-500/20 to-emerald-600/5",
        borderColor: "border-emerald-500/30",
        dotColor: "bg-emerald-400",
        icon: "🔬",
    },
    {
        name: "GLM 4.6",
        role: "Critic Agent #3",
        description: "Final independent judge. Specializes in document-level and structural analysis.",
        color: "from-amber-500/20 to-amber-600/5",
        borderColor: "border-amber-500/30",
        dotColor: "bg-amber-400",
        icon: "🧬",
    },
];

const Pipeline = () => {
    return (
        <section id="pipeline" className="py-20 md:py-24">
            <div className="container">
                <div className="text-center mb-16">
                    <p className="text-sm font-semibold uppercase tracking-widest text-purple-400 mb-3">Zero-Trust Architecture</p>
                    <h2 className="text-4xl md:text-6xl font-medium tracking-tighter">
                        Multi-Agent Jury System
                    </h2>
                    <p className="text-white/60 text-lg md:text-xl max-w-2xl mx-auto tracking-tight mt-5">
                        Every piece of evidence is independently analyzed by 4 AI agents.
                        No single model can override the verdict.
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 max-w-6xl mx-auto">
                    {agents.map((agent, i) => (
                        <motion.div
                            key={agent.name}
                            initial={{ opacity: 0, y: 30 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ delay: i * 0.15, duration: 0.5 }}
                            className={`relative border ${agent.borderColor} rounded-2xl bg-gradient-to-b ${agent.color} p-6 backdrop-blur-sm`}
                        >
                            <div className="text-3xl mb-4">{agent.icon}</div>
                            <div className="flex items-center gap-2 mb-1">
                                <div className={`h-2 w-2 rounded-full ${agent.dotColor} animate-pulse`} />
                                <span className="text-xs font-semibold uppercase tracking-wider text-white/50">{agent.role}</span>
                            </div>
                            <h3 className="text-lg font-bold text-white mb-2">{agent.name}</h3>
                            <p className="text-sm text-white/60 leading-relaxed">{agent.description}</p>
                        </motion.div>
                    ))}
                </div>

                {/* Consensus indicator */}
                <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{ delay: 0.6 }}
                    className="mt-8 max-w-md mx-auto border border-white/10 rounded-xl bg-white/5 p-5 text-center backdrop-blur-sm"
                >
                    <div className="text-2xl mb-2">🗳️</div>
                    <div className="text-sm font-bold text-white mb-1">Majority Consensus</div>
                    <p className="text-xs text-white/50">Final verdict is determined by majority vote across all agents with calibrated confidence scoring.</p>
                </motion.div>
            </div>
        </section>
    );
};

export default Pipeline;
