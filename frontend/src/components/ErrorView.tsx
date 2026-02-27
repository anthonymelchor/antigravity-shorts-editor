'use client';

import React from 'react';
import { ShieldAlert } from 'lucide-react';

export function ErrorView() {
    return (
        <div className="min-h-screen bg-black text-white font-sans flex flex-col items-center justify-center p-8 relative overflow-hidden">

            {/* Background Branding (Disabled Dashboard Aesthetic) */}
            <div className="mb-12 flex flex-col items-center opacity-20 pointer-events-none">
                <h1 className="text-5xl font-bold tracking-tighter uppercase text-white">RocotoClip</h1>
            </div>

            <div className="w-full max-w-2xl opacity-20 pointer-events-none mb-24">
                <div className="bg-[#0a0a0a] rounded-[2.5rem] border border-white/10 p-2">
                    <div className="px-20 py-10 text-xl font-medium text-neutral-700">
                        Drop a YouTube link
                    </div>
                    <div className="flex items-center justify-between px-8 py-6 border-t border-white/5 bg-black/40 rounded-b-[2.3rem]">
                        <div className="w-24 h-4 bg-white/5 rounded" />
                        <div className="w-32 h-12 bg-white/5 rounded-2xl" />
                    </div>
                </div>
            </div>

            {/* Minimal Error Footer */}
            <div className="fixed bottom-12 left-1/2 -translate-x-1/2 w-full max-w-md animate-in fade-in slide-in-from-bottom-4 duration-1000 z-[999]">
                <div className="bg-[#0a0a0a] border border-red-500/20 px-8 py-6 rounded-[2.5rem] flex items-center gap-6 shadow-2xl">
                    <div className="w-12 h-12 bg-red-500/10 rounded-full flex items-center justify-center shrink-0">
                        <ShieldAlert className="w-6 h-6 text-red-500" />
                    </div>
                    <div className="flex flex-col">
                        <div className="flex items-center gap-2">
                            <span className="text-[10px] font-black uppercase text-red-500 tracking-widest">System Error</span>
                            <div className="w-1 h-1 bg-red-500 rounded-full animate-pulse" />
                        </div>
                        <span className="text-xs font-bold text-neutral-400 leading-relaxed">
                            Estamos trabajando para solucionarlo. El motor se reiniciará automáticamente.
                        </span>
                    </div>
                </div>
            </div>

        </div>
    );
}
