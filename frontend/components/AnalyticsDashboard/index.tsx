/* eslint-disable @typescript-eslint/no-explicit-any */
'use client';

import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import Link from 'next/link';
import Button from '../Button';

interface AnalyticsData {
  total_records: number;
  processed_records: number;
  fake_count: number;
  real_count: number;
  flagged_rate_percentage: number;
  avg_confidence: number;
  avg_processing_time_sec: number;
  database_engine?: string;
  media_counts: {
    images: number;
    documents: number;
    videos: number;
  };
  severity_breakdown?: {
    critical_fraud: number;
    high_risk: number;
    suspicious: number;
    low_risk: number;
  };
  recent_evaluations: Array<{
    id: number;
    filename: string;
    media_type: string;
    fraud_category: string;
    ai_prediction: string;
    confidence: number;
    risk_score?: number;
    severity_tier?: string;
    recommended_action?: string;
    final_reasoning: string;
    processing_time: number;
    processed_at: string;
  }>;
}

const mockDefaultData: AnalyticsData = {
  total_records: 48,
  processed_records: 48,
  fake_count: 19,
  real_count: 29,
  flagged_rate_percentage: 39.6,
  avg_confidence: 0.942,
  avg_processing_time_sec: 4.8,
  database_engine: "PostgreSQL / SQLite",
  media_counts: {
    images: 32,
    documents: 11,
    videos: 5
  },
  severity_breakdown: {
    critical_fraud: 12,
    high_risk: 7,
    suspicious: 14,
    low_risk: 15
  },
  recent_evaluations: [
    {
      id: 1,
      filename: "tampered_invoice_04.pdf",
      media_type: "Document",
      fraud_category: "Document Fraud",
      ai_prediction: "Fake",
      confidence: 0.98,
      risk_score: 0.96,
      severity_tier: "CRITICAL_FRAUD",
      recommended_action: "BLOCK_TRANSACTION_AND_ALERT_SECURITY",
      final_reasoning: "DeepSeek & Qwen critics identified spliced font metrics and metadata mismatch in header.",
      processing_time: 3.2,
      processed_at: "2026-09-22 21:15:30"
    },
    {
      id: 2,
      filename: "bumper_crash_rear.jpg",
      media_type: "Image",
      fraud_category: "Vehicle Claim",
      ai_prediction: "Real",
      confidence: 0.96,
      risk_score: 0.08,
      severity_tier: "LOW_RISK",
      recommended_action: "APPROVE_AUTOMATICALLY",
      final_reasoning: "Authentic ambient specular reflections and natural compression artifacts confirmed by jury.",
      processing_time: 2.1,
      processed_at: "2026-09-22 20:45:10"
    },
    {
      id: 3,
      filename: "dashcam_intersection.mp4",
      media_type: "Video",
      fraud_category: "Vehicle Claim",
      ai_prediction: "Fake",
      confidence: 0.93,
      risk_score: 0.88,
      severity_tier: "HIGH_RISK",
      recommended_action: "ESCALATE_TO_SENIOR_ANALYST_QUEUE",
      final_reasoning: "Frame-to-frame temporal inconsistency detected on passenger door reflection pattern.",
      processing_time: 8.4,
      processed_at: "2026-09-22 19:30:22"
    },
    {
      id: 4,
      filename: "roof_hail_damage.jpg",
      media_type: "Image",
      fraud_category: "Property Claim",
      ai_prediction: "Real",
      confidence: 0.89,
      risk_score: 0.22,
      severity_tier: "LOW_RISK",
      recommended_action: "APPROVE_AUTOMATICALLY",
      final_reasoning: "Consistent lighting angle across impact craters matching solar direction metadata.",
      processing_time: 2.4,
      processed_at: "2026-09-22 18:12:05"
    }
  ]
};

const AnalyticsDashboard = () => {
  const [data, setData] = useState<AnalyticsData>(mockDefaultData);
  const [loading, setLoading] = useState(false);
  const [isLive, setIsLive] = useState(false);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'https://multimodal-fraud-detector-1.onrender.com';

  const fetchStats = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiUrl}/api/analytics/stats`);
      if (res.ok) {
        const json = await res.json();
        if (json.total_records > 0 || json.recent_evaluations?.length > 0) {
          setData(json);
          setIsLive(true);
        }
      }
    } catch (e) {
      console.warn("Backend analytics offline, showing cached metrics:", e);
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const handleDownloadCsv = () => {
    window.open(`${apiUrl}/api/analytics/export-csv`, '_blank');
  };

  const getTierBadge = (tier?: string) => {
    switch (tier) {
      case 'CRITICAL_FRAUD':
        return <span className="px-2 py-0.5 rounded-full font-bold text-[10px] bg-red-500/20 text-red-400 border border-red-500/30">CRITICAL</span>;
      case 'HIGH_RISK':
        return <span className="px-2 py-0.5 rounded-full font-bold text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30">HIGH RISK</span>;
      case 'SUSPICIOUS':
        return <span className="px-2 py-0.5 rounded-full font-bold text-[10px] bg-yellow-500/20 text-yellow-300 border border-yellow-500/30">SUSPICIOUS</span>;
      case 'LOW_RISK':
        return <span className="px-2 py-0.5 rounded-full font-bold text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">LOW RISK</span>;
      default:
        return <span className="px-2 py-0.5 rounded-full font-mono text-[10px] text-white/40">--</span>;
    }
  };

  const getActionBadge = (action?: string) => {
    switch (action) {
      case 'BLOCK_TRANSACTION_AND_ALERT_SECURITY':
        return <span className="text-red-400 font-medium">Block & Alert</span>;
      case 'ESCALATE_TO_SENIOR_ANALYST_QUEUE':
        return <span className="text-amber-300 font-medium">Escalate Queue</span>;
      case 'REQUIRE_STEP_UP_MFA_AUTHENTICATION':
        return <span className="text-yellow-300 font-medium">Step-up MFA</span>;
      case 'APPROVE_AUTOMATICALLY':
        return <span className="text-emerald-400 font-medium">Auto Approve</span>;
      default:
        return <span className="text-white/40 font-mono">Manual Review</span>;
    }
  };

  return (
    <section className="py-12 md:py-16">
      <div className="container max-w-6xl mx-auto px-4">
        
        {/* Header Title & Controls */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-10 pb-6 border-b border-white/10">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-white">Forensics Analytics & Audit Log</h1>
              <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium border ${isLive ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-purple-500/20 text-purple-300 border-purple-500/30'}`}>
                {isLive ? `● Live (${data.database_engine || 'Database'})` : 'Demo Dataset'}
              </span>
            </div>
            <p className="text-white/60 text-sm mt-1">Multi-agent consensus history, risk tier breakdown, and policy audit logs.</p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={fetchStats}
              disabled={loading}
              className="text-xs px-3.5 py-2 rounded-lg border border-white/20 bg-white/5 hover:bg-white/10 text-white transition flex items-center gap-1.5"
            >
              <svg className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Refresh
            </button>
            <button
              onClick={handleDownloadCsv}
              className="text-xs px-3.5 py-2 rounded-lg border border-purple-500/30 bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 transition flex items-center gap-1.5"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Export CSV Report
            </button>
            <Link href="/analyze">
              <Button className="text-xs py-2 px-3">New Scan</Button>
            </Link>
          </div>
        </div>

        {/* Top Metric Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} className="p-5 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-sm">
            <span className="text-xs uppercase tracking-wider text-white/50 font-semibold">Total Evaluated</span>
            <div className="text-3xl font-bold text-white mt-1">{data.total_records}</div>
            <span className="text-xs text-white/40 mt-1 block">Processed evidence records</span>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="p-5 rounded-2xl bg-red-500/10 border border-red-500/20 backdrop-blur-sm">
            <span className="text-xs uppercase tracking-wider text-red-400 font-semibold">Fraud Flagged Rate</span>
            <div className="text-3xl font-bold text-red-400 mt-1">{data.flagged_rate_percentage}%</div>
            <span className="text-xs text-red-300/60 mt-1 block">{data.fake_count} flagged as synthetic/forged</span>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="p-5 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 backdrop-blur-sm">
            <span className="text-xs uppercase tracking-wider text-emerald-400 font-semibold">Authentic Media</span>
            <div className="text-3xl font-bold text-emerald-400 mt-1">{data.real_count}</div>
            <span className="text-xs text-emerald-300/60 mt-1 block">Passed zero-trust critic check</span>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="p-5 rounded-2xl bg-purple-500/10 border border-purple-500/20 backdrop-blur-sm">
            <span className="text-xs uppercase tracking-wider text-purple-400 font-semibold">Mean Jury Confidence</span>
            <div className="text-3xl font-bold text-purple-300 mt-1">{(data.avg_confidence * 100).toFixed(1)}%</div>
            <span className="text-xs text-purple-200/60 mt-1 block">Avg latency: {data.avg_processing_time_sec}s</span>
          </motion.div>
        </div>

        {/* Severity Risk Tier Distribution */}
        {data.severity_breakdown && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
            <div className="p-4 rounded-xl bg-red-950/20 border border-red-500/20 text-center">
              <div className="text-[11px] uppercase tracking-wider text-red-400 font-semibold">🚨 Critical Fraud</div>
              <div className="text-2xl font-bold text-red-300 mt-1">{data.severity_breakdown.critical_fraud}</div>
              <span className="text-[10px] text-white/40">Immediate block policy</span>
            </div>
            <div className="p-4 rounded-xl bg-amber-950/20 border border-amber-500/20 text-center">
              <div className="text-[11px] uppercase tracking-wider text-amber-400 font-semibold">⚠️ High Risk</div>
              <div className="text-2xl font-bold text-amber-300 mt-1">{data.severity_breakdown.high_risk}</div>
              <span className="text-[10px] text-white/40">Escalated to senior queue</span>
            </div>
            <div className="p-4 rounded-xl bg-yellow-950/20 border border-yellow-500/20 text-center">
              <div className="text-[11px] uppercase tracking-wider text-yellow-400 font-semibold">🔍 Suspicious</div>
              <div className="text-2xl font-bold text-yellow-300 mt-1">{data.severity_breakdown.suspicious}</div>
              <span className="text-[10px] text-white/40">Step-up verification required</span>
            </div>
            <div className="p-4 rounded-xl bg-emerald-950/20 border border-emerald-500/20 text-center">
              <div className="text-[11px] uppercase tracking-wider text-emerald-400 font-semibold">🛡️ Low Risk</div>
              <div className="text-2xl font-bold text-emerald-300 mt-1">{data.severity_breakdown.low_risk}</div>
              <span className="text-[10px] text-white/40">Automated fast approval</span>
            </div>
          </div>
        )}

        {/* Media Distribution Breakdown */}
        <div className="p-5 rounded-2xl bg-[#0d071b] border border-white/10 mb-8 flex flex-wrap items-center justify-between gap-6">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-white">Media Modality Pipeline:</span>
          </div>
          <div className="flex flex-wrap items-center gap-6 text-xs text-white/70">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-blue-400" />
              <span>Images: <strong className="text-white">{data.media_counts.images}</strong></span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
              <span>Documents (PDF): <strong className="text-white">{data.media_counts.documents}</strong></span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-purple-400" />
              <span>Videos (Keyframes): <strong className="text-white">{data.media_counts.videos}</strong></span>
            </div>
          </div>
        </div>

        {/* Audit Log Table */}
        <div className="rounded-2xl border border-white/10 bg-[#0a0515]/90 backdrop-blur-md overflow-hidden">
          <div className="p-5 border-b border-white/10 flex items-center justify-between">
            <h2 className="text-lg font-bold text-white">Forensic Audit Log</h2>
            <span className="text-xs text-white/40">Showing latest {data.recent_evaluations.length} records</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-white/5 text-white/50 uppercase tracking-wider text-[11px] border-b border-white/10">
                <tr>
                  <th className="py-3.5 px-4 font-semibold">Evidence Name</th>
                  <th className="py-3.5 px-4 font-semibold">Type</th>
                  <th className="py-3.5 px-4 font-semibold">Verdict</th>
                  <th className="py-3.5 px-4 font-semibold">Confidence</th>
                  <th className="py-3.5 px-4 font-semibold">Severity Tier</th>
                  <th className="py-3.5 px-4 font-semibold">Policy Action</th>
                  <th className="py-3.5 px-4 font-semibold">Jury Forensic Findings</th>
                  <th className="py-3.5 px-4 font-semibold">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-white/80">
                {data.recent_evaluations.map((item) => (
                  <tr key={item.id} className="hover:bg-white/[0.02] transition">
                    <td className="py-3.5 px-4 font-medium text-white truncate max-w-[180px]">{item.filename}</td>
                    <td className="py-3.5 px-4">
                      <span className="px-2 py-0.5 rounded bg-white/10 text-white/80 text-[11px]">
                        {item.media_type}
                      </span>
                    </td>
                    <td className="py-3.5 px-4">
                      <span className={`px-2.5 py-0.5 rounded-full font-bold text-[11px] ${item.ai_prediction.toLowerCase() === 'fake' ? 'bg-red-500/20 text-red-400 border border-red-500/30' : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'}`}>
                        {item.ai_prediction}
                      </span>
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-2">
                        <div className="w-14 h-1.5 rounded-full bg-white/10 overflow-hidden">
                          <div 
                            className={`h-full ${item.ai_prediction.toLowerCase() === 'fake' ? 'bg-red-400' : 'bg-emerald-400'}`}
                            style={{ width: `${item.confidence * 100}%` }}
                          />
                        </div>
                        <span className="font-semibold">{(item.confidence * 100).toFixed(0)}%</span>
                      </div>
                    </td>
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      {getTierBadge(item.severity_tier)}
                    </td>
                    <td className="py-3.5 px-4 whitespace-nowrap text-[11px]">
                      {getActionBadge(item.recommended_action)}
                    </td>
                    <td className="py-3.5 px-4 max-w-[280px] truncate text-white/60" title={item.final_reasoning}>
                      {item.final_reasoning}
                    </td>
                    <td className="py-3.5 px-4 text-white/40 whitespace-nowrap">{item.processed_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </section>
  );
};

export default AnalyticsDashboard;
