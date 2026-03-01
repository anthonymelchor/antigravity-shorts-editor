'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Player, PlayerRef } from '@remotion/player';
import { Main } from '../remotion/Composition';
import {
    Youtube,
    Upload,
    RotateCcw,
    Settings,
    ShieldAlert,
    Link as LinkIcon,
    Cloud,
    ChevronRight,
    Play,
    ThumbsUp,
    ThumbsDown,
    Download,
    ExternalLink,
    Edit2,
    Scissors,
    Zap,
    Layout,
    Video,
    Check,
    LogOut,
    Sparkles,
    Trash2,
    X
} from 'lucide-react';
import Link from 'next/link';
import { createClientComponentClient } from '@supabase/auth-helpers-nextjs';
import { useRouter } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export default function Home() {
    const [url, setUrl] = useState('');
    const [view, setView] = useState<'dashboard' | 'results' | 'editor'>('dashboard');
    const [status, setStatus] = useState({
        status: 'idle',
        progress: 0,
        message: 'Ready',
        error: null as string | null,
        version: null as string | null
    });
    const [transcript, setTranscript] = useState<any>(null);
    const [selectedClipIdx, setSelectedClipIdx] = useState(0);
    const [selectedForRender, setSelectedForRender] = useState<number[]>([]);
    const [preferredLanguage, setPreferredLanguage] = useState<'en' | 'es'>('es');
    const [projects, setProjects] = useState<any[]>([]);
    const [showDeleteModal, setShowDeleteModal] = useState<string | null>(null);
    const [alert, setAlert] = useState<{ msg: string; type: 'error' | 'warning' } | null>(null);
    const [activeUrl, setActiveUrl] = useState<string | null>(null);
    const [currentVersion, setCurrentVersion] = useState<string | null>(null);
    const [isLaunching, setIsLaunching] = useState(false);
    const processingRef = useRef<string | null>(null);
    const versionRef = useRef<string | null>(null);
    const playerRef = useRef<PlayerRef>(null);
    const pendingDeletions = useRef<Set<string>>(new Set());

    const router = useRouter();
    const supabase = createClientComponentClient();

    // Authenticated fetch helper — sends Supabase JWT token on every API call
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

    useEffect(() => {
        fetchProjects();
    }, []);

    const fetchProjects = async () => {
        try {
            const res = await authFetch(`${API_BASE}/api/projects`);
            const data = await res.json();
            if (Array.isArray(data)) {
                const failedProj = data.find(p => p.status === 'failed');
                if (failedProj && !pendingDeletions.current.has(failedProj.version)) {
                    setAlert({ msg: "Hubo un inconveniente, intenta de nuevo en unos minutos.", type: 'error' });
                    pendingDeletions.current.add(failedProj.version);
                    authFetch(`${API_BASE}/api/project/${failedProj.version}`, { method: 'DELETE' });
                }

                if (versionRef.current && data.find(p => String(p.version) === String(versionRef.current))) {
                    setIsLaunching(false);
                    versionRef.current = null;
                }

                setProjects(data.filter(p => p.status !== 'failed'));
            }
        } catch (err) {
            console.error("Failed to fetch projects", err);
            setProjects([]);
        }
    };

    const handleLogout = async () => {
        await supabase.auth.signOut();
        router.push('/login');
        router.refresh();
    };

    useEffect(() => {
        checkInitialStatus();
    }, []);

    const checkInitialStatus = async () => {
        // SECURITY: No longer loads global transcript. Projects are loaded explicitly via loadProject().
        // This function now only checks for an active processing state.
    };

    useEffect(() => {
        if (alert && alert.type === 'warning') {
            const timer = setTimeout(() => setAlert(null), 6000);
            return () => clearTimeout(timer);
        }
    }, [alert]);

    useEffect(() => {
        let interval: NodeJS.Timeout;
        if (status.status !== 'idle' && status.status !== 'completed' && status.status !== 'failed') {
            interval = setInterval(async () => {
                try {
                    const res = await authFetch(`${API_BASE}/api/status${status.version ? `?version=${status.version}` : ''}`);
                    const data = await res.json();
                    setStatus(data);

                    if ((data.status === 'completed' || data.status === 'failed') && String(data.version) === String(versionRef.current)) {
                        processingRef.current = null;
                        versionRef.current = null;
                        setCurrentVersion(null);
                        checkInitialStatus();
                        fetchProjects();
                    }
                } catch (err) { console.error("Poll failed", err); }
            }, 2000);
        }
        return () => clearInterval(interval);
    }, [status.status, status.version]);

    useEffect(() => {
        let interval: NodeJS.Timeout;
        if (view === 'dashboard') {
            fetchProjects();
            interval = setInterval(fetchProjects, isLaunching ? 1000 : 3000);
        }
        return () => clearInterval(interval);
    }, [view, isLaunching]);

    const handleProcess = async () => {
        if (!url.trim()) return;

        const { data: { session } } = await supabase.auth.getSession();

        const alreadyProcessing = projects.find(p => p.isActive && p.url === url.trim());
        if (alreadyProcessing) {
            setAlert({ msg: `Este video ya está siendo procesado: "${alreadyProcessing.title || 'Proyecto'}"`, type: 'warning' });
            setView('dashboard');
            return;
        }

        try {
            setAlert(null);
            setIsLaunching(true);
            setActiveUrl(url.trim());
            processingRef.current = url.trim();

            setStatus({ status: 'processing', progress: 0, message: 'Waking up engine...', error: null, version: null });
            setTranscript(null);

            const res = await authFetch(`${API_BASE}/api/process`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url.trim() })
            });
            const data = await res.json();

            if (data.version) {
                setCurrentVersion(String(data.version));
                versionRef.current = String(data.version);
                await fetchProjects();
            }

            setView('dashboard');
        } catch (err: any) {
            console.error(err);
            processingRef.current = null;
            versionRef.current = null;
            setCurrentVersion(null);
            setStatus({ status: 'failed', progress: 0, message: 'Network Error', error: err.message, version: null });
            setAlert({ msg: "Hubo un inconveniente, intenta de nuevo en unos minutos.", type: 'error' });
            setIsLaunching(false);
        }
    };

    const handleReset = async () => {
        if (!confirm("CONFIRMAR: ¿Deseas eliminar únicamente TUS proyectos activos de la lista?")) return;
        try {
            await authFetch(`${API_BASE}/api/reset`, { method: 'POST' });
            setTranscript(null); setUrl('');
            setStatus({ status: 'idle', progress: 0, message: 'Project Cleared', error: null, version: null });
            setView('dashboard');
            fetchProjects();
        } catch (err: any) { console.error(err); }
    };

    const handleDeleteProject = async (version: string) => {
        try {
            await authFetch(`${API_BASE}/api/project/${version}`, { method: 'DELETE' });
            setShowDeleteModal(null);
            fetchProjects();
            if (transcript?.version === version) {
                setTranscript(null);
                setStatus({ status: 'idle', progress: 0, message: 'Ready', error: null, version: null });
            }
        } catch (err: any) { console.error(err); }
    };

    const loadProject = async (version: string) => {
        try {
            const res = await authFetch(`${API_BASE}/api/transcript/${version}`);
            const data = await res.json();
            if (data && !data.error) {
                setTranscript(data);
                setStatus({ status: 'completed', progress: 100, message: 'Loaded', error: null, version: data.version });
                setView('results');
            }
        } catch (err) { console.error("Failed to load project", err); }
    };

    const removeEmoji = (idxToRemove: number) => {
        if (!transcript) return;
        const newTranscript = { ...transcript };
        const clipIcons = newTranscript?.clips?.[selectedClipIdx]?.edit_events?.icons;
        if (clipIcons && Array.isArray(clipIcons)) {
            newTranscript.clips[selectedClipIdx].edit_events.icons = clipIcons.filter((_: any, i: number) => i !== idxToRemove);
        } else if (newTranscript?.edit_events?.icons && Array.isArray(newTranscript.edit_events.icons)) {
            newTranscript.edit_events.icons = newTranscript.edit_events.icons.filter((_: any, i: number) => i !== idxToRemove);
        }
        setTranscript(newTranscript);
        saveChangesDebounced(newTranscript);
    };

    const saveChangesDebounced = async (currentTranscript: any) => {
        try {
            if (!currentTranscript?.version) return;

            await authFetch(`${API_BASE}/api/update-framing`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    version: currentTranscript.version,
                    user_id: '',  // Server extracts from token now
                    center: currentTranscript.center,
                    layout: currentTranscript.layout,
                    framing_segments: currentTranscript.framing_segments
                })
            });
        } catch (err) { console.error("Auto-save failed", err); }
    };

    const handleRender = async (clipIdx?: number) => {
        if (!transcript?.version) {
            setAlert({ msg: "No version found to render", type: 'error' });
            return;
        }

        const indicesToRender = clipIdx !== undefined ? [clipIdx] : selectedForRender;

        if (indicesToRender.length === 0) {
            setAlert({ msg: "No clips selected for rendering", type: 'error' });
            return;
        }

        try {
            setAlert({ msg: `Rendering ${indicesToRender.length} clip(s)...`, type: 'warning' });

            const res = await authFetch(`${API_BASE}/api/render`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    version: transcript.version,
                    user_id: '',  // Server extracts from token now
                    indices: indicesToRender
                })
            });
            const data = await res.json();

            if (data.message && data.message.includes("started")) {
                setAlert({ msg: "¡Excelente! Hemos iniciado la fila de renderizado. Los clips aparecerán en tu panel principal en unos minutos.", type: 'warning' });
                setView('dashboard');
                fetchProjects();
            } else {
                setAlert({ msg: "Hubo un pequeño contratiempo al iniciar el render. Por favor, intenta de nuevo en un momento.", type: 'error' });
            }
        } catch (err) {
            console.error("Render trigger failed", err);
            setAlert({ msg: "No pudimos conectar con el servidor de video. Revisa tu conexión e intenta otra vez.", type: 'error' });
        }
    };

    const resultsLayout = (
        <div className="flex-1 flex flex-col bg-black">
            <nav className="border-b border-white/5 px-12 h-20 flex items-center justify-between bg-black/50 backdrop-blur-xl">
                <div className="flex items-center gap-4">
                    <button onClick={() => setView('dashboard')} className="p-2 hover:bg-white/5 rounded-full transition-all cursor-pointer">
                        <ChevronRight className="w-5 h-5 rotate-180" />
                    </button>
                    <h1 className="text-xl font-bold tracking-tighter uppercase">RocotoClip</h1>
                </div>
                <div className="flex items-center gap-6">
                    <div className="flex bg-white/5 rounded-xl p-1 gap-1 border border-white/5">
                        <button
                            onClick={() => setPreferredLanguage('en')}
                            className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase transition-all cursor-pointer ${preferredLanguage === 'en' ? 'bg-white text-black' : 'text-neutral-500 hover:text-white'}`}
                        >
                            EN
                        </button>
                        <button
                            onClick={() => setPreferredLanguage('es')}
                            className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase transition-all cursor-pointer ${preferredLanguage === 'es' ? 'bg-white text-black' : 'text-neutral-500 hover:text-white'}`}
                        >
                            ES
                        </button>
                    </div>
                    <div className="flex flex-col items-end">
                        <span className="text-[10px] font-black text-neutral-500 uppercase">Analysis Complete</span>
                        <span className="text-xs font-bold text-white">Clips Identified</span>
                    </div>
                </div>
            </nav>

            <div className="border-b border-white/5 py-4 px-12 flex justify-between items-center bg-[#050505] sticky top-0 z-50">
                <span className="text-xs font-bold text-neutral-500 uppercase tracking-widest">Select the clips you want to export</span>
                <button
                    onClick={() => handleRender()}
                    disabled={selectedForRender.length === 0}
                    className="px-6 py-2 bg-purple-600 hover:bg-purple-500 text-white text-[10px] font-black uppercase tracking-widest rounded-xl disabled:opacity-30 transition-all shadow-[0_0_20px_rgba(147,51,234,0.3)] cursor-pointer">
                    Render Selected ({selectedForRender.length})
                </button>
            </div>

            <div className="flex-1 overflow-y-auto p-12 bg-black custom-scrollbar">
                <div className="max-w-6xl mx-auto flex flex-col gap-12 pb-24">
                    {transcript?.clips?.map((clip: any, idx: number) => {
                        const isSelected = selectedForRender.includes(idx);
                        const toggleSelect = () => setSelectedForRender(prev =>
                            prev.includes(idx) ? prev.filter(i => i !== idx) : [...prev, idx]
                        );

                        return (
                            <div key={idx} className="flex gap-10 items-start">
                                <div className="w-20 pt-16 flex flex-col items-center shrink-0">
                                    <div className="text-2xl font-black text-neutral-600 mb-8">#{idx + 1}</div>
                                    <div className="flex flex-col items-center gap-2 mb-8">
                                        <Zap className="w-5 h-5 text-yellow-500 fill-yellow-500" />
                                        <span className="text-3xl font-black text-white">{clip.score}</span>
                                        <span className="text-[10px] text-neutral-600 font-bold">/100</span>
                                    </div>
                                    <div className="flex flex-col gap-2 w-full px-2 mb-8">
                                        {['hook', 'flow', 'value', 'trend'].map(m => (
                                            <div key={m} className="flex justify-between items-center bg-white/5 rounded border border-white/5 px-2 py-1">
                                                <span className="text-[9px] font-bold text-neutral-500 uppercase">{m[0]}</span>
                                                <span className="text-[10px] font-black text-neutral-300">{clip[`${m}_score`]}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                <div className="flex-1 bg-[#0a0a0a] rounded-[2.5rem] border border-white/5 flex flex-col overflow-hidden shadow-2xl relative">
                                    <div className="h-16 border-b border-white/5 flex items-center justify-between px-8 bg-[#0c0c0c]">
                                        <div className="flex items-center gap-4">
                                            <label className="relative flex cursor-pointer items-center justify-center p-2 group">
                                                <input type="checkbox" className="peer sr-only" checked={isSelected} onChange={toggleSelect} />
                                                <div className="w-6 h-6 rounded-md border-2 border-white/20 peer-checked:bg-purple-600 peer-checked:border-purple-600 transition-all flex items-center justify-center group-hover:border-purple-500">
                                                    {isSelected && <Check className="w-4 h-4 text-white" />}
                                                </div>
                                            </label>
                                            <h3 className="text-sm font-bold truncate max-w-[500px] text-white/90">{clip.title || `Segment #${idx + 1}`}</h3>
                                        </div>
                                        <button onClick={() => { setSelectedClipIdx(idx); setView('editor'); }} className="w-10 h-10 flex items-center justify-center bg-white text-black hover:bg-neutral-200 rounded-xl transition-transform hover:scale-105 shadow-xl cursor-pointer">
                                            <Edit2 className="w-4 h-4" />
                                        </button>
                                    </div>

                                    <div className="flex bg-[#050505] p-6 gap-8">
                                        <div className="w-[30%] min-w-[200px] flex justify-center items-start">
                                            <div className="w-[200px] aspect-[9/16] bg-black rounded-lg overflow-hidden shadow-2xl border border-white/10 relative">
                                                <Player
                                                    component={Main}
                                                    durationInFrames={Math.ceil((clip.end - clip.start || 30) * 30)}
                                                    compositionWidth={1080} compositionHeight={1920} fps={30}
                                                    style={{ width: '100%', height: '100%', objectFit: 'contain' }} controls
                                                    inputProps={{
                                                        transcript: { ...transcript, ...clip },
                                                        isPlayer: true,
                                                        preferredLanguage
                                                    }}
                                                />
                                            </div>
                                        </div>

                                        <div className="flex-1 flex flex-col p-6 bg-[#0a0a0a] rounded-[1.5rem] border border-white/5">
                                            <div className="flex items-center justify-between mb-4">
                                                <h2 className="text-xs font-black uppercase tracking-widest italic text-white">Scene analysis</h2>
                                            </div>
                                            <p className="text-neutral-400 leading-relaxed text-xs mb-8">
                                                {clip.reasoning || "Analyzing context for viral potential and topic coherence..."}
                                            </p>
                                            <div className="flex-1 flex flex-col min-h-[150px]">
                                                <div className="flex items-center gap-2 mb-4 text-[10px] font-black uppercase tracking-widest text-neutral-500">
                                                    <Play className="w-2.5 h-2.5" /> Transcript
                                                </div>
                                                <div className="flex-1 rounded-xl bg-transparent border-l-2 border-white/5 pl-4 max-h-[250px] overflow-y-auto custom-scrollbar">
                                                    <div className="text-xs font-medium text-neutral-300 leading-relaxed">
                                                        {(preferredLanguage === 'es' && clip?.words_es ? clip.words_es : clip?.words)?.map((w: any, id: number) => (
                                                            <span key={id} className="hover:text-white transition-colors cursor-default">{w.word} </span>
                                                        ))}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );

    const dashboardView = (
        <main className="min-h-screen bg-black text-white font-sans flex flex-col items-center justify-center p-8 transition-all duration-700">

            {/* SOBER HEADER INTEGRATION */}
            <header className="fixed top-0 left-0 w-full border-b border-white/5 px-12 py-6 flex justify-between items-center bg-black/50 backdrop-blur-md z-[60]">
                <div className="flex items-center gap-4">
                    <h1 className="text-2xl font-bold tracking-tighter uppercase">RocotoClip</h1>
                    <div className="h-4 w-px bg-white/10" />
                    <nav className="flex gap-6 text-[10px] font-black uppercase tracking-widest text-neutral-500">
                        <Link href="/discovery" className="hover:text-white transition-colors flex items-center gap-2">
                            <Sparkles className="w-3 h-3" />
                            Discovery Engine
                        </Link>
                    </nav>
                </div>
                <button
                    onClick={handleLogout}
                    className="p-2 hover:bg-white/5 rounded-full text-neutral-500 hover:text-white transition-all cursor-pointer"
                >
                    <LogOut className="w-5 h-5" />
                </button>
            </header>

            {/* BRANDING */}
            <div className="mb-12 flex flex-col items-center mt-20">
                <h1 className="text-5xl font-bold tracking-tighter uppercase text-white select-none">RocotoClip</h1>
            </div>

            {/* INPUT AREA */}
            <div className="w-full max-w-2xl relative z-10">
                <div className="bg-[#0a0a0a] rounded-[2.5rem] border border-white/10 p-2 shadow-[0_0_100px_rgba(255,255,255,0.02)]">
                    <div className="relative group">
                        <div className="absolute left-8 top-1/2 -translate-y-1/2 text-neutral-600 group-focus-within:text-white transition-colors duration-300">
                            <LinkIcon className="w-5 h-5" />
                        </div>
                        <input
                            type="text"
                            placeholder="Drop a YouTube link"
                            className="w-full bg-transparent border-none px-20 py-10 text-xl font-medium outline-none placeholder:text-neutral-700 transition-all"
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleProcess()}
                        />
                    </div>

                    <div className="flex items-center justify-between px-8 py-6 border-t border-white/5 bg-black/40 rounded-b-[2.3rem]">
                        <div className="flex gap-6">
                            <Link href="/discovery" className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-neutral-500 hover:text-white transition-all cursor-pointer">
                                <Sparkles className="w-4 h-4" /> Discovery
                            </Link>
                            <button className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-neutral-500 hover:text-white transition-all cursor-pointer">
                                <Cloud className="w-4 h-4" /> Cloud Sync
                            </button>
                        </div>

                        <button
                            onClick={handleProcess}
                            disabled={isLaunching || !url}
                            className={`bg-white text-black px-12 py-5 rounded-[1.5rem] font-black uppercase text-[12px] tracking-tighter transition-all shadow-[0_10px_40px_rgba(255,255,255,0.1)] active:scale-95 flex items-center gap-2
                ${isLaunching ? 'opacity-50 cursor-wait bg-neutral-400' : 'hover:bg-neutral-200 cursor-pointer disabled:opacity-10'}`}
                        >
                            {isLaunching ? (
                                <>
                                    <div className="w-3 h-3 border-2 border-black/30 border-t-black rounded-full animate-spin" />
                                    Starting...
                                </>
                            ) : 'Analyze'}
                        </button>
                    </div>

                    <div className="mx-8 mt-2 h-[3px] overflow-hidden rounded-full">
                        {isLaunching && (
                            <div className="h-full bg-sky-500/30 w-full relative">
                                <div className="absolute top-0 bottom-0 bg-white animate-[loadingLine_2s_infinite_linear] w-[60%] shadow-[0_0_25px_rgba(255,255,255,1)]" />
                            </div>
                        )}
                    </div>
                </div>

                {alert && (
                    <div className={`mt-6 w-full flex items-center gap-4 border py-5 px-8 rounded-[2.5rem] animate-in fade-in slide-in-from-top-2 duration-500 shadow-2xl transition-colors
            ${alert.type === 'error' ? 'bg-red-500/10 border-red-500/10 text-red-500/90' : 'bg-amber-500/10 border-amber-500/10 text-amber-500/90'}`}>
                        <ShieldAlert className="w-5 h-5 shrink-0 opacity-70" />
                        <p className="flex-1 text-[11px] font-bold tracking-tight">
                            {alert.msg}
                        </p>
                        <button onClick={() => setAlert(null)} className="p-1.5 hover:bg-white/10 rounded-full transition-all">
                            <Check className="w-4 h-4" />
                        </button>
                    </div>
                )}
            </div>

            <div className="mt-20 w-full max-w-5xl grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 animate-in fade-in slide-in-from-bottom-8 duration-700">
                {Array.isArray(projects) && projects.map((proj) => {
                    const isProcessing = proj.isActive;
                    const isFailed = proj.status === 'failed';

                    return (
                        <div
                            key={proj.version}
                            onClick={() => !isProcessing && !isFailed && loadProject(proj.version)}
                            className={`relative group h-48 rounded-[2rem] border overflow-hidden p-8 flex flex-col justify-end transition-all cursor-pointer 
                ${isProcessing ? 'border-sky-500/50 bg-sky-950/20 cursor-wait' :
                                    isFailed ? 'border-red-500/20 bg-red-950/10 cursor-default' :
                                        'border-white/5 bg-neutral-900/50 hover:border-white/20 hover:scale-[1.02]'}`}
                        >
                            <div className="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-transparent z-10" />

                            {!isProcessing && (
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        if (isFailed) {
                                            handleDeleteProject(proj.version);
                                        } else {
                                            setShowDeleteModal(proj.version);
                                        }
                                    }}
                                    className="absolute top-6 right-6 z-30 p-2.5 bg-black/80 hover:bg-neutral-800 text-white rounded-full opacity-0 group-hover:opacity-100 transition-all scale-75 group-hover:scale-100 shadow-2xl"
                                >
                                    {isFailed ? <X className="w-4 h-4" /> : <Trash2 className="w-4 h-4" />}
                                </button>
                            )}

                            <div className="absolute inset-0 flex items-center justify-center opacity-[0.03] z-0">
                                <Youtube className={`w-32 h-32 ${isProcessing ? 'animate-pulse text-sky-400' : ''}`} />
                            </div>

                            <div className="relative z-20">
                                <div className="flex flex-col gap-1 mb-3">
                                    <p className="text-base font-bold truncate text-white">
                                        {proj.title || "Project " + proj.version}
                                    </p>
                                    <h4 className="text-[10px] font-black uppercase tracking-widest text-amber-500/60 flex justify-between items-center">
                                        <span>{new Date(proj.timestamp * 1000).toLocaleDateString()} • {new Date(proj.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true })}</span>
                                        {isProcessing && (
                                            <span className={`${proj.status === 'queued' ? 'bg-amber-500' : 'bg-sky-500'} text-white px-2 py-0.5 rounded-full animate-pulse text-[8px] tracking-tight`}>
                                                {proj.status === 'queued' ? 'EN COLA' : 'EN PROCESO'}
                                            </span>
                                        )}
                                        {isFailed && <span className="bg-red-500/80 text-white px-2 py-0.5 rounded-full text-[8px] tracking-tight font-black">ERROR</span>}
                                    </h4>
                                </div>

                                {isProcessing && proj.status !== 'queued' && (
                                    <div className="w-full h-1 bg-white/10 rounded-full overflow-hidden mt-2">
                                        <div
                                            className="h-full bg-sky-500 transition-all duration-500"
                                            style={{ width: `${proj.progress}%` }}
                                        />
                                    </div>
                                )}
                                {isProcessing && proj.status === 'queued' && (
                                    <p className="text-[10px] font-medium text-neutral-500 mt-2 uppercase tracking-tight">Esperando turno...</p>
                                )}
                            </div>

                            {!isProcessing && !isFailed && (
                                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-20 p-5 bg-white/10 backdrop-blur-md rounded-full shadow-2xl opacity-0 group-hover:opacity-100 transition-all scale-50 group-hover:scale-100 cursor-pointer">
                                    <Play className="w-6 h-6 fill-white" />
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>

            {showDeleteModal && (
                <div className="fixed inset-0 z-[100] bg-black/95 backdrop-blur-sm flex items-center justify-center p-6 animate-in fade-in duration-300">
                    <div className="max-w-md w-full bg-[#0a0a0a] border border-white/10 p-12 rounded-[3.5rem] text-center shadow-[0_0_100px_rgba(0,0,0,1)]">
                        <div className="w-20 h-20 bg-red-500/10 rounded-full flex items-center justify-center mx-auto mb-8">
                            <ShieldAlert className="w-10 h-10 text-red-500" />
                        </div>
                        <h2 className="text-3xl font-black uppercase text-white mb-4 tracking-tighter">Destruir Proyecto</h2>
                        <p className="text-neutral-500 text-xs mb-10 leading-relaxed font-medium uppercase tracking-widest">
                            ¿Confirmas la eliminación permanente de este nodo de datos? Esta acción es irreversible.
                        </p>
                        <div className="flex gap-4">
                            <button
                                onClick={() => setShowDeleteModal(null)}
                                className="flex-1 px-8 py-4 bg-white/5 hover:bg-white/10 text-white font-black rounded-2xl uppercase text-[10px] tracking-widest transition-all cursor-pointer"
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={() => handleDeleteProject(showDeleteModal)}
                                className="flex-1 bg-white text-black font-black py-4 rounded-2xl uppercase text-[10px] tracking-widest transition-all shadow-2xl"
                            >
                                Eliminar
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <footer className="py-24 text-center opacity-5 select-none pointer-events-none">
                <h2 className="text-[12rem] font-black tracking-[ -0.05em] uppercase italic">RocotoClip</h2>
            </footer>
        </main>
    );

    const editorView = (
        <main className="min-h-screen bg-black text-white font-sans flex flex-col">
            <nav className="border-b border-white/10 px-8 flex items-center justify-between h-16">
                <div className="flex items-center gap-4">
                    <button onClick={() => setView('results')} className="p-2 hover:bg-white/5 rounded-full transition-all cursor-pointer">
                        <ChevronRight className="w-5 h-5 rotate-180" />
                    </button>
                    <h1 className="text-xl font-bold tracking-tighter uppercase">RocotoClip <span className="text-neutral-500">Editor</span></h1>
                </div>
                <div className="flex items-center gap-6">
                    <div className="flex bg-white/5 rounded-xl p-1 gap-1 border border-white/5 mr-4">
                        <button
                            onClick={() => setPreferredLanguage('en')}
                            className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase transition-all ${preferredLanguage === 'en' ? 'bg-white text-black' : 'text-neutral-500 hover:text-white'}`}
                        >
                            EN
                        </button>
                        <button
                            onClick={() => setPreferredLanguage('es')}
                            className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase transition-all ${preferredLanguage === 'es' ? 'bg-white text-black' : 'text-neutral-500 hover:text-white'}`}
                        >
                            ES
                        </button>
                    </div>
                    <button
                        onClick={() => handleRender(selectedClipIdx)}
                        className="bg-white text-black px-6 py-2 rounded-xl text-[10px] font-black uppercase hover:bg-neutral-200 transition-all cursor-pointer"
                    >
                        Final Render
                    </button>
                </div>
            </nav>

            <div className="flex-1 flex overflow-hidden">
                <div className="flex-1 flex flex-col bg-[#050505] overflow-hidden border-r border-white/5">
                    <div className="flex-1 flex items-center justify-center min-h-0 p-8">
                        <div className="h-full aspect-[9/16] bg-black rounded-[2rem] overflow-hidden shadow-2xl border border-white/5">
                            <Player
                                ref={playerRef}
                                component={Main}
                                durationInFrames={Math.ceil((transcript?.clips?.[selectedClipIdx]?.duration || 30) * 30)}
                                compositionWidth={1080} compositionHeight={1920} fps={30}
                                style={{ width: '100%', height: '100%' }} controls
                                inputProps={{
                                    transcript: { ...transcript, ...transcript?.clips?.[selectedClipIdx] },
                                    isPlayer: true,
                                    preferredLanguage
                                }}
                            />
                        </div>
                    </div>

                    <div className="h-56 bg-[#0a0a0a] border-t border-white/5 flex flex-col p-6 shadow-2xl z-10">
                        <div className="flex items-center justify-between mb-4">
                            <span className="text-[10px] uppercase tracking-widest font-black text-neutral-500 flex items-center gap-2">
                                <Scissors className="w-3 h-3" /> Rocoto Timeline
                            </span>
                            <div className="flex gap-4">
                                <span className="text-[10px] text-neutral-600 font-bold">Start: {(transcript?.clips?.[selectedClipIdx]?.start || 0).toFixed(2)}s</span>
                                <span className="text-[10px] text-neutral-600 font-bold">End: {(transcript?.clips?.[selectedClipIdx]?.end || transcript?.duration || 0).toFixed(2)}s</span>
                            </div>
                        </div>

                        <div className="flex-1 rounded-xl bg-black border border-white/5 relative overflow-x-auto overflow-y-hidden custom-scrollbar flex flex-col py-2 px-4 gap-2">
                            <div className="h-6 w-full bg-white/5 rounded-md flex items-center px-4 relative shrink-0">
                                <Video className="w-3 h-3 text-neutral-600 absolute left-2" />
                                <div className="w-full text-center text-[8px] text-neutral-700 tracking-widest font-bold uppercase">Base Video Layer</div>
                            </div>

                            <div className="h-10 w-full bg-purple-900/10 rounded-md border border-purple-500/10 flex items-center px-8 relative shrink-0">
                                <Zap className="w-3 h-3 text-purple-600 absolute left-2" />
                                <div className="flex gap-2 w-full max-w-full overflow-x-auto custom-scrollbar items-center">
                                    {(transcript?.clips?.[selectedClipIdx]?.edit_events?.icons || transcript?.edit_events?.icons || []).map((icon: any, idx: number) => (
                                        <div key={idx} className="flex items-center gap-2 bg-purple-500/20 px-3 py-1 rounded-md text-[10px] font-black uppercase text-purple-300 border border-purple-500/30 whitespace-nowrap">
                                            <span>{icon.keyword} ({parseFloat(icon.time).toFixed(1)}s)</span>
                                            <button onClick={(e) => { e.stopPropagation(); removeEmoji(idx); }} className="p-0.5 hover:bg-black/50 rounded-full text-red-400 opacity-50 hover:opacity-100 transition-opacity cursor-pointer">
                                                <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div className="h-6 w-full bg-blue-900/10 rounded-md border border-blue-500/10 flex items-center px-4 relative shrink-0 overflow-hidden">
                                <div className="w-full flex truncate items-center opacity-30 px-6 gap-1">
                                    {transcript?.words?.map((w: any, idx: number) => <span key={idx} className="text-[8px] border-l border-white/10 px-1 truncate">{w.word}</span>)}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="w-[350px] bg-[#020202] py-8 pr-8 pl-8 overflow-y-auto flex flex-col gap-10 custom-scrollbar z-20">
                    <h2 className="text-xs font-black uppercase tracking-widest text-neutral-600 italic">Overrides & Control</h2>

                    <section className="space-y-4">
                        <div className="flex items-center gap-2 text-[10px] font-black uppercase text-neutral-500 tracking-widest">
                            <Scissors className="w-3 h-3" /> Timeline Cuts
                        </div>
                        <div className="p-6 bg-[#0a0a0a] border border-white/5 rounded-2xl flex flex-col gap-4">
                            <div className="flex justify-between items-center text-xs text-neutral-400 font-bold">
                                <span>Start:</span>
                                <span className="text-white bg-white/5 px-2 py-1 rounded">
                                    {(transcript?.clips?.[selectedClipIdx]?.start || 0).toFixed(2)}s
                                </span>
                            </div>
                            <div className="flex justify-between items-center text-xs text-neutral-400 font-bold">
                                <span>End:</span>
                                <span className="text-white bg-white/5 px-2 py-1 rounded">
                                    {(transcript?.clips?.[selectedClipIdx]?.end || transcript?.duration || 0).toFixed(2)}s
                                </span>
                            </div>
                            <button className="w-full mt-2 py-3 border border-white/10 hover:bg-white/10 text-white rounded-xl text-[9px] font-black uppercase tracking-widest transition-all cursor-pointer">
                                Fine Tune Duration
                            </button>
                        </div>
                    </section>

                    <section className="space-y-6">
                        <div className="flex items-center gap-2 text-[10px] font-black uppercase text-neutral-500 tracking-widest">
                            <Layout className="w-3 h-3" /> AI Framing Center
                        </div>
                        <div className="p-6 bg-[#0a0a0a] border border-white/5 rounded-2xl space-y-6">
                            <div className="flex justify-between items-end">
                                <span className="text-[9px] uppercase font-bold text-neutral-500 tracking-widest">Offset X</span>
                                <span className="text-lg font-black text-white">{((transcript?.center || 0.5) * 100).toFixed(0)}%</span>
                            </div>
                            <input type="range" min="0" max="1" step="0.01" value={transcript?.center || 0.5}
                                onChange={(e) => {
                                    const next = { ...transcript, center: parseFloat(e.target.value) };
                                    setTranscript(next);
                                    saveChangesDebounced(next);
                                }}
                                className="w-full accent-white h-2 bg-neutral-900 rounded-full appearance-none" />
                        </div>
                    </section>
                </div>
            </div>
        </main>
    );

    return (
        <div className="relative min-h-screen bg-black overflow-x-hidden">
            <div className="transition-all duration-700">
                {view === 'dashboard' && dashboardView}
                {view === 'results' && resultsLayout}
                {view === 'editor' && editorView}
            </div>

            <style jsx global>{`
        body { background: black; overflow-x: hidden; }
        .custom-scrollbar::-webkit-scrollbar { width: 4px; height: 4px; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        input[type=range]::-webkit-slider-thumb { 
          -webkit-appearance: none; 
          height: 20px; 
          width: 20px; 
          border-radius: 50%; 
          background: #ffffff; 
          cursor: pointer; 
          border: 3px solid #000; 
          box-shadow: 0 0 10px rgba(255,255,255,0.2); 
        }
        @keyframes loadingLine {
          from { left: -60%; }
          to { left: 100%; }
        }
      `}</style>
        </div>
    );
}
