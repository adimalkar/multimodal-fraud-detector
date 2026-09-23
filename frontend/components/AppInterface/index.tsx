/* eslint-disable @typescript-eslint/no-explicit-any */
'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import Button from '../Button';

const AppInterface = () => {
  const [file, setFile] = useState<File | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<any>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
      setResult(null);
    }
  };

  const handleUpload = () => {
    if (!file) return;
    setAnalyzing(true);
    // Simulate multi-agent processing delay
    setTimeout(() => {
      setAnalyzing(false);
      setResult({
        classification: 'Fake',
        confidence: 0.98,
        reason: 'Microscopic artifacts in the reflection pattern and impossible geometry detected by critics.',
        votes: [
          { model: 'Qwen-VL-Plus (Vision)', vote: 'Fake', conf: 0.95 },
          { model: 'Qwen Turbo', vote: 'Fake', conf: 0.99 },
          { model: 'DeepSeek R1', vote: 'Fake', conf: 0.98 },
          { model: 'GLM 4.6', vote: 'Real', conf: 0.60 },
        ]
      });
    }, 3500);
  };

  return (
    <section id="app-interface" className="py-20 md:py-24 relative">
      <div className="container relative z-10">
        <h2 className="text-4xl md:text-5xl font-semibold text-center tracking-tighter mb-12">
          Verify Media Authenticity
        </h2>

        <div className="max-w-4xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-8">
          
          {/* Upload Column */}
          <div className="flex flex-col gap-4">
            <div 
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              className="border-2 border-dashed border-white/20 rounded-2xl bg-white/5 backdrop-blur-md p-10 flex flex-col items-center justify-center min-h-[300px] hover:border-[#8c45ff] transition-colors"
            >
              <div className="h-16 w-16 rounded-full bg-white/10 flex items-center justify-center mb-4">
                <svg className="w-8 h-8 text-white/70" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
              </div>
              <p className="text-white/70 text-center mb-2">
                Drag and drop your image, video, or PDF here
              </p>
              <input 
                type="file" 
                className="hidden" 
                id="file-upload" 
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    setFile(e.target.files[0]);
                    setResult(null);
                  }
                }} 
              />
              <label htmlFor="file-upload" className="cursor-pointer text-[#8c45ff] hover:text-[#a875ff] font-medium transition-colors">
                or browse files
              </label>
              
              {file && (
                <div className="mt-6 p-3 bg-white/10 rounded-lg w-full flex items-center justify-between">
                  <span className="text-sm truncate text-white">{file.name}</span>
                  <span className="text-xs text-white/50">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                </div>
              )}
            </div>

            <Button onClick={handleUpload} className="w-full justify-center">
              {analyzing ? 'Agents Analyzing...' : 'Analyze Evidence'}
            </Button>
          </div>

          {/* Results Column */}
          <div className="border border-white/10 rounded-2xl bg-[#0a0515]/80 backdrop-blur-md p-8 relative overflow-hidden">
            {!analyzing && !result && (
              <div className="flex flex-col items-center justify-center h-full text-white/30 text-center">
                <svg className="w-12 h-12 mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
                <p>Upload a file to see the multi-agent forensics report here.</p>
              </div>
            )}

            {analyzing && (
              <div className="flex flex-col h-full gap-4 pt-4">
                <motion.div 
                  initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }}
                  className="flex items-center gap-3 text-sm text-white/70"
                >
                  <div className="h-2 w-2 rounded-full bg-[#8c45ff] animate-pulse" />
                  Qwen-VL extracting visual anomalies...
                </motion.div>
                <motion.div 
                  initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 1 }}
                  className="flex items-center gap-3 text-sm text-white/70"
                >
                  <div className="h-2 w-2 rounded-full bg-[#8c45ff] animate-pulse" />
                  DeepSeek checking consistency matrices...
                </motion.div>
                <motion.div 
                  initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 2 }}
                  className="flex items-center gap-3 text-sm text-white/70"
                >
                  <div className="h-2 w-2 rounded-full bg-[#8c45ff] animate-pulse" />
                  Jury system calculating consensus...
                </motion.div>
              </div>
            )}

            {result && (
              <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="flex flex-col gap-6">
                <div className={`p-4 rounded-xl border ${result.classification === 'Fake' ? 'bg-red-500/10 border-red-500/30' : 'bg-green-500/10 border-green-500/30'}`}>
                  <div className="text-xs font-bold tracking-widest uppercase text-white/50 mb-1">Final Verdict</div>
                  <div className={`text-4xl font-bold ${result.classification === 'Fake' ? 'text-red-400' : 'text-green-400'}`}>
                    {result.classification}
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-white/70">Confidence Score</span>
                    <span className="font-bold text-white">{result.confidence * 100}%</span>
                  </div>
                  <div className="h-2 bg-white/10 rounded-full overflow-hidden">
                    <motion.div 
                      initial={{ width: 0 }} animate={{ width: `${result.confidence * 100}%` }} 
                      className={`h-full ${result.classification === 'Fake' ? 'bg-red-500' : 'bg-green-500'}`} 
                    />
                  </div>
                </div>

                <div>
                  <div className="text-sm font-semibold mb-3 text-white">Agent Jury Breakdown</div>
                  <div className="space-y-2">
                    {result.votes.map((v: any, i: number) => (
                      <div key={i} className="flex items-center justify-between bg-white/5 p-2 rounded-md text-xs">
                        <span className="text-white/80">{v.model}</span>
                        <div className="flex items-center gap-2">
                          <span className={`${v.vote === 'Fake' ? 'text-red-400' : 'text-green-400'}`}>{v.vote}</span>
                          <span className="text-white/40">{(v.conf * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="text-sm text-white/80 leading-relaxed p-3 bg-[#190d2e] rounded-lg border border-[#8c45ff]/20">
                  <span className="text-[#8c45ff] font-semibold">Executive Summary: </span>
                  {result.reason}
                </div>
              </motion.div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
};

export default AppInterface;
