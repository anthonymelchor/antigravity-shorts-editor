'use client';

import React, { useState, useEffect, useRef, useMemo, memo } from 'react';
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
    X,
    Globe,
    Clock,
    Loader2
} from 'lucide-react';
import Link from 'next/link';
import { createClientComponentClient } from '@supabase/auth-helpers-nextjs';
import { useRouter } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

const ClipPlayer = memo(({ clip, transcript, preferredLanguage, authToken, API_BASE }: any) => {
    const inputProps = useMemo(() => ({
        transcript: { ...transcript, ...clip },
        isPlayer: true,
        preferredLanguage,
        apiBase: API_BASE,
        version: transcript?.version,
        token: authToken
    }), [transcript?.version, clip.id, clip.start, clip.end, authToken, preferredLanguage]);

    return (
        <Player
            component={Main}
            durationInFrames={Math.ceil((clip.end - clip.start || 30) * 30)}
            compositionWidth={1080} compositionHeight={1920} fps={30}
            style={{ width: '100%', height: '100%', objectFit: 'contain' }} controls
            bufferStateDelayInMilliseconds={1000}
            renderLoading={() => <div className="absolute inset-0 flex items-center justify-center bg-black/50 text-white text-[10px] animate-pulse">Buffering...</div>}
            inputProps={inputProps}
        />
    );
});

const EditorPlayer = memo(({ transcript, selectedClipIdx, preferredLanguage, authToken, API_BASE, playerRef }: any) => {
    const clip = transcript?.clips?.[selectedClipIdx];
    const inputProps = useMemo(() => ({
        transcript: { ...transcript, ...clip },
        isPlayer: true,
        preferredLanguage,
        apiBase: API_BASE,
        version: transcript?.version,
        token: authToken
    }), [transcript?.version, selectedClipIdx, authToken, preferredLanguage]);

    return (
        <Player
            ref={playerRef}
            component={Main}
            durationInFrames={Math.ceil((clip?.duration || 30) * 30)}
            compositionWidth={1080}
            compositionHeight={1920}
            fps={30}
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            controls
            bufferStateDelayInMilliseconds={1000}
            autoPlay={true}
            inputProps={inputProps}
        />
    );
});

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
    const [showCancelModal, setShowCancelModal] = useState(false);
    const [alert, setAlert] = useState<{ msg: string; type: 'error' | 'warning' | 'success' } | null>(null);
    const [isRenderingNow, setIsRenderingNow] = useState(false);
    const [activeUrl, setActiveUrl] = useState<string | null>(null);
    const [currentVersion, setCurrentVersion] = useState<string | null>(null);
    const [accounts, setAccounts] = useState<any[]>([]);
    const [nicheFilter, setNicheFilter] = useState<string | null>(null);
    const [selectedNiche, setSelectedNiche] = useState<string>('');
    const [isEditingMetadata, setIsEditingMetadata] = useState(false);
    const [isLaunching, setIsLaunching] = useState(false);
    const [currentFrame, setCurrentFrame] = useState(0);
    const [timelineZoom, setTimelineZoom] = useState(1);
    const processingRef = useRef<string | null>(null);
    const versionRef = useRef<string | null>(null);
    const playerRef = useRef<PlayerRef>(null);
    const pendingDeletions = useRef<Set<string>>(new Set());

    const router = useRouter();
    const supabase = createClientComponentClient();
    const [authToken, setAuthToken] = useState<string | null>(null);

    useEffect(() => {
        supabase.auth.getSession().then(({ data: { session } }) => {
            if (session?.access_token) {
                setAuthToken(session.access_token);
            }
        });
        const {
            data: { subscription },
        } = supabase.auth.onAuthStateChange((_event, session) => {
            setAuthToken(session?.access_token ?? null);
        });
        return () => subscription.unsubscribe();
    }, [supabase]);

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
        fetchAccounts();
    }, []);

    const fetchAccounts = async () => {
        try {
            const res = await authFetch(`${API_BASE}/api/accounts`);
            const data = await res.json();
            if (Array.isArray(data)) {
                setAccounts(data);
            }
        } catch (err) {
            console.error("Failed to fetch accounts", err);
        }
    };

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
        if (alert && (alert.type === 'warning' || alert.type === 'success')) {
            const timer = setTimeout(() => setAlert(null), alert.type === 'success' ? 4000 : 6000);
            return () => clearTimeout(timer);
        }
    }, [alert]);

    // Track playhead by polling every animation frame. 
    // We try 3 sources in order: <video> element, playerRef.getCurrentFrame(), nothing.
    useEffect(() => {
        if (view !== 'results' && view !== 'editor') return;
        let rafId: number;
        let lastVal = -1;

        const tick = () => {
            let timeSec = -1;
            let durationSec = 1;

            if (view === 'editor') {
                // In editor, try to find the player's video element first (more accurate)
                const editorPlayer = document.querySelector('.editor-player-container');
                const videoEl = editorPlayer?.querySelector('video') as HTMLVideoElement | null;

                if (videoEl && isFinite(videoEl.duration) && videoEl.duration > 0) {
                    timeSec = videoEl.currentTime;
                    durationSec = videoEl.duration;
                } else if (playerRef.current) {
                    // Fallback to Player API
                    try {
                        const f = (playerRef.current as any).getCurrentFrame?.();
                        if (typeof f === 'number') {
                            timeSec = f / 30;
                            durationSec = (transcript?.clips?.[selectedClipIdx]?.duration) || 30;
                        }
                    } catch (_) { }
                }

                if (timeSec >= 0 && Math.abs(timeSec - lastVal) > 0.01) {
                    lastVal = timeSec;
                    const pct = Math.min(100, (timeSec / durationSec) * 100);
                    const edLine = document.getElementById('rct-editor-playhead-line');
                    if (edLine) (edLine as HTMLElement).style.left = pct + '%';
                    const edLabel = document.getElementById('rct-editor-playhead-label');
                    if (edLabel) (edLabel as HTMLElement).textContent = timeSec.toFixed(1) + 's';
                    const edInp = document.getElementById('rct-editor-playhead-input') as HTMLInputElement | null;
                    if (edInp && document.activeElement !== edInp) edInp.value = timeSec.toFixed(3);
                }
            } else if (view === 'results') {
                // In results view, we just let the native controls do their thing, 
                // but we could track the active one if we had a specific global UI for it.
            }

            rafId = requestAnimationFrame(tick);
        };

        rafId = requestAnimationFrame(tick);
        return () => cancelAnimationFrame(rafId);
    }, [view, transcript?.version, selectedClipIdx]);

    useEffect(() => {
        let interval: NodeJS.Timeout;
        const currentId = transcript?.version || status.version;

        const poll = async () => {
            try {
                const url = currentId ? `${API_BASE}/api/status?version=${currentId}` : `${API_BASE}/api/status`;
                const res = await authFetch(url);
                const data = await res.json();

                setStatus(prev => ({ ...prev, ...data }));

                if (data.active_clips && data.active_clips.some((c: any) => c.status === 'completed')) {
                    fetchProjects();
                }

                if ((data.status === 'completed' || data.status === 'failed') && versionRef.current && String(data.version) === String(versionRef.current)) {
                    processingRef.current = null;
                    versionRef.current = null;
                    setCurrentVersion(null);
                    checkInitialStatus();
                }
            } catch (err) { console.error("Poll failed", err); }
        };

        poll();
        interval = setInterval(poll, 2500);
        return () => clearInterval(interval);
    }, [transcript?.version, view]);

    useEffect(() => {
        let interval: NodeJS.Timeout;
        if (view === 'dashboard') {
            fetchProjects();
            interval = setInterval(fetchProjects, isLaunching ? 1000 : 3000);
        }
        return () => clearInterval(interval);
    }, [view, isLaunching]);

    const [renderStatus, setRenderStatus] = useState<any>(null);
    useEffect(() => {
        let active = true;
        let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;

        const startStream = async () => {
            if (view === 'editor' && transcript?.version && selectedClipIdx !== null) {
                try {
                    const params = new URLSearchParams({ version: transcript.version, idx: selectedClipIdx.toString() });
                    const res = await authFetch(`${API_BASE}/api/render-stream?${params}`);
                    if (!res.body) return;

                    reader = res.body.getReader();
                    const decoder = new TextDecoder();

                    while (active) {
                        const { value, done } = await reader.read();
                        if (done) break;

                        const chunk = decoder.decode(value, { stream: true });
                        const lines = chunk.split('\n').filter(Boolean);
                        for (const line of lines) {
                            try {
                                const data = JSON.parse(line);
                                if (data.status && data.status !== 'idle') {
                                    setRenderStatus(data);
                                } else {
                                    setRenderStatus(null);
                                }
                            } catch (e) { }
                        }
                    }
                } catch (err) {
                    if (active) setRenderStatus(null);
                }
            } else {
                setRenderStatus(null);
            }
        };

        startStream();

        return () => {
            active = false;
            // if (reader) reader.cancel().catch(() => {}); // Optional tear down
        };
    }, [view, transcript?.version, selectedClipIdx]);

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
                body: JSON.stringify({
                    url: url.trim(),
                    niche: selectedNiche || undefined
                })
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

            let payload: any = {
                version: currentTranscript.version,
                user_id: '',
                center: currentTranscript.center,
                layout: currentTranscript.layout,
                framing_segments: currentTranscript.framing_segments
            };

            if (selectedClipIdx !== null && currentTranscript.clips && currentTranscript.clips[selectedClipIdx]) {
                const clip = currentTranscript.clips[selectedClipIdx];
                payload = {
                    ...payload,
                    clip_index: selectedClipIdx,
                    center: clip.center !== undefined ? clip.center : currentTranscript.center,
                    layout: clip.layout !== undefined ? clip.layout : currentTranscript.layout,
                    framing_segments: clip.framing_segments !== undefined ? clip.framing_segments : currentTranscript.framing_segments,
                    start: clip.start,
                    end: clip.end
                };
            }

            await authFetch(`${API_BASE}/api/update-framing`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch (err) { console.error("Auto-save failed", err); }
    };

    const updateMetadata = async (metadata: any) => {
        try {
            if (!transcript?.version) return;
            const res = await authFetch(`${API_BASE}/api/update-metadata`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    version: transcript.version,
                    user_id: '',
                    ...metadata
                })
            });
            const result = await res.json();
            if (result.status === 'success') {
                setTranscript({ ...transcript, ...result.data });
            }
        } catch (err) { console.error("Metadata update failed", err); }
    };

    const togglePublished = async (clipIdx: number) => {
        if (!transcript?.version || !transcript.clips) return;
        try {
            const isCurrentlyPublished = !!transcript.clips[clipIdx].published;
            const res = await authFetch(`${API_BASE}/api/update-published`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    version: transcript.version,
                    clip_index: clipIdx,
                    published: !isCurrentlyPublished
                })
            });
            const result = await res.json();
            if (result.status === 'success') {
                const newClips = [...transcript.clips];
                newClips[clipIdx] = { ...newClips[clipIdx], published: result.published };
                setTranscript({ ...transcript, clips: newClips });
                fetchProjects(); // Para refrescar contadores en dashboard
            }
        } catch (err) { console.error("Published toggle failed", err); }
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
            setIsRenderingNow(true);
            setAlert({ msg: `Preparando ${indicesToRender.length} clip(s)...`, type: 'success' });

            // Optimistic update to immediately reflect the rendering state
            setStatus((prev: any) => {
                const newClips = prev.active_clips ? [...prev.active_clips] : [];
                indicesToRender.forEach(renderIdx => {
                    const versionStr = String(transcript.version);
                    const existingIdx = newClips.findIndex((c: any) => c.version === `render_${versionStr}_${renderIdx}`);
                    if (existingIdx !== -1) {
                        newClips[existingIdx] = { ...newClips[existingIdx], status: 'queued', progress: 0 };
                    } else {
                        newClips.push({ status: 'queued', version: `render_${versionStr}_${renderIdx}`, progress: 0 });
                    }
                });
                return { ...prev, active_clips: newClips, status: 'rendering' };
            });

            const res = await authFetch(`${API_BASE}/api/render`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    version: transcript.version,
                    user_id: '',  // Server extracts from token now
                    indices: indicesToRender,
                    preferredLanguage
                })
            });
            const data = await res.json();

            if (data.message && data.message.includes("started")) {
                setAlert({ msg: "¡Excelente! Hemos iniciado la fila de renderizado. Puedes ver el progreso en los clips.", type: 'success' });

                // We keep them in selectedForRender for a moment to bridge the gap until polling catches up
                setTimeout(() => {
                    setSelectedForRender([]);
                    fetchProjects();
                }, 3000);

                // Keep the button "off" for a moment to feel the click
                setTimeout(() => setIsRenderingNow(false), 2000);
            } else {
                setAlert({ msg: "Hubo un pequeño contratiempo al iniciar el render. Por favor, intenta de nuevo en un momento.", type: 'error' });
                setIsRenderingNow(false);
            }
        } catch (err) {
            console.error("Render trigger failed", err);
            setAlert({ msg: "No pudimos conectar con el servidor de video. Revisa tu conexión e intenta otra vez.", type: 'error' });
            setIsRenderingNow(false);
        }
    };

    const handleCancelRender = async () => {
        try {
            const res = await authFetch(`${API_BASE}/api/cancel-render`, { method: 'POST' });
            const data = await res.json();

            if (data.status === 'success') {
                setAlert({ msg: data.message, type: 'warning' });
                // Optimistically clear the rendering status in UI
                setStatus((prev: any) => ({ ...prev, active_clips: [], status: 'idle' }));
                setIsRenderingNow(false);
            } else {
                setAlert({ msg: "El servidor no pudo cancelar la operación: " + (data.message || "Error desconocido"), type: 'warning' });
            }
        } catch (err) {
            console.error("Cancel failed", err);
            setAlert({ msg: "No se pudo conectar con el servidor para detener el render.", type: 'error' });
        } finally {
            setShowCancelModal(false);
            setIsRenderingNow(false);
        }
    };

    const handleOpenRemotion = async (clipIdx: number) => {
        if (!transcript?.version) return;

        try {
            setAlert({ msg: "Sincronizando con Studio...", type: 'warning' });

            const res = await authFetch(`${API_BASE}/api/preview-remotion`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    version: transcript.version,
                    clip_index: clipIdx,
                    preferredLanguage
                })
            });
            const data = await res.json();

            if (data.status === 'success') {
                setAlert({ msg: "Abriendo Remotion Studio.", type: 'success' });
                window.open("http://localhost:3001", "_blank");
            } else {
                setAlert({ msg: "Error al abrir Remotion Studio", type: 'error' });
            }
        } catch (err) {
            console.error("Remotion Preview failed", err);
            setAlert({ msg: "Hubo un error al preparar el preview.", type: 'error' });
        }
    };



    const addFramingCut = (layoutToApply: 'single' | 'split') => {
        if (!playerRef.current || selectedClipIdx === null) return;
        const clip = transcript?.clips?.[selectedClipIdx];
        if (!clip) return;

        let segments = clip.framing_segments || [{
            start: 0,
            end: clip.duration || 30,
            center: transcript?.center || 0.5,
            center_top: transcript?.center_top || 0.5,
            center_bottom: transcript?.center_bottom || 0.5,
            layout: clip.layout || transcript?.layout || 'single'
        }];

        segments = JSON.parse(JSON.stringify(segments));

        const currentFrame = playerRef.current.getCurrentFrame();
        const currentTimeMs = currentFrame / 30; // in seconds

        const newSegments = [];
        let deletedCut = false;

        // Tolerance for deleting a cut (within 0.3 seconds of boundary)
        const DELETE_TOLERANCE = 0.3;

        for (let i = 0; i < segments.length; i++) {
            const seg = segments[i];

            // If playhead is right on the boundary between this segment and the next one
            if (i < segments.length - 1 && Math.abs(currentTimeMs - seg.end) < DELETE_TOLERANCE) {
                // Merge this segment with the next one
                const nextSeg = segments[i + 1];
                newSegments.push({
                    ...seg,
                    end: nextSeg.end,
                    // Keep layout of the first segment
                });
                i++; // Skip next segment since we merged it
                deletedCut = true;
                continue;
            }

            // Normal cut logic
            if (!deletedCut && currentTimeMs > seg.start && currentTimeMs < seg.end) {
                newSegments.push({ ...seg, end: currentTimeMs });

                const newSeg: any = { ...seg, start: currentTimeMs, layout: layoutToApply };

                // When forcing split, find the best center_top/center_bottom values available.
                // Priority: existing split segment → clip-level → transcript root → sensible defaults.
                // This ensures the forced split looks identical to an automatic AI-split.
                if (layoutToApply === 'split') {
                    const existingSplit = segments.find((s: any) => s.layout === 'split');
                    newSeg.center_top =
                        existingSplit?.center_top ??
                        clip.center_top ??
                        transcript?.center_top ??
                        0.3;
                    newSeg.center_bottom =
                        existingSplit?.center_bottom ??
                        clip.center_bottom ??
                        transcript?.center_bottom ??
                        0.7;
                } else if (layoutToApply === 'single') {
                    const existingSingle = segments.find((s: any) => s.layout === 'single');
                    newSeg.center =
                        existingSingle?.center ??
                        clip.center ??
                        transcript?.center ??
                        0.5;
                }

                newSegments.push(newSeg);
            } else {
                newSegments.push(seg);
            }
        }

        const next = { ...transcript };
        if (next.clips && next.clips[selectedClipIdx]) {
            next.clips[selectedClipIdx].framing_segments = newSegments;
        } else {
            next.framing_segments = newSegments;
        }

        setTranscript(next);
        saveChangesDebounced(next);

        // Let's trigger a toast message to let the user know their cut was successful
        setAlert({ msg: deletedCut ? "Corte eliminado y fusionado" : `Corte añadido: a partir de ahora es ${layoutToApply === 'single' ? 'vertical (single)' : 'horizontal (split)'}`, type: 'warning' });
        setTimeout(() => setAlert(null), 3000);
    };

    const adjustClipBoundary = (boundary: 'start' | 'end', amount: number) => {
        if (selectedClipIdx === null) return;
        const clip = transcript?.clips?.[selectedClipIdx];
        if (!clip) return;

        const next = { ...transcript };
        if (next.clips && next.clips[selectedClipIdx]) {
            const currentVal = next.clips[selectedClipIdx][boundary] || 0;
            const newVal = Math.max(0, currentVal + amount);
            next.clips[selectedClipIdx][boundary] = newVal;

            const newStart = next.clips[selectedClipIdx].start || 0;
            const newEnd = next.clips[selectedClipIdx].end || 0;
            next.clips[selectedClipIdx].duration = Math.max(0.1, newEnd - newStart);
        }
        setTranscript(next);
        saveChangesDebounced(next);
    };

    const setClipBoundary = (boundary: 'start' | 'end', value: number) => {
        if (selectedClipIdx === null) return;
        const clip = transcript?.clips?.[selectedClipIdx];
        if (!clip) return;

        const next = { ...transcript };
        if (next.clips && next.clips[selectedClipIdx]) {
            next.clips[selectedClipIdx][boundary] = Math.max(0, value);

            const newStart = next.clips[selectedClipIdx].start || 0;
            const newEnd = next.clips[selectedClipIdx].end || 0;
            next.clips[selectedClipIdx].duration = Math.max(0.1, newEnd - newStart);
        }
        setTranscript(next);
        saveChangesDebounced(next);
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
                <div className="flex items-center gap-6">
                    <span className="text-xs font-bold text-neutral-500 uppercase tracking-widest">Select the clips you want to export</span>
                    <div className="h-4 w-px bg-white/10" />
                    <div className="flex items-center gap-3 bg-white/5 px-4 py-2 rounded-xl border border-white/10 group relative">
                        <div className="flex flex-col">
                            <span className="text-[9px] font-black text-white/40 uppercase tracking-tighter">Branding Identity</span>
                            <span className="text-[11px] font-bold text-white/90">
                                {accounts.find(a => a.id === transcript?.account_id)?.niche || 'General'}
                                <span className="mx-2 text-white/20">|</span>
                                <span className="text-white">@{accounts.find(a => a.id === transcript?.account_id)?.name || 'rocotoclip'}</span>
                            </span>
                        </div>
                        <button
                            onClick={() => setIsEditingMetadata(!isEditingMetadata)}
                            className="p-1.5 hover:bg-white/10 rounded-lg transition-all text-neutral-400 hover:text-white cursor-pointer"
                        >
                            <Edit2 className="w-3.5 h-3.5" />
                        </button>

                        {isEditingMetadata && (
                            <div className="absolute top-full left-0 mt-2 w-72 bg-[#121212] border border-white/10 rounded-2xl shadow-2xl p-4 z-[70] animate-in fade-in slide-in-from-top-2">
                                <h4 className="text-[10px] font-black uppercase text-neutral-500 mb-3 px-2">Select Branding Account</h4>
                                <div className="flex flex-col gap-1">
                                    {accounts.map(acc => (
                                        <button
                                            key={acc.id}
                                            onClick={() => {
                                                updateMetadata({ account_id: acc.id });
                                                setIsEditingMetadata(false);
                                            }}
                                            className={`flex flex-col items-start px-3 py-2 rounded-xl transition-all cursor-pointer ${transcript?.account_id === acc.id ? 'bg-white/10 border border-white/20' : 'hover:bg-white/5 border border-transparent'}`}
                                        >
                                            <span className="text-xs font-bold text-white">{acc.niche}</span>
                                            <span className="text-[10px] text-neutral-500">@{acc.name}</span>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    {(((status as any).active_clips?.some((c: any) => c.status === 'rendering' || c.status === 'queued')) || isRenderingNow) && (
                        <button
                            onClick={() => setShowCancelModal(true)}
                            className="flex items-center gap-3 px-6 py-4 bg-red-600/20 hover:bg-red-600/40 text-red-500 border border-red-500/30 rounded-2xl font-black uppercase text-[10px] tracking-widest transition-all shadow-2xl active:scale-95 cursor-pointer"
                        >
                            <X className="w-4 h-4" />
                            Detener Todo
                        </button>
                    )}
                    <button
                        onClick={() => handleRender()}
                        disabled={selectedForRender.length === 0 || isRenderingNow}
                        className={`flex items-center gap-3 px-8 py-4 bg-white text-black rounded-2xl font-black uppercase text-[10px] tracking-widest transition-all shadow-2xl active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed ${isRenderingNow ? 'animate-pulse' : ''}`}
                    >
                        {isRenderingNow ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                            <Download className="w-4 h-4" />
                        )}
                        <span>{isRenderingNow ? 'Preparando...' : `Renderizar Seleccionados (${selectedForRender.length})`}</span>
                    </button>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-12 bg-black custom-scrollbar">
                <div className="max-w-6xl mx-auto flex flex-col gap-12 pb-24 relative">
                    {alert && (
                        <div className="flex justify-center -mt-8 mb-[-1rem] relative z-[80]">
                            <div className={`inline-flex items-center gap-2 border px-4 py-1.5 rounded-full animate-in fade-in slide-in-from-top-2 duration-500 shadow-xl transition-all
                                ${alert.type === 'error' ? 'bg-red-500/10 border-red-500/20 text-red-400' :
                                    alert.type === 'success' ? 'bg-[#0f291e]/90 backdrop-blur-md border-[#1b3d2f] text-[#4ade80]' :
                                        'bg-amber-500/10 border-amber-500/20 text-amber-400'}`}>
                                {alert.type === 'success' ? <Check className="w-3 h-3 shrink-0" /> : <ShieldAlert className="w-3 h-3 shrink-0 opacity-80" />}
                                <p className="text-[10px] font-bold tracking-wide leading-none">
                                    {alert.msg}
                                </p>
                            </div>
                        </div>
                    )}

                    {transcript?.clips?.map((clip: any, idx: number) => {
                        const activeRenders = (status as any).active_clips || [];
                        const versionStr = String(transcript.version);
                        const clipRenderStatus = activeRenders.find((r: any) =>
                            String(r.version) === `render_${versionStr}_${idx}` ||
                            String(r.version).includes(`render_${versionStr}_${idx}`)
                        );

                        const isActuallyRenderingServer = !!(clipRenderStatus && (clipRenderStatus.status === 'rendering' || clipRenderStatus.status === 'queued'));
                        const isRenderingOptimistic = selectedForRender.includes(idx) && isRenderingNow;
                        const isRendering = !!(isActuallyRenderingServer || isRenderingOptimistic);

                        // Requirement #1: Block checkbox if rendering, and keep it checked
                        const isSelected = !!(selectedForRender.includes(idx) || isActuallyRenderingServer);
                        const toggleSelect = () => {
                            if (isRendering) return;
                            setSelectedForRender(prev =>
                                prev.includes(idx) ? prev.filter(i => i !== idx) : [...prev, idx]
                            );
                        };

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
                                    {/* Requirement #2: Loading bar inside the card */}
                                    {/* Requirement #2: Loading bar inside the card - ONLY when actively rendering */}
                                    {isRendering && clipRenderStatus?.status === 'rendering' && (
                                        <div className="absolute top-0 left-0 right-0 h-[4px] bg-white/5 z-[60] overflow-hidden">
                                            <div
                                                className="h-full transition-all duration-700 ease-out bg-sky-400 shadow-[0_0_25px_rgba(14,165,233,1)]"
                                                style={{ width: `${clipRenderStatus?.progress || 5}%` }}
                                            />
                                        </div>
                                    )}

                                    <div className="h-16 border-b border-white/5 flex items-center justify-between px-8 bg-[#0c0c0c]">
                                        <div className="flex items-center gap-4">
                                            <div className="relative flex items-center justify-center p-2 w-10 h-10">
                                                <label className={`group flex items-center justify-center w-full h-full ${isRendering ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}>
                                                    <input
                                                        type="checkbox"
                                                        className="peer sr-only"
                                                        checked={isSelected}
                                                        onChange={toggleSelect}
                                                        disabled={isRendering}
                                                    />
                                                    <div className={`w-6 h-6 rounded-md border-2 transition-all flex items-center justify-center ${isSelected ? 'bg-white border-white shadow-[0_0_15px_rgba(255,255,255,0.4)]' : 'border-white/20 group-hover:border-white/40'}`}>
                                                        {isSelected && <Check className="w-4 h-4 text-black" />}
                                                    </div>
                                                </label>
                                            </div>
                                            <div className="flex flex-col">
                                                <div className="flex items-center gap-2">
                                                    <h3 className="text-sm font-normal truncate max-w-[400px] text-white/90">{clip.title || `Segment #${idx + 1}`}</h3>
                                                    {clip.is_title_clip && (
                                                        <span className="bg-indigo-500/20 border border-indigo-400/40 text-indigo-400 px-2 py-0.5 rounded-full text-[8px] font-black uppercase tracking-tight flex items-center gap-1 shadow-[0_0_15px_rgba(99,102,241,0.2)]">
                                                            <Sparkles className="w-3 h-3" />
                                                            Clip del Título
                                                        </span>
                                                    )}
                                                    {isRendering && clipRenderStatus?.status === 'queued' && (
                                                        <span className="bg-amber-500 text-white px-2 py-0.5 rounded-full animate-pulse text-[8px] font-black uppercase tracking-tight flex items-center gap-1">
                                                            <Clock className="w-3 h-3" />
                                                            EN COLA
                                                        </span>
                                                    )}
                                                    {isRendering && clipRenderStatus?.status === 'rendering' && (
                                                        <span className="bg-sky-500/20 border border-sky-400/30 text-sky-400 px-2 py-0.5 rounded-full text-[8px] font-black uppercase tracking-tight flex items-center gap-1">
                                                            <Loader2 className="w-3 h-3 animate-spin" />
                                                            RENDERIZANDO
                                                        </span>
                                                    )}
                                                </div>
                                                {isRendering && (
                                                    <span className={`text-[9px] font-black uppercase tracking-widest ${clipRenderStatus?.status === 'rendering' ? 'text-sky-400' : 'text-amber-500'}`}>
                                                        {clipRenderStatus?.status === 'rendering' ? `Renderizando... ${clipRenderStatus?.progress}%` : 'Esperando turno...'}
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-3">
                                            <button
                                                onClick={(e) => { e.stopPropagation(); togglePublished(idx); }}
                                                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[9px] font-black uppercase transition-all border 
                                                    ${clip.published
                                                        ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                                                        : 'bg-white/5 border-white/10 text-neutral-500 hover:text-white hover:bg-white/10'}`}
                                            >
                                                <Globe className="w-3 h-3" />
                                                {clip.published ? 'Publicado' : 'Pendiente'}
                                            </button>
                                            <button
                                                onClick={(e) => { e.stopPropagation(); handleOpenRemotion(idx); }}
                                                className="w-10 h-10 flex items-center justify-center bg-white text-black hover:bg-neutral-200 rounded-xl transition-transform hover:scale-105 shadow-xl cursor-pointer"
                                                title="Preview exacto en Remotion Studio"
                                            >
                                                <ExternalLink className="w-4 h-4" />
                                            </button>
                                            <button onClick={() => { setSelectedClipIdx(idx); setView('editor'); }} className="w-10 h-10 flex items-center justify-center bg-white text-black hover:bg-neutral-200 rounded-xl transition-transform hover:scale-105 shadow-xl cursor-pointer">
                                                <Edit2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </div>

                                    <div className="flex bg-[#050505] p-6 gap-8">
                                        <div className="w-[30%] min-w-[200px] flex justify-center items-start">
                                            <div className="w-[200px] aspect-[9/16] bg-black rounded-lg overflow-hidden shadow-2xl border border-white/10 relative">
                                                <ClipPlayer
                                                    clip={clip}
                                                    transcript={transcript}
                                                    preferredLanguage={preferredLanguage}
                                                    authToken={authToken}
                                                    API_BASE={API_BASE}
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
        <main className="min-h-screen bg-black text-white font-sans flex flex-col items-center p-8 transition-all duration-700 pt-32">

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
                        <div className="flex gap-6 items-center">
                            <Link href="/discovery" className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-neutral-500 hover:text-white transition-all cursor-pointer">
                                <Sparkles className="w-4 h-4" /> Discovery
                            </Link>
                            <div className="h-4 w-px bg-white/5" />
                            <select
                                value={selectedNiche}
                                onChange={(e) => setSelectedNiche(e.target.value)}
                                className="bg-transparent border-none text-[10px] font-black uppercase tracking-widest outline-none hover:text-white transition-all cursor-pointer text-neutral-500"
                            >
                                <option value="" className="bg-[#0a0a0a]">Categorizar</option>
                                {Array.from(new Set(accounts.map(a => a.niche).filter(Boolean))).map(n => (
                                    <option key={n} value={n} className="bg-[#0a0a0a]">{n}</option>
                                ))}
                            </select>
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

            </div>

            {/* PROJECT LIST HEADER & FILTER */}
            <div className="mt-20 w-full max-w-5xl flex flex-col gap-8 animate-in fade-in slide-in-from-bottom-8 duration-700">
                <div className="flex items-center justify-between border-b border-white/5 pb-6">
                    <div className="flex items-center gap-4">
                        <h2 className="text-sm font-black uppercase tracking-widest text-neutral-500">Mis Proyectos</h2>
                        <span className="bg-white/5 px-3 py-1 rounded-lg text-[10px] font-bold text-neutral-400 border border-white/5">
                            {projects.length}
                        </span>
                    </div>

                    {/* Dynamic Niche Filter */}
                    <div className="flex items-center gap-3 overflow-x-auto no-scrollbar max-w-[60%] py-1">
                        <button
                            onClick={() => setNicheFilter(null)}
                            className={`px-4 py-2 rounded-xl text-[10px] font-black capitalize tracking-widest transition-all cursor-pointer border
                                ${!nicheFilter ? 'bg-white text-black border-white shadow-[0_0_20px_rgba(255,255,255,0.1)]' : 'bg-transparent text-neutral-500 border-white/5 hover:border-white/10 hover:text-white'}`}
                        >
                            Todos
                        </button>
                        {Array.from(new Set(projects.map(p => p.niche).filter(Boolean))).map(niche => (
                            <button
                                key={niche}
                                onClick={() => setNicheFilter(niche)}
                                className={`px-4 py-2 rounded-xl text-[10px] font-black tracking-widest transition-all cursor-pointer border whitespace-nowrap
                                    ${nicheFilter === niche ? 'bg-white text-black border-white shadow-[0_0_20px_rgba(255,255,255,0.1)]' : 'bg-transparent text-neutral-500 border-white/5 hover:border-white/10 hover:text-white'}`}
                            >
                                {niche.charAt(0).toUpperCase() + niche.slice(1).toLowerCase()}
                            </button>
                        ))}
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {Array.isArray(projects) && projects.filter(p => !nicheFilter || p.niche === nicheFilter).map((proj) => {
                        const isRenderingTask = proj.status === 'rendering';
                        const isInitialProcessing = proj.isActive && !isRenderingTask;
                        const isFailed = proj.status === 'failed';

                        return (
                            <div
                                key={proj.version}
                                onClick={() => (proj.canOpen && !isFailed) && loadProject(proj.version)}
                                className={`relative group h-48 rounded-[2rem] border overflow-hidden p-8 flex flex-col justify-end transition-all 
                ${isInitialProcessing ? 'border-sky-500/50 bg-sky-950/20 shadow-[0_0_30px_rgba(14,165,233,0.1)]' :
                                        isFailed ? 'border-red-500/20 bg-red-950/10' :
                                            'border-white/5 bg-neutral-900/50 hover:border-white/20 hover:scale-[1.02]'}
                ${proj.canOpen && !isFailed ? 'cursor-pointer' : 'cursor-wait'}`}
                            >
                                <div className="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-transparent z-10" />

                                {!proj.isActive && (
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
                                    <Youtube className={`w-32 h-32 ${proj.isActive ? 'animate-pulse text-sky-400' : ''}`} />
                                </div>

                                <div className="relative z-20">
                                    <div className="flex flex-col gap-1 mb-3">
                                        <p className="text-base font-bold truncate text-white">
                                            {proj.title || "Project " + proj.version}
                                        </p>
                                        <h4 className="text-[10px] font-black uppercase tracking-widest text-neutral-500 flex flex-col gap-2">
                                            <div className="flex justify-between items-center">
                                                <span>{new Date(proj.timestamp * 1000).toLocaleDateString()} • {new Date(proj.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true })}</span>
                                                {proj.status === 'completed' && proj.total_clips > 0 && (
                                                    <span className={`text-[9px] font-bold ${isRenderingTask ? 'text-sky-400' : 'text-neutral-400'}`}>
                                                        {proj.published_count}/{proj.total_clips} publicados {isRenderingTask && "• Renderizando..."}
                                                    </span>
                                                )}
                                                {isInitialProcessing && (
                                                    <span className={`${proj.status === 'queued' ? 'bg-amber-500' : 'bg-sky-500'} text-white px-2 py-0.5 rounded-full animate-pulse text-[8px] tracking-tight`}>
                                                        {proj.status === 'queued' ? 'EN COLA' : 'EN PROCESO'}
                                                    </span>
                                                )}
                                                {isRenderingTask && (
                                                    <span className="bg-sky-500 shadow-[0_0_15px_rgba(14,165,233,0.8)] text-white px-2 py-0.5 rounded-full animate-pulse text-[8px] tracking-tight font-black uppercase">
                                                        RENDERIZANDO
                                                    </span>
                                                )}
                                                {isFailed && <span className="bg-red-500/80 text-white px-2 py-0.5 rounded-full text-[8px] tracking-tight font-black">ERROR</span>}
                                            </div>
                                            <div className="flex">
                                                <span className="bg-white/5 text-white/80 border border-white/10 px-2 py-1 rounded-lg text-[9px] font-black tracking-tighter">
                                                    {(() => {
                                                        const n = proj.niche || 'General';
                                                        return n.charAt(0).toUpperCase() + n.slice(1).toLowerCase();
                                                    })()}
                                                </span>
                                            </div>
                                        </h4>
                                    </div>

                                    {isInitialProcessing && proj.status !== 'queued' && (
                                        <div className="w-full h-1 bg-white/10 rounded-full overflow-hidden mt-2">
                                            <div
                                                className="h-full bg-sky-500 transition-all duration-500"
                                                style={{ width: `${proj.progress}%` }}
                                            />
                                        </div>
                                    )}
                                    {isInitialProcessing && proj.status === 'queued' && (
                                        <p className="text-[10px] font-medium text-neutral-500 mt-2 uppercase tracking-tight">Esperando turno...</p>
                                    )}
                                </div>

                                {!proj.isActive && !isFailed && (
                                    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-20 p-5 bg-white/10 backdrop-blur-md rounded-full shadow-2xl opacity-0 group-hover:opacity-100 transition-all scale-50 group-hover:scale-100 cursor-pointer">
                                        <Play className="w-6 h-6 fill-white" />
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>

            <footer className="py-24 text-center opacity-5 select-none pointer-events-none">
                <h2 className="text-[12rem] font-black tracking-[ -0.05em] uppercase italic">RocotoClip</h2>
            </footer>
        </main >
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
                        disabled={renderStatus?.status === 'rendering' || renderStatus?.status === 'queued'}
                        className={`px-6 py-2 rounded-xl text-[10px] font-black uppercase transition-all flex items-center gap-2 ${renderStatus?.status === 'rendering' || renderStatus?.status === 'queued' ? 'bg-white/10 text-white/50 cursor-not-allowed' : 'bg-white text-black hover:bg-neutral-200 cursor-pointer'}`}
                    >
                        {renderStatus?.status === 'rendering' ? (
                            <>
                                <Loader2 className="w-3 h-3 animate-spin" /> Renderizando...
                            </>
                        ) : renderStatus?.status === 'queued' ? (
                            <>
                                <Clock className="w-3 h-3" /> En Cola
                            </>
                        ) : (
                            'Final Render'
                        )}
                    </button>
                </div>
            </nav>

            <div className="flex-1 flex overflow-hidden">
                <div className="flex-1 flex flex-col bg-[#050505] overflow-hidden border-r border-white/5">
                    <div className="flex-1 flex items-center justify-center min-h-0 p-8">
                        <div className="h-full aspect-[9/16] bg-black rounded-[2rem] overflow-hidden shadow-2xl border border-white/5 relative editor-player-container">
                            <EditorPlayer
                                transcript={transcript}
                                selectedClipIdx={selectedClipIdx}
                                preferredLanguage={preferredLanguage}
                                authToken={authToken}
                                API_BASE={API_BASE}
                                playerRef={playerRef}
                            />

                            {/* Render Status Overlay/Indicator under player */}
                            {(renderStatus?.status === 'rendering' || renderStatus?.status === 'queued') && (
                                <div className="absolute bottom-4 left-4 right-4 bg-[#0a0a0a]/90 backdrop-blur-md rounded-xl border border-white/10 p-3 shadow-2xl z-50 transform transition-all">
                                    <div className="flex items-center justify-between mb-2">
                                        <div className="flex items-center gap-2">
                                            {renderStatus?.status === 'rendering' ? <Loader2 className="w-4 h-4 text-sky-400 animate-spin" /> : <Clock className="w-4 h-4 text-amber-400" />}
                                            <span className="text-[10px] font-black uppercase tracking-widest text-white">
                                                {renderStatus?.status === 'rendering' ? 'Renderizando clip' : 'En cola de espera'}
                                            </span>
                                        </div>
                                        <span className="text-[10px] tabular-nums font-bold text-neutral-400">
                                            {renderStatus?.status === 'rendering' ? `${renderStatus.progress}%` : '...'}
                                        </span>
                                    </div>
                                    <div className="w-full h-1 bg-white/10 rounded-full overflow-hidden">
                                        <div
                                            className={`h-full ${renderStatus?.status === 'queued' ? 'bg-amber-400 opacity-50' : 'bg-sky-400'} transition-all duration-500`}
                                            style={{ width: renderStatus?.status === 'queued' ? '100%' : `${renderStatus.progress || 0}%` }}
                                        />
                                    </div>
                                    <p className="text-[8px] text-neutral-500 mt-2 truncate font-medium">{renderStatus.message || 'Procesando...'}</p>
                                </div>
                            )}
                        </div>
                    </div>

                    <div className="h-64 bg-[#0a0a0a] border-t border-white/5 flex flex-col p-6 shadow-2xl z-10">
                        <div className="flex items-center justify-between mb-4">
                            <span className="text-[10px] uppercase tracking-widest font-black text-neutral-500 flex items-center gap-2">
                                <Scissors className="w-3 h-3" /> Rocoto Timeline
                            </span>
                            <div className="flex gap-6 items-center">
                                <div className="flex items-center gap-2">
                                    <span className="text-[10px] text-neutral-600 font-bold">Zoom</span>
                                    <input type="range" min="1" max="10" step="0.5" value={timelineZoom} onChange={(e) => setTimelineZoom(parseFloat(e.target.value))} className="w-24 accent-white h-1 bg-neutral-900 appearance-none rounded-full" />
                                </div>
                            </div>
                        </div>

                        <div className="flex-1 rounded-xl bg-[#050505] border border-white/5 relative overflow-x-auto overflow-y-hidden custom-scrollbar">
                            <div style={{ minWidth: `${timelineZoom * 100}%` }} className="h-full relative flex flex-col justify-center group">

                                <div className="h-8 w-full relative shrink-0">
                                    <div className="absolute inset-0 flex overflow-hidden opacity-90 transition-opacity">
                                        {(transcript?.clips?.[selectedClipIdx]?.framing_segments || [{ start: 0, end: transcript?.clips?.[selectedClipIdx]?.duration || 30, layout: transcript?.clips?.[selectedClipIdx]?.layout || 'single' }]).map((seg: any, idx: number) => {
                                            const clipDur = transcript?.clips?.[selectedClipIdx]?.duration || 30;
                                            const leftPct = (seg.start / clipDur) * 100;
                                            const widthPct = ((Math.min(seg.end, clipDur) - seg.start) / clipDur) * 100;
                                            return (
                                                <div key={idx} style={{ left: `${leftPct}%`, width: `${widthPct}%` }} className={`absolute h-full border-r border-[#050505] text-[8px] font-black flex items-center justify-center uppercase tracking-widest ${seg.layout === 'split' ? 'bg-white text-black' : 'bg-neutral-800 text-neutral-400'}`}>
                                                    {seg.layout}
                                                </div>
                                            )
                                        })}
                                    </div>
                                </div>

                                {(playerRef.current || currentFrame >= 0) && (
                                    <div
                                        id="rct-editor-playhead-line"
                                        className="absolute top-0 bottom-0 w-[1px] bg-red-500 z-20 pointer-events-none shadow-[0_0_10px_rgba(239,68,68,0.3)] transition-none"
                                    // Left is fully controlled by the native tick() animation frame to prevent react re-render snapping
                                    >
                                        <div className="absolute top-2 -translate-x-1/2 flex flex-col items-center">
                                            <svg width="12" height="16" viewBox="0 0 12 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                                                <path d="M0 2C0 0.89543 0.89543 0 2 0H10C11.1046 0 12 0.89543 12 2V10L6 16L0 10V2Z" fill="#ef4444" />
                                            </svg>
                                            <div id="rct-editor-playhead-label" className="text-[10px] text-red-500 font-bold mt-1 bg-black/50 px-1 rounded tabular-nums">
                                                0.0s
                                            </div>
                                        </div>
                                    </div>
                                )}

                                <input
                                    id="rct-editor-playhead-input"
                                    type="range"
                                    min="0"
                                    max={transcript?.clips?.[selectedClipIdx]?.duration || 30}
                                    step={1 / 30}
                                    defaultValue={currentFrame / 30}
                                    onChange={(e) => {
                                        const time = parseFloat(e.target.value);
                                        const frame = Math.round(time * 30);
                                        playerRef.current?.seekTo(frame);
                                        // Immediately update state so the red line reflects the drag position
                                        setCurrentFrame(frame);
                                    }}
                                    className="absolute inset-0 w-full h-full opacity-0 cursor-ew-resize z-30 m-0"
                                />
                            </div>
                        </div>
                    </div>
                </div>

                <div className="w-[350px] bg-[#020202] py-8 pr-8 pl-8 overflow-y-auto flex flex-col gap-10 custom-scrollbar z-20">
                    <h2 className="text-xs font-black uppercase tracking-widest text-neutral-600 italic">Overrides & Control</h2>

                    <section className="space-y-4">
                        <div className="p-6 bg-[#0a0a0a] border border-white/5 rounded-2xl flex flex-col gap-4">
                            <button
                                onClick={() => togglePublished(selectedClipIdx)}
                                className={`w-full py-4 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border flex items-center justify-center gap-2
                                    ${transcript?.clips?.[selectedClipIdx]?.published
                                        ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                                        : 'bg-white/5 border-white/10 text-neutral-400 hover:text-white hover:border-white/20'}`}
                            >
                                <Globe className="w-4 h-4" />
                                {transcript?.clips?.[selectedClipIdx]?.published ? 'Video publicado' : 'Marcar como publicado'}
                            </button>
                        </div>
                    </section>

                    <section className="space-y-4">
                        <div className="flex items-center gap-2 text-[10px] font-black uppercase text-neutral-500 tracking-widest">
                            <Scissors className="w-3 h-3" /> Timeline Cuts
                        </div>
                        <div className="p-6 bg-[#0a0a0a] border border-white/5 rounded-2xl flex flex-col gap-6">
                            <div className="flex flex-col gap-2">
                                <div className="flex justify-between items-end">
                                    <span className="text-[9px] uppercase font-bold text-neutral-500 tracking-widest">Start</span>
                                    <span className="text-sm font-black text-white">{(transcript?.clips?.[selectedClipIdx]?.start || 0).toFixed(2)}s</span>
                                </div>
                                <input type="range" min="0" max={transcript?.duration || 300} step="0.1"
                                    value={transcript?.clips?.[selectedClipIdx]?.start || 0}
                                    onChange={(e) => setClipBoundary('start', parseFloat(e.target.value))}
                                    className="w-full accent-white h-2 bg-neutral-900 rounded-full appearance-none cursor-ew-resize" />
                            </div>

                            <div className="flex flex-col gap-2">
                                <div className="flex justify-between items-end">
                                    <span className="text-[9px] uppercase font-bold text-neutral-500 tracking-widest">End</span>
                                    <span className="text-sm font-black text-white">{(transcript?.clips?.[selectedClipIdx]?.end || transcript?.duration || 0).toFixed(2)}s</span>
                                </div>
                                <input type="range" min="0" max={transcript?.duration || 300} step="0.1"
                                    value={transcript?.clips?.[selectedClipIdx]?.end || transcript?.duration || 0}
                                    onChange={(e) => setClipBoundary('end', parseFloat(e.target.value))}
                                    className="w-full accent-white h-2 bg-neutral-900 rounded-full appearance-none cursor-ew-resize" />
                            </div>
                            <div className="flex flex-col gap-2 mt-4 pt-4 border-t border-white/5">
                                <div className="text-[10px] text-neutral-500 font-bold uppercase tracking-widest text-center mb-1">Cortes desde el segundo actual</div>
                                <button onClick={() => addFramingCut('single')} className="w-full py-3 border border-blue-500/20 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 rounded-xl text-[9px] font-black uppercase tracking-widest transition-all cursor-pointer">
                                    ✂️ Forzar Vertical (Single)
                                </button>
                                <button onClick={() => addFramingCut('split')} className="w-full py-3 border border-purple-500/20 bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 rounded-xl text-[9px] font-black uppercase tracking-widest transition-all cursor-pointer">
                                    ✂️ Forzar Horizontal (Split)
                                </button>
                            </div>
                        </div>
                    </section>

                    <section className="space-y-6">
                        <div className="flex items-center gap-2 text-[10px] font-black uppercase text-neutral-500 tracking-widest">
                            <Layout className="w-3 h-3" /> AI Framing Center
                        </div>
                        <div className="p-6 bg-[#0a0a0a] border border-white/5 rounded-2xl space-y-6">
                            <div className="flex justify-between items-end">
                                <span className="text-[9px] uppercase font-bold text-neutral-500 tracking-widest">Offset X</span>
                                <span className="text-lg font-black text-white">{(((transcript?.clips?.[selectedClipIdx]?.center !== undefined ? transcript.clips[selectedClipIdx].center : transcript?.center) || 0.5) * 100).toFixed(0)}%</span>
                            </div>
                            <input type="range" min="0" max="1" step="0.01" value={(transcript?.clips?.[selectedClipIdx]?.center !== undefined ? transcript.clips[selectedClipIdx].center : transcript?.center) || 0.5}
                                onChange={(e) => {
                                    const next = { ...transcript };
                                    const val = parseFloat(e.target.value);
                                    if (selectedClipIdx !== null && next.clips && next.clips[selectedClipIdx]) {
                                        next.clips[selectedClipIdx].center = val;
                                    } else {
                                        next.center = val;
                                    }
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

            {/* GLOBAL MODALS */}
            {
                showDeleteModal && (
                    <div className="fixed inset-0 z-[300] flex items-center justify-center p-8 backdrop-blur-3xl bg-black/80 animate-in fade-in duration-500">
                        <div className="bg-[#050505] border border-white/5 rounded-[3rem] p-12 max-w-lg w-full shadow-[0_40px_100px_rgba(0,0,0,1)] border-t-white/10">
                            <div className="w-20 h-20 bg-white/5 rounded-[1.5rem] flex items-center justify-center mb-8 border border-white/5">
                                <Trash2 className="w-10 h-10 text-white" />
                            </div>
                            <h2 className="text-3xl font-black tracking-tighter text-white mb-4 uppercase italic">¿Eliminar Proyecto?</h2>
                            <p className="text-neutral-500 text-xs mb-10 leading-relaxed font-medium uppercase tracking-widest">
                                Esta acción es irreversible y eliminará todos los archivos, clips y análisis asociados a este video de forma permanente.
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
                )
            }

            {
                showCancelModal && (
                    <div className="fixed inset-0 z-[300] flex items-center justify-center p-8 backdrop-blur-3xl bg-black/80 animate-in fade-in duration-500">
                        <div className="bg-[#050505] border border-white/5 rounded-[3rem] p-12 max-w-lg w-full shadow-[0_40px_100px_rgba(0,0,0,1)] border-t-white/10">
                            <div className="w-20 h-20 bg-red-500/20 rounded-[1.5rem] flex items-center justify-center mb-8 border border-red-500/30">
                                <ShieldAlert className="w-10 h-10 text-red-500" />
                            </div>
                            <h2 className="text-3xl font-black tracking-tighter text-white mb-4 uppercase italic">Detener Renderizado</h2>
                            <p className="text-neutral-500 text-xs mb-10 leading-relaxed font-medium uppercase tracking-widest">
                                ¿Confirmas que deseas detener todos los procesos de renderizado en curso? Esta acción cancelará las tareas actuales y limpiará la cola de espera.
                            </p>
                            <div className="flex gap-4">
                                <button
                                    onClick={() => setShowCancelModal(false)}
                                    className="flex-1 px-8 py-4 bg-white/5 hover:bg-white/10 text-white font-black rounded-2xl uppercase text-[10px] tracking-widest transition-all cursor-pointer"
                                >
                                    Continuar Renderizado
                                </button>
                                <button
                                    onClick={handleCancelRender}
                                    className="flex-1 bg-red-600 text-white font-black py-4 rounded-2xl uppercase text-[10px] tracking-widest transition-all shadow-2xl"
                                >
                                    Detener Todo
                                </button>
                            </div>
                        </div>
                    </div>
                )
            }


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
