'use client';

import React, { useState, useEffect } from 'react';
import {
    Download,
    Link as LinkIcon,
    Youtube,
    X,
    Clock,
    Loader2,
    Check,
    ChevronRight,
    ArrowLeft,
    Monitor,
} from 'lucide-react';
import Link from 'next/link';
import { createClientComponentClient } from '@supabase/auth-helpers-nextjs';
import { useRouter } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export default function VideoDownloadsPage() {
    const [url, setUrl] = useState('');
    const [downloads, setDownloads] = useState<any[]>([]);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [alert, setAlert] = useState<{ msg: string; type: 'error' | 'success' } | null>(null);

    const router = useRouter();
    const supabase = createClientComponentClient();
    const [authToken, setAuthToken] = useState<string | null>(null);

    useEffect(() => {
        supabase.auth.getSession().then(({ data: { session } }) => {
            if (session?.access_token) {
                setAuthToken(session.access_token);
            }
        });
    }, [supabase]);

    const authFetch = async (url: string, options: RequestInit = {}): Promise<Response> => {
        const { data: { session } } = await supabase.auth.getSession();
        if (!session?.access_token) {
            router.push('/login');
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

    const fetchDownloads = async () => {
        try {
            const res = await authFetch(`${API_BASE}/api/downloads`);
            const data = await res.json();
            if (Array.isArray(data)) {
                setDownloads(data);
            }
        } catch (err) {
            console.error("Failed to fetch downloads", err);
        }
    };

    useEffect(() => {
        fetchDownloads();
        const interval = setInterval(fetchDownloads, 2000);
        return () => clearInterval(interval);
    }, []);

    const handleDownload = async () => {
        if (!url.trim()) return;
        setIsSubmitting(true);
        try {
            const res = await authFetch(`${API_BASE}/api/downloads`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url.trim() })
            });
            const data = await res.json();
            if (data.status === 'success') {
                setAlert({ msg: "Video añadido a la cola de descarga", type: 'success' });
                setUrl('');
                fetchDownloads();
            } else {
                setAlert({ msg: data.detail || "Error al iniciar descarga", type: 'error' });
            }
        } catch (err: any) {
            setAlert({ msg: err.message, type: 'error' });
        } finally {
            setIsSubmitting(false);
            setTimeout(() => setAlert(null), 4000);
        }
    };

    return (
        <main className="min-h-screen bg-[#050505] text-white font-sans flex flex-col items-center p-8 pt-32 selection:bg-purple-500/30">
            {/* STUNNING HEADER */}
            <header className="fixed top-0 left-0 w-full border-b border-white/5 px-12 py-6 flex justify-between items-center bg-black/50 backdrop-blur-md z-[60]">
                <div className="flex items-center gap-4">
                    <Link href="/" className="hover:opacity-80 transition-opacity">
                        <h1 className="text-2xl font-bold tracking-tighter uppercase">RocotoClip</h1>
                    </Link>
                    <div className="h-4 w-px bg-white/10" />
                    <nav className="flex gap-6 text-[10px] font-black uppercase tracking-widest text-neutral-500">
                        <Link href="/" className="hover:text-white transition-colors flex items-center gap-2">
                            Dashboard
                        </Link>
                        <Link href="/discovery" className="hover:text-white transition-colors flex items-center gap-2">
                            Discovery Engine
                        </Link>
                        <span className="text-purple-400 flex items-center gap-2">
                            <Download className="w-3 h-3" />
                            Descargas
                        </span>
                    </nav>
                </div>
            </header>

            {/* INPUT SECTION - DEEP PURPLE ACCENT */}
            <div className="w-full max-w-2xl relative z-10 mb-20 animate-in fade-in slide-in-from-top-10 duration-1000">
                <div className="bg-[#0a0a0a] rounded-[2.5rem] border border-purple-500/20 p-2 shadow-[0_0_100px_rgba(168,85,247,0.05)]">
                    <div className="relative group">
                        <div className="absolute left-8 top-1/2 -translate-y-1/2 text-neutral-600 group-focus-within:text-purple-400 transition-colors duration-300">
                            <LinkIcon className="w-5 h-5" />
                        </div>
                        <input
                            type="text"
                            placeholder="Sube un link de YouTube para descargar"
                            className="w-full bg-transparent border-none px-20 py-10 text-xl font-medium outline-none placeholder:text-neutral-700 transition-all"
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleDownload()}
                        />
                        <button
                            onClick={handleDownload}
                            disabled={isSubmitting || !url.trim()}
                            className={`absolute right-4 top-1/2 -translate-y-1/2 bg-purple-600 text-white px-8 py-4 rounded-3xl font-black uppercase text-[10px] tracking-widest transition-all shadow-[0_10px_40px_rgba(168,85,247,0.3)] active:scale-95 flex items-center gap-2
                                ${isSubmitting ? 'opacity-50 cursor-wait' : 'hover:bg-purple-500 cursor-pointer disabled:opacity-30 disabled:grayscale'}`}
                        >
                            {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                            {isSubmitting ? 'Iniciando...' : 'Descargar'}
                        </button>
                    </div>
                </div>

                {alert && (
                    <div className="absolute -bottom-16 left-1/2 -translate-x-1/2 w-full flex justify-center">
                        <div className={`px-6 py-2 rounded-full border text-[10px] font-bold uppercase tracking-widest animate-in fade-in slide-in-from-top-2
                            ${alert.type === 'error' ? 'bg-red-500/10 border-red-500/20 text-red-400' : 'bg-purple-500/10 border-purple-500/20 text-purple-400'}`}>
                            {alert.msg}
                        </div>
                    </div>
                )}
            </div>

            {/* QUEUE DISPLAY - FLASHCARD GRID */}
            <div className="w-full max-w-6xl flex flex-col gap-10 animate-in fade-in slide-in-from-bottom-10 duration-1000 delay-200">
                <div className="flex items-center justify-between border-b border-white/5 pb-6">
                    <div className="flex items-center gap-4">
                        <h2 className="text-sm font-black uppercase tracking-widest text-neutral-500">Fila de Descargas</h2>
                        <div className="bg-purple-500/10 px-3 py-1 rounded-lg text-[10px] font-bold text-purple-400 border border-purple-500/20">
                            {downloads.length}
                        </div>
                    </div>
                    <div className="flex items-center gap-2 text-[9px] font-bold text-neutral-600 uppercase tracking-tighter">
                        Capacidad máxima: 2K Video @ 60fps
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {downloads.length === 0 ? (
                        <div className="col-span-full py-32 flex flex-col items-center justify-center border-2 border-dashed border-white/5 rounded-[3rem] opacity-30">
                            <Youtube className="w-20 h-20 mb-6" />
                            <p className="font-bold text-neutral-500 uppercase tracking-widest text-xs">No hay descargas activas</p>
                        </div>
                    ) : (
                        downloads.map((dl, idx) => (
                            <div key={idx} className="bg-[#0a0a0a] border border-white/5 rounded-[2.5rem] p-8 flex flex-col h-64 shadow-2xl relative overflow-hidden group">
                                {/* PROGRESS BAR BACKGROUND */}
                                {dl.status === 'downloading' && (
                                    <div className="absolute top-0 left-0 bottom-0 bg-purple-600/5 transition-all duration-1000 ease-out" style={{ width: `${dl.progress}%` }} />
                                )}

                                <div className="flex-1 flex flex-col z-10">
                                    <div className="flex justify-between items-start mb-6">
                                        <div className={`p-3 rounded-2xl ${dl.status === 'completed' ? 'bg-green-500/10 text-green-500' : dl.status === 'failed' ? 'bg-red-500/10 text-red-500' : 'bg-purple-500/10 text-purple-400'}`}>
                                            {dl.status === 'completed' ? <Check className="w-5 h-5" /> :
                                                dl.status === 'failed' ? <X className="w-5 h-5" /> :
                                                    dl.status === 'downloading' ? <Loader2 className="w-5 h-5 animate-spin" /> :
                                                        <Clock className="w-5 h-5" />}
                                        </div>
                                        <span className={`text-[8px] font-black uppercase tracking-widest px-3 py-1 rounded-full border
                                            ${dl.status === 'completed' ? 'border-green-500/20 text-emerald-500' :
                                                dl.status === 'failed' ? 'border-red-500/20 text-red-500' :
                                                    'border-purple-500/20 text-purple-400'}`}>
                                            {dl.status === 'queued' ? 'En espera' : dl.status}
                                        </span>
                                    </div>

                                    <h3 className="text-sm font-bold text-white mb-2 line-clamp-2 leading-relaxed">
                                        {dl.title || "Procesando metadatos..."}
                                    </h3>
                                    <p className="text-[10px] text-neutral-600 truncate mb-auto">
                                        {dl.url}
                                    </p>
                                </div>

                                <div className="mt-6 flex flex-col gap-4 z-10">
                                    {(dl.status === 'downloading' || dl.status === 'queued') && (
                                        <div className="w-full">
                                            <div className="flex justify-between items-center mb-2">
                                                <span className="text-[9px] font-black text-neutral-500 uppercase">Progreso</span>
                                                <span className="text-[10px] font-black text-purple-400 tabular-nums">{dl.progress}%</span>
                                            </div>
                                            <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
                                                <div
                                                    className="h-full bg-purple-600 transition-all duration-700 shadow-[0_0_10px_rgba(168,85,247,0.5)]"
                                                    style={{ width: `${dl.progress}%` }}
                                                />
                                            </div>
                                        </div>
                                    )}

                                    {dl.status === 'completed' && (
                                        <div className="flex items-center gap-2 text-emerald-500/80">
                                            <Monitor className="w-3 h-3" />
                                            <span className="text-[9px] font-black uppercase tracking-widest">Disponible en /videos</span>
                                        </div>
                                    )}

                                    {dl.status === 'failed' && (
                                        <p className="text-[9px] text-red-400 font-medium truncate italic">{dl.error || "Se produjo un error durante la descarga"}</p>
                                    )}
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </div>

            <footer className="py-32 text-center opacity-[0.03] select-none pointer-events-none">
                <h2 className="text-[12rem] font-black tracking-[-0.05em] uppercase italic text-purple-500">Downloader</h2>
            </footer>
        </main>
    );
}
