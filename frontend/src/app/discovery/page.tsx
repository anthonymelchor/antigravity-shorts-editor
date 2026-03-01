"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Flame, Play, CheckCircle, Info, ArrowLeft, ExternalLink, Zap, Sparkles, RefreshCw, Check, Filter } from "lucide-react";
import Link from "next/link";
import { createClientComponentClient } from "@supabase/auth-helpers-nextjs";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface Candidate {
    id: number;
    title: string;
    original_url: string;
    views: number;
    niche: string;
    status: string;
}

export default function DiscoveryPage() {
    const supabase = createClientComponentClient();
    const [candidates, setCandidates] = useState<Candidate[]>([]);
    const [loading, setLoading] = useState(true);
    const [nicheFilter, setNicheFilter] = useState<string | null>(null);

    // Derive unique niches from candidates
    const uniqueNiches = Array.from(new Set(candidates.map(c => c.niche).filter(Boolean)));
    const filteredCandidates = nicheFilter
        ? candidates.filter(c => c.niche === nicheFilter)
        : candidates;
    const [approvingId, setApprovingId] = useState<number | null>(null);

    // Authenticated fetch helper
    const authFetch = async (url: string, options: RequestInit = {}): Promise<Response> => {
        const { data: { session } } = await supabase.auth.getSession();
        if (!session?.access_token) {
            window.location.href = '/login';
            throw new Error('Not authenticated');
        }
        return fetch(url, {
            ...options,
            headers: {
                ...(options.headers || {}),
                'Authorization': `Bearer ${session.access_token}`,
            },
        });
    };


    const [isDiscovering, setIsDiscovering] = useState(false);
    const [discoveryStatus, setDiscoveryStatus] = useState<any>(null);
    const [alert, setAlert] = useState<{ msg: string; type: 'success' | 'error' } | null>(null);

    useEffect(() => {
        let interval: NodeJS.Timeout;
        if (isDiscovering) {
            interval = setInterval(async () => {
                try {
                    const { data: { session } } = await supabase.auth.getSession();
                    const uid = session?.user?.id;
                    const res = await authFetch(`${API_BASE}/api/status?version=discovery_${uid || 'global'}`);
                    const data = await res.json();

                    if (data.status) {
                        setDiscoveryStatus(data);
                    }

                    if (data.status === 'completed' || data.status === 'failed') {
                        setIsDiscovering(false);
                        fetchCandidates();
                        if (data.status === 'completed') {
                            setAlert({ msg: "Neural Trend Discovery Completed! New candidates identified.", type: 'success' });
                        } else {
                            setAlert({ msg: "Engine Error: " + data.message, type: 'error' });
                        }
                        // Reset status after a delay
                        setTimeout(() => setDiscoveryStatus(null), 5000);
                    }
                } catch (err) { console.error("Status check failed", err); }
            }, 2500);
        }
        return () => clearInterval(interval);
    }, [isDiscovering]);

    useEffect(() => {
        checkInitialStatus();
        fetchCandidates();
    }, []);

    const checkInitialStatus = async () => {
        try {
            const { data: { session } } = await supabase.auth.getSession();
            const uid = session?.user?.id;
            const res = await authFetch(`${API_BASE}/api/status?version=discovery_${uid || 'global'}`);
            const data = await res.json();
            if (data.status === 'processing') {
                setIsDiscovering(true);
                setDiscoveryStatus(data);
            }
        } catch (err) { console.error("Initial status check failed", err); }
    };

    const fetchCandidates = async () => {
        try {
            setLoading(true);
            const resp = await authFetch(`${API_BASE}/api/discovery`);
            const data = await resp.json();
            setCandidates(data);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const handleRunDiscovery = async () => {
        setIsDiscovering(true);
        // Set an immediate status so the blue bar shows up instantly
        setDiscoveryStatus({
            status: 'processing',
            message: 'Iniciando Motor Neural...',
            progress: 5,
            version: 'Iniciando...'
        });
        setAlert(null);
        try {
            const res = await authFetch(`${API_BASE}/api/discovery/run`, { method: 'POST' });
            if (!res.ok) {
                const data = await res.json();
                setAlert({ msg: data.detail || 'Error starting discovery', type: 'error' });
                setIsDiscovering(false);
                setDiscoveryStatus(null);
            }
            // If res.ok, the interval will take over polling from the server
        } catch (err) {
            setAlert({ msg: 'Failed to connect to server', type: 'error' });
            setIsDiscovering(false);
            setDiscoveryStatus(null);
        }
    };

    const handleApprove = async (id: number) => {
        const candidate = candidates.find(c => c.id === id);
        if (!candidate) return;

        setApprovingId(id);
        try {
            // 1. Mark as approved in DB (with auth)
            const resp = await authFetch(`${API_BASE}/api/discovery/approve/${id}`, {
                method: "POST",
            });

            if (resp.ok) {
                // 2. Trigger the actual video pipeline
                await authFetch(`${API_BASE}/api/process`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        url: candidate.original_url
                    })
                });

                setCandidates((prev) => prev.filter((c) => c.id !== id));
                // 3. User feedback: Redirect to dashboard to see the progress
                window.location.href = '/';
            }
        } catch (err) {
            console.error("Failed to approve", err);
        } finally {
            setApprovingId(null);
        }
    };

    return (
        <div className="min-h-screen bg-black text-white p-8 selection:bg-white/10 font-sans">
            <div className="max-w-6xl mx-auto">
                {/* Header */}
                <div className="flex items-center justify-between mb-16 border-b border-white/5 pb-12">
                    <div>
                        <Link href="/" className="inline-flex items-center text-[10px] font-black uppercase tracking-widest text-neutral-500 hover:text-white mb-6 transition-colors">
                            <ArrowLeft className="w-4 h-4 mr-2" /> Volver al Motor
                        </Link>
                        <h1 className="text-6xl font-black tracking-tighter uppercase">
                            Discovery Engine
                        </h1>
                        <p className="text-neutral-500 mt-4 font-bold uppercase tracking-widest text-[10px]">Neural AI Trend Analysis • RocotoClip</p>
                    </div>
                    <div className="flex gap-4">
                        <div className="bg-white/5 border border-white/10 px-6 py-3 rounded-full flex items-center gap-3">
                            <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
                            <span className="text-[10px] font-black tracking-widest uppercase">Engine Active</span>
                        </div>
                    </div>
                </div>
                {/* MANUAL DISCOVERY CONTROLS */}
                <div className="bg-[#0a0a0a] border border-white/5 rounded-[2.5rem] p-8 mb-12 flex flex-col md:flex-row items-center justify-between gap-6 shadow-2xl transition-all">
                    <div className="flex-1">
                        <div className="flex items-center gap-3 mb-2">
                            <Sparkles className="w-5 h-5 text-amber-500" />
                            <h2 className="text-xl font-bold">Discovery Engine</h2>
                        </div>
                        <p className="text-neutral-500 text-[10px] font-bold uppercase tracking-widest">Escaneando contenido viral en tiempo real</p>
                    </div>

                    <div className="flex items-center gap-4 bg-black/40 p-2 rounded-3xl border border-white/5">

                        <button
                            onClick={handleRunDiscovery}
                            disabled={isDiscovering}
                            className={`flex items-center gap-3 bg-white text-black px-8 py-4 rounded-2xl font-black uppercase text-[10px] tracking-widest transition-all shadow-[0_10px_40px_rgba(255,255,255,0.05)] active:scale-95
                                ${isDiscovering ? 'opacity-70 cursor-wait bg-neutral-200' : 'hover:bg-neutral-200'}`}
                        >
                            {isDiscovering ? (
                                <div className="w-3 h-3 border-2 border-black/30 border-t-black rounded-full animate-spin" />
                            ) : <RefreshCw className="w-4 h-4" />}
                            {isDiscovering ? (discoveryStatus?.message || 'Escaneando...') : 'Descubrir Ahora'}
                        </button>
                    </div>
                </div>

                {discoveryStatus && isDiscovering && (
                    <div className="mb-12 bg-[#0a0a0a] border border-white/5 rounded-[2.5rem] p-10 animate-in fade-in zoom-in duration-500 shadow-2xl overflow-hidden relative">
                        <div className="flex justify-between items-center mb-6 relative z-10">
                            <div>
                                <span className="text-[10px] font-black uppercase tracking-[0.2em] text-sky-500 mb-1 block">Neural Analysis</span>
                                <h3 className="text-xl font-bold text-white uppercase tracking-tighter">Current Search Status</h3>
                            </div>
                            <div className="text-right">
                                <span className="text-2xl font-black text-white">{discoveryStatus.progress}%</span>
                                <span className="text-[10px] block font-bold text-neutral-500 uppercase tracking-widest">Processed</span>
                            </div>
                        </div>

                        <div className="relative h-6 bg-black rounded-xl border border-white/5 p-1 overflow-hidden sm:h-8">
                            <div
                                className="h-full bg-sky-500 rounded-lg transition-all duration-1000 ease-out relative shadow-[0_0_20px_rgba(14,165,233,0.3)]"
                                style={{ width: `${discoveryStatus.progress}%` }}
                            >
                                <div className="absolute top-0 bottom-0 left-0 right-0 bg-white/20 animate-pulse rounded-lg" />
                                <div className="absolute top-0 bottom-0 bg-white animate-[loadingLine_2s_infinite_linear] w-[40%] skew-x-[-20deg] opacity-40 blur-sm shadow-[0_0_30px_rgba(255,255,255,0.8)]" />
                            </div>
                        </div>

                        <div className="mt-8 flex items-center justify-between border-t border-white/5 pt-6">
                            <div className="flex items-center gap-3">
                                <div className="w-1.5 h-1.5 rounded-full bg-sky-500 animate-pulse" />
                                <p className="text-[10px] font-black uppercase tracking-[0.15em] text-neutral-400">
                                    {discoveryStatus.message || 'Scanning Content Pools...'}
                                </p>
                            </div>
                            <span className="text-[9px] font-bold text-neutral-600 uppercase tracking-widest">Thread: {discoveryStatus.version}</span>
                        </div>
                    </div>
                )}

                {alert && (
                    <div className={`mb-12 p-6 rounded-[2rem] border animate-in fade-in slide-in-from-top-4 duration-500 flex items-center justify-between
                        ${alert.type === 'error' ? 'bg-red-500/10 border-red-500/10 text-red-500/90' : 'bg-green-500/10 border-green-500/10 text-green-500/90'}`}>
                        <div className="flex items-center gap-3">
                            <Check className="w-4 h-4" />
                            <p className="text-xs font-bold tracking-tight">{alert.msg}</p>
                        </div>
                        <button onClick={() => setAlert(null)} className="text-[10px] font-black uppercase tracking-widest opacity-50 hover:opacity-100 transition-opacity px-4">Cerrar</button>
                    </div>
                )}

                {loading ? (
                    <div className="flex flex-col items-center justify-center h-96">
                        <div className="relative w-16 h-16 mb-8">
                            <div className="absolute inset-0 rounded-full border-4 border-sky-500/20" />
                            <div className="absolute inset-0 rounded-full border-4 border-sky-500 border-t-transparent animate-spin shadow-[0_0_15px_rgba(14,165,233,0.3)]" />
                            <Sparkles className="absolute inset-0 m-auto w-6 h-6 text-sky-500 animate-pulse" />
                        </div>
                        <span className="text-[10px] font-black tracking-[0.3em] uppercase text-sky-500 animate-pulse">Sincronizando Tendencias...</span>
                        <span className="text-neutral-500 text-[8px] font-bold uppercase tracking-widest mt-2">Consultando Engine Neural</span>
                    </div>
                ) : (
                    <>
                        {/* NICHE FILTER BAR */}
                        {uniqueNiches.length > 1 && (
                            <div className="flex items-center gap-3 mb-8 flex-wrap">
                                <div className="flex items-center gap-2 text-neutral-600 mr-2">
                                    <Filter className="w-3.5 h-3.5" />
                                    <span className="text-[10px] font-black uppercase tracking-widest">Filtrar</span>
                                </div>
                                <button
                                    onClick={() => setNicheFilter(null)}
                                    className={`px-5 py-2 rounded-full text-[10px] font-black uppercase tracking-widest border transition-all
                                        ${!nicheFilter
                                            ? 'bg-white text-black border-white shadow-[0_0_15px_rgba(255,255,255,0.1)]'
                                            : 'bg-transparent text-neutral-500 border-white/10 hover:border-white/20 hover:text-white'}`}
                                >
                                    Todos ({candidates.length})
                                </button>
                                {uniqueNiches.map(niche => {
                                    const count = candidates.filter(c => c.niche === niche).length;
                                    return (
                                        <button
                                            key={niche}
                                            onClick={() => setNicheFilter(niche)}
                                            className={`px-5 py-2 rounded-full text-[10px] font-black uppercase tracking-widest border transition-all
                                                ${nicheFilter === niche
                                                    ? 'bg-white text-black border-white shadow-[0_0_15px_rgba(255,255,255,0.1)]'
                                                    : 'bg-transparent text-neutral-500 border-white/10 hover:border-white/20 hover:text-white'}`}
                                        >
                                            {niche} ({count})
                                        </button>
                                    );
                                })}
                            </div>
                        )}

                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                            <AnimatePresence mode="popLayout">
                                {filteredCandidates.map((c) => (
                                    <motion.div
                                        key={c.id}
                                        layout
                                        initial={{ opacity: 0, y: 20 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0, scale: 0.95 }}
                                        className="group bg-[#0a0a0a] border border-white/5 rounded-[2.5rem] p-8 hover:border-white/10 transition-all duration-500 relative overflow-hidden"
                                    >
                                        <div className="flex justify-between items-start mb-6">
                                            <span className="bg-white/5 text-neutral-400 text-[10px] font-black tracking-widest uppercase px-4 py-1.5 rounded-full border border-white/5">
                                                {c.niche}
                                            </span>
                                            <div className="flex items-center gap-1.5 text-neutral-500 group-hover:text-white transition-colors">
                                                <Flame className="w-4 h-4" />
                                                <span className="text-xs font-black">{c.views >= 1000000 ? `${(c.views / 1000000).toFixed(1)}M` : `${(c.views / 1000).toFixed(0)}K`}</span>
                                            </div>
                                        </div>

                                        <h3 className="text-xl font-bold leading-tight mb-8 group-hover:text-white transition-colors line-clamp-2">
                                            {c.title}
                                        </h3>

                                        <div className="flex items-center gap-3">
                                            <button
                                                onClick={() => handleApprove(c.id)}
                                                disabled={approvingId === c.id}
                                                className="flex-1 bg-white text-black font-black text-[10px] uppercase tracking-widest py-4 rounded-2xl hover:bg-neutral-200 transition-all transform active:scale-95 disabled:opacity-20 flex items-center justify-center gap-2"
                                            >
                                                {approvingId === c.id ? "SIEMBRA..." : (
                                                    <>
                                                        <span>Procesar Ahora</span>
                                                        <Zap className="w-3 h-3 fill-current" />
                                                    </>
                                                )}
                                            </button>
                                            <a
                                                href={c.original_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="p-4 bg-white/5 rounded-2xl border border-white/5 hover:bg-white/10 hover:border-white/20 transition-all text-neutral-600 hover:text-white"
                                            >
                                                <ExternalLink className="w-4 h-4" />
                                            </a>
                                        </div>
                                    </motion.div>
                                ))}
                            </AnimatePresence>
                        </div>
                    </>
                )}

                {candidates.length === 0 && !loading && (
                    <div className="text-center py-32 bg-[#0a0a0a] rounded-[3rem] border border-dashed border-white/5">
                        <Info className="w-12 h-12 text-neutral-800 mx-auto mb-6" />
                        <h2 className="text-sm font-black text-neutral-600 uppercase tracking-[0.3em]">No hay contenido nuevo</h2>
                        <p className="text-neutral-700 mt-2 text-xs font-medium uppercase tracking-widest">El motor está explorando nuevas tendencias...</p>
                    </div>
                )}
            </div>
        </div>
    );
}
