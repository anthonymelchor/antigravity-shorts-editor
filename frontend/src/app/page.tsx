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
  Check
} from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';



export default function Home() {
  const [url, setUrl] = useState('');
  const [view, setView] = useState<'dashboard' | 'results' | 'editor'>('dashboard');
  const [status, setStatus] = useState({
    status: 'idle',
    progress: 0,
    message: 'Ready',
    error: null as string | null
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


  useEffect(() => {
    fetchProjects();
  }, []);

  const fetchProjects = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/projects`);
      const data = await res.json();
      if (Array.isArray(data)) {
        // Find failed projects to show error and auto-cleanup
        const failedProj = data.find(p => p.status === 'failed');
        if (failedProj && !pendingDeletions.current.has(failedProj.version)) {
          setAlert({ msg: "Hubo un inconveniente, intenta de nuevo en unos minutos.", type: 'error' });
          // Auto-cleanup failed projects so they don't clutter the UI
          pendingDeletions.current.add(failedProj.version);
          fetch(`${API_BASE}/api/project/${failedProj.version}`, { method: 'DELETE' });
        }

        // If we were launching and now we see the project in the list, stop launching state
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





  useEffect(() => {
    checkInitialStatus();
  }, []);

  const checkInitialStatus = async () => {
    try {
      const transRes = await fetch(`${API_BASE}/api/transcript`);
      const transData = await transRes.json();
      if (transData && !transData.error) {
        setTranscript(transData);
        setStatus(prev => ({ ...prev, status: 'completed', progress: 100 }));
        // If we have a transcript, the project is "done"
      }
    } catch (err) { console.log("Empty project"); }
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
          const res = await fetch(`${API_BASE}/api/status`);
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
  }, [status.status]);

  // Dashboard Auto-Refresh: Keeps project list and progress cards updated
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (view === 'dashboard') {
      fetchProjects(); // Initial fetch
      interval = setInterval(fetchProjects, isLaunching ? 1000 : 3000);
    }
    return () => clearInterval(interval);
  }, [view, isLaunching]);

  const handleProcess = async () => {
    if (!url.trim()) return;

    // Global Duplicate Check: Check if any project in secondary list is already processing this URL
    const alreadyProcessing = projects.find(p => p.isActive && p.url === url.trim());
    if (alreadyProcessing) {
      setAlert({ msg: `Este video ya está siendo procesado: "${alreadyProcessing.title || 'Proyecto'}"`, type: 'warning' });
      setView('dashboard');
      return;
    }

    try {
      setAlert(null); // Clear previous alerts
      setIsLaunching(true);
      setActiveUrl(url.trim());
      processingRef.current = url.trim(); // LOCK INSTANTLY

      // Clear previous error state immediately
      setStatus({ status: 'processing', progress: 0, message: 'Waking up engine...', error: null });
      setTranscript(null);

      const res = await fetch(`${API_BASE}/api/process`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() })
      });
      const data = await res.json();

      if (data.version) {
        setCurrentVersion(String(data.version));
        versionRef.current = String(data.version);
        await fetchProjects(); // Initial check
      }

      setView('dashboard');
    } catch (err: any) {
      console.error(err);
      processingRef.current = null; // UNLOCK ON ERROR
      versionRef.current = null;
      setCurrentVersion(null);
      setStatus({ status: 'failed', progress: 0, message: 'Network Error', error: err.message });
      setAlert({ msg: "Hubo un inconveniente, intenta de nuevo en unos minutos.", type: 'error' });
      setIsLaunching(false); // Stop on hard error
    }

  };

  const handleReset = async () => {
    if (!confirm("HARD RESET: Deleting all project data. Continue?")) return;
    try {
      await fetch(`${API_BASE}/api/reset`, { method: 'POST' });
      setTranscript(null); setUrl('');
      setStatus({ status: 'idle', progress: 0, message: 'Project Cleared', error: null });
      setView('dashboard');
      fetchProjects();
    } catch (err: any) { console.error(err); }

  };

  const handleDeleteProject = async (version: string) => {
    try {
      await fetch(`${API_BASE}/api/project/${version}`, { method: 'DELETE' });
      setShowDeleteModal(null);
      fetchProjects();
      // If we are viewing this specific project, reset view
      if (transcript?.version === version) {
        setTranscript(null);
        setStatus({ status: 'idle', progress: 0, message: 'Ready', error: null });
      }
    } catch (err: any) { console.error(err); }

  };

  const loadProject = async (version: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/transcript/${version}`);
      const data = await res.json();
      if (data && !data.error) {
        setTranscript(data);
        setStatus({ status: 'completed', progress: 100, message: 'Loaded', error: null });
        setView('results');
      }
    } catch (err) { console.error("Failed to load project", err); }
  };


  const removeEmoji = (idxToRemove: number) => {
    if (!transcript) return;
    const newTranscript = { ...transcript };
    // Check if it's stored inside clips or globally
    const clipIcons = newTranscript?.clips?.[selectedClipIdx]?.edit_events?.icons;
    if (clipIcons && Array.isArray(clipIcons)) {
      newTranscript.clips[selectedClipIdx].edit_events.icons = clipIcons.filter((_: any, i: number) => i !== idxToRemove);
    } else if (newTranscript?.edit_events?.icons && Array.isArray(newTranscript.edit_events.icons)) {
      newTranscript.edit_events.icons = newTranscript.edit_events.icons.filter((_: any, i: number) => i !== idxToRemove);
    }
    setTranscript(newTranscript);
  };

  const handleRender = async (clipIdx?: number) => {
    if (!transcript?.version) {
      setAlert({ msg: "No version found to render", type: 'error' });
      return;
    }

    // Preparation: if clipIdx is passed, use that. Else use selectedForRender.
    const indicesToRender = clipIdx !== undefined ? [clipIdx] : selectedForRender;

    if (indicesToRender.length === 0) {
      setAlert({ msg: "No clips selected for rendering", type: 'error' });
      return;
    }

    try {
      setAlert({ msg: `Rendering ${indicesToRender.length} clip(s)...`, type: 'warning' });
      const res = await fetch(`${API_BASE}/api/render`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          version: transcript.version,
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
      {/* Navbar Results */}
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
            <span className="text-xs font-bold text-white">5 Clips Identified</span>
          </div>
        </div>
      </nav>



      {/* Top Menu for Results */}
      <div className="border-b border-white/5 py-4 px-12 flex justify-between items-center bg-[#050505] sticky top-0 z-50">
        <span className="text-xs font-bold text-neutral-500 uppercase tracking-widest">Select the clips you want to export</span>
        <button
          onClick={() => handleRender()}
          disabled={selectedForRender.length === 0}
          className="px-6 py-2 bg-purple-600 hover:bg-purple-500 text-white text-[10px] font-black uppercase tracking-widest rounded-xl disabled:opacity-30 transition-all shadow-[0_0_20px_rgba(147,51,234,0.3)] cursor-pointer">
          Render Selected ({selectedForRender.length})
        </button>
      </div>

      {/* Main Content Area - Cascade View */}
      <div className="flex-1 overflow-y-auto p-12 bg-black custom-scrollbar">
        <div className="max-w-6xl mx-auto flex flex-col gap-12 pb-24">
          {transcript?.clips?.map((clip: any, idx: number) => {
            const isSelected = selectedForRender.includes(idx);
            const toggleSelect = () => setSelectedForRender(prev =>
              prev.includes(idx) ? prev.filter(i => i !== idx) : [...prev, idx]
            );

            return (
              <div key={idx} className="flex gap-10 items-start">

                {/* Left Column: Number & Checkbox & Score */}
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

                {/* Main Card (Cascade) */}
                <div className="flex-1 bg-[#0a0a0a] rounded-[2.5rem] border border-white/5 flex flex-col overflow-hidden shadow-2xl relative">

                  {/* Card Header for the title & edit */}
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

                  {/* Card Body: Video Preview + Details */}
                  <div className="flex bg-[#050505] p-6 gap-8">
                    {/* Vertical Preview (Left half inside card, tighter width) */}
                    <div className="w-[30%] min-w-[200px] flex justify-center items-start">
                      <div className="w-[200px] aspect-[9/16] bg-black rounded-lg overflow-hidden shadow-2xl border border-white/10 relative">
                        {/* Always sync player to specific clip duration logic if possible, else standard duration */}
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

                    {/* Analysis & Transcript (Right half inside card) */}
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
                            {/* Rendering words based on preferred language – FIX: using clip.words_es / clip.words */}
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

      {/* BRANDING */}
      <div className="mb-12 flex flex-col items-center">
        <h1 className="text-5xl font-bold tracking-tighter uppercase text-white">RocotoClip</h1>
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
              <button className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-neutral-500 hover:text-white transition-all cursor-pointer">
                <Upload className="w-4 h-4" /> Upload
              </button>
              <button className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-neutral-500 hover:text-white transition-all cursor-pointer">
                <Cloud className="w-4 h-4" /> Google Drive
              </button>
            </div>

            <button
              onClick={handleProcess}
              disabled={isLaunching}
              className={`bg-white text-black px-12 py-5 rounded-[1.5rem] font-black uppercase text-[12px] tracking-tighter transition-all shadow-[0_10px_40px_rgba(255,255,255,0.1)] active:scale-95 flex items-center gap-2
                ${isLaunching ? 'opacity-50 cursor-wait bg-neutral-400' : 'hover:bg-neutral-200 cursor-pointer'}`}
            >
              {isLaunching ? (
                <>
                  <div className="w-3 h-3 border-2 border-black/30 border-t-black rounded-full animate-spin" />
                  Starting...
                </>
              ) : 'Analyze'}
            </button>

          </div>

          {/* LOADING LINE (CONTAINED WITHIN CARD) */}
          <div className="mx-8 mt-2 h-[3px] overflow-hidden rounded-full">
            {isLaunching && (
              <div className="h-full bg-sky-500/30 w-full relative">
                <div className="absolute top-0 bottom-0 bg-white animate-[loadingLine_2s_infinite_linear] w-[60%] shadow-[0_0_25px_rgba(255,255,255,1)]" />
              </div>
            )}
          </div>
        </div>

        {/* ALERT BANNER (OUTSIDE / BELOW CARD) */}
        {alert && (
          <div className={`mt-6 w-full flex items-center gap-4 border py-5 px-8 rounded-[2.5rem] animate-in fade-in slide-in-from-top-2 duration-500 shadow-2xl transition-colors
            ${alert.type === 'error' ? 'bg-rose-500/10 border-rose-500/10 text-rose-500/90' : 'bg-amber-500/10 border-amber-500/10 text-amber-500/90'}`}>
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

      {/* PROJECTS CONTAINER */}
      {/* PROJECTS GRID */}
      <div className="mt-16 w-full max-w-4xl grid grid-cols-2 md:grid-cols-3 gap-6 animate-in fade-in slide-in-from-bottom-8 duration-700">

        {/* Existing & Active Projects are now consolidated in one list */}

        {/* Existing Projects */}
        {Array.isArray(projects) && projects.map((proj) => {
          const isProcessing = proj.isActive;
          const isFailed = proj.status === 'failed';

          return (
            <div
              key={proj.version}
              onClick={() => !isProcessing && !isFailed && loadProject(proj.version)}
              className={`relative group h-48 rounded-[2rem] border overflow-hidden p-6 flex flex-col justify-end transition-all cursor-pointer 
                ${isProcessing ? 'border-sky-500/50 bg-sky-950/20 cursor-wait' :
                  isFailed ? 'border-red-500/40 bg-red-950/10 cursor-default' :
                    'border-white/5 bg-neutral-900 hover:border-white/20 hover:scale-[1.02]'}`}
            >
              <div className="absolute inset-0 bg-gradient-to-t from-black via-black/20 to-transparent z-10" />

              {/* Delete Button - Only for completed or failed projects */}
              {!isProcessing && (
                <button
                  onClick={(e) => { e.stopPropagation(); setShowDeleteModal(proj.version); }}
                  className="absolute top-4 right-4 z-30 p-2 bg-black/50 hover:bg-red-500/80 text-white rounded-full opacity-0 group-hover:opacity-100 transition-all scale-75 group-hover:scale-100"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </button>
              )}

              <div className="absolute inset-0 flex items-center justify-center opacity-10">
                <Video className={`w-24 h-24 ${isProcessing ? 'animate-pulse text-sky-400' : ''}`} />
              </div>

              <div className="relative z-20">
                <div className="flex flex-col gap-1 mb-3">
                  <p className="text-sm font-bold truncate text-white">
                    {proj.title}
                  </p>
                  <h4 className="text-[10px] font-black uppercase tracking-widest text-white/50 flex justify-between items-center">
                    <span>{new Date(proj.timestamp * 1000).toLocaleDateString()} • {new Date(proj.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true })}</span>
                    {isProcessing && <span className="bg-sky-500 text-white px-2 py-0.5 rounded-full animate-pulse text-[8px] tracking-tight">EN PROCESO</span>}
                    {isFailed && <span className="bg-red-500 text-white px-2 py-0.5 rounded-full text-[8px] tracking-tight">ERROR</span>}
                  </h4>
                </div>

                {isProcessing && (
                  <div className="w-full h-1 bg-white/10 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-sky-500 transition-all duration-500"
                      style={{ width: `${proj.progress}%` }}
                    />
                    <p className="text-[10px] text-sky-400 font-bold mt-2 animate-pulse uppercase tracking-tighter">
                      {proj.message || 'Processing...'}
                    </p>
                  </div>
                )}

                {isFailed && (
                  <p className="text-[10px] text-red-500 font-bold mt-2 uppercase tracking-tighter truncate">
                    {proj.error || 'Error desconocido'}
                  </p>
                )}
              </div>

              {!isProcessing && (
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-20 p-4 bg-white/10 backdrop-blur-md rounded-full shadow-2xl opacity-0 group-hover:opacity-100 transition-all scale-50 group-hover:scale-100 cursor-pointer">
                  <Play className="w-6 h-6 fill-white" />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* DELETE CONFIRMATION MODAL */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-[100] bg-black/90 backdrop-blur-sm flex items-center justify-center p-6 animate-in fade-in duration-300">
          <div className="max-w-md w-full bg-[#0a0a0a] border border-white/10 p-10 rounded-[3rem] text-center shadow-[0_0_100px_rgba(0,0,0,1)]">
            <div className="w-20 h-20 bg-red-500/10 rounded-full flex items-center justify-center mx-auto mb-8">
              <ShieldAlert className="w-10 h-10 text-red-500" />
            </div>
            <h2 className="text-2xl font-black uppercase text-white mb-4 tracking-tighter">Eliminar Proyecto</h2>
            <p className="text-neutral-400 text-sm mb-10 leading-relaxed">
              ¿Estás seguro de que quieres borrar este proyecto? Se eliminarán permanentemente todos los videos, audios y archivos asociados.
            </p>
            <div className="flex gap-4">
              <button
                onClick={() => setShowDeleteModal(null)}
                className="flex-1 px-8 py-4 bg-white/5 hover:bg-white/10 text-white font-bold rounded-2xl uppercase text-[10px] tracking-widest transition-all cursor-pointer"
              >
                No, cancelar
              </button>
              <button
                onClick={() => handleDeleteProject(showDeleteModal)}
                className="flex-1 bg-red-600 hover:bg-red-500 text-white font-black py-4 rounded-2xl uppercase text-[10px] tracking-widest transition-all shadow-2xl shadow-red-500/20"
              >
                Sí, eliminar
              </button>
            </div>
          </div>
        </div>
      )}



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
        {/* Left Area: Video + Timeline Floor */}
        <div className="flex-1 flex flex-col bg-[#050505] overflow-hidden border-r border-white/5">

          {/* Main Video Area */}
          <div className="flex-1 flex items-center justify-center min-h-0 p-8">
            <div className="h-full aspect-[9/16] bg-black rounded-[2rem] overflow-hidden shadow-2xl border border-white/5">
              <Player
                ref={playerRef}
                component={Main}
                durationInFrames={Math.ceil((transcript?.clips?.[selectedClipIdx]?.duration || 30) * 30)}
                compositionWidth={1080} compositionHeight={1920} fps={30}
                style={{ width: '100%', height: '100%' }} controls
                inputProps={{
                  // Pass the SPECIFIC clip transcript data
                  transcript: { ...transcript, ...transcript?.clips?.[selectedClipIdx] },
                  isPlayer: true,
                  preferredLanguage
                }}
              />
            </div>
          </div>

          {/* Bottom Timeline Rack */}
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

            {/* Tracks Representation */}
            <div className="flex-1 rounded-xl bg-black border border-white/5 relative overflow-x-auto overflow-y-hidden custom-scrollbar flex flex-col py-2 px-4 gap-2">

              {/* Visual Video Track Mockup */}
              <div className="h-6 w-full bg-white/5 rounded-md flex items-center px-4 relative shrink-0">
                <Video className="w-3 h-3 text-neutral-600 absolute left-2" />
                <div className="w-full text-center text-[8px] text-neutral-700 tracking-widest font-bold">BASE VIDEO LAYER</div>
              </div>

              {/* Emojis Track */}
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

              {/* Words Track */}
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

          {/* Timeline / Cuts Control */}
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



          {/* Framing / Crop Center */}
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
                onChange={(e) => setTranscript({ ...transcript, center: parseFloat(e.target.value) })}
                className="w-full accent-white h-2 bg-neutral-900 rounded-full appearance-none" />
            </div>
          </section>
        </div>
      </div>
    </main>
  );

  return (
    <div className="relative min-h-screen bg-black">
      {/* MAIN CONTENT - NO GHOSTING FOR OPERATIONAL FAILURES */}
      <div className="transition-all duration-700">
        {view === 'dashboard' && dashboardView}
        {view === 'results' && resultsLayout}
        {view === 'editor' && editorView}
      </div>


      <style jsx global>{`
        body { background: black; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
        input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; height: 24px; width: 24px; border-radius: 50%; background: #ffffff; cursor: pointer; border: 4px solid #000; box-shadow: 0 0 15px rgba(255,255,255,0.3); }
      `}</style>
    </div>
  );


}
