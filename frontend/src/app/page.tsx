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

// --- ERROR LOGGING HELPER ---
const logErrorToBackend = async (error: any, context?: string) => {
  try {
    await fetch(`${API_BASE}/api/log-error`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: error.message || String(error),
        stack: error.stack,
        context: context || 'General UI Error',
        url: window.location.href,
        userAgent: navigator.userAgent
      })
    });
  } catch (err) {
    console.error("Critical: Failed to report error to backend", err);
  }
};

// --- ERROR BOUNDARY COMPONENT ---
class GlobalErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) { logErrorToBackend(error, errorInfo.componentStack ?? undefined); }
  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-black flex flex-col items-center justify-center p-8 text-center">
          <ShieldAlert className="w-16 h-16 text-red-500 mb-6" />
          <h1 className="text-2xl font-bold mb-4 text-white uppercase tracking-tighter">System Error</h1>
          <button onClick={() => window.location.reload()} className="px-8 py-3 bg-white text-black font-bold uppercase rounded-xl">Restart</button>
        </div>
      );
    }
    return this.props.children;
  }
}

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
  const playerRef = useRef<PlayerRef>(null);

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
    let interval: NodeJS.Timeout;
    if (status.status !== 'idle' && status.status !== 'completed' && status.status !== 'failed') {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE}/api/status`);
          const data = await res.json();
          setStatus(data);
          if (data.status === 'completed') {
            checkInitialStatus();
          }
        } catch (err) { console.error("Poll failed", err); }
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [status.status]);

  const handleProcess = async () => {
    if (!url.trim()) return;
    try {
      setTranscript(null);
      await fetch(`${API_BASE}/api/process`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      });
      setStatus({ status: 'processing', progress: 0, message: 'Waking up engine...', error: null });
      setView('dashboard');
    } catch (err: any) {
      logErrorToBackend(err, 'handleProcess');
      setStatus({ ...status, status: 'failed', error: 'Internal Engine Communication Error' });
    }
  };

  const handleReset = async () => {
    if (!confirm("HARD RESET: Deleting all project data. Continue?")) return;
    try {
      await fetch(`${API_BASE}/api/reset`, { method: 'POST' });
      setTranscript(null); setUrl('');
      setStatus({ status: 'idle', progress: 0, message: 'Project Cleared', error: null });
      setView('dashboard');
    } catch (err: any) { logErrorToBackend(err, 'handleReset'); }
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

  const resultsLayout = (
    <div className="flex-1 flex flex-col bg-black">
      {/* Navbar Results */}
      <nav className="border-b border-white/5 px-12 h-20 flex items-center justify-between bg-black/50 backdrop-blur-xl">
        <div className="flex items-center gap-4">
          <button onClick={() => setView('dashboard')} className="p-2 hover:bg-white/5 rounded-full transition-all">
            <ChevronRight className="w-5 h-5 rotate-180" />
          </button>
          <h1 className="text-xl font-bold tracking-tighter uppercase">RocotoClip</h1>
        </div>
        <div className="flex items-center gap-6">
          <div className="flex flex-col items-end">
            <span className="text-[10px] font-black text-neutral-500 uppercase">Analysis Complete</span>
            <span className="text-xs font-bold text-white">5 Clips Identified</span>
          </div>
        </div>
      </nav>

      {/* ERROR OVERLAY IF FAILED WHILE VIEWING */}
      {status.status === 'failed' && (
        <div className="absolute inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-12">
          <div className="max-w-md w-full bg-neutral-900 border border-red-500/20 p-10 rounded-[3rem] text-center shadow-2xl">
            <ShieldAlert className="w-12 h-12 text-red-500 mx-auto mb-6" />
            <h2 className="text-xl font-black uppercase text-white mb-4">Lo sentimos</h2>
            <p className="text-neutral-400 text-sm mb-8">Hubo un fallo en el proceso, estamos trabajando para solucionarlo.</p>
            <button
              onClick={() => setView('dashboard')}
              className="w-full bg-white text-black font-black py-4 rounded-2xl uppercase text-[10px] tracking-widest hover:bg-neutral-200 transition-all"
            >
              Volver al Panel
            </button>
          </div>
        </div>
      )}

      {/* Top Menu for Results */}
      <div className="border-b border-white/5 py-4 px-12 flex justify-between items-center bg-[#050505] sticky top-0 z-50">
        <span className="text-xs font-bold text-neutral-500 uppercase tracking-widest">Select the clips you want to export</span>
        <button
          disabled={selectedForRender.length === 0}
          className="px-6 py-2 bg-purple-600 hover:bg-purple-500 text-white text-[10px] font-black uppercase tracking-widest rounded-xl disabled:opacity-30 transition-all shadow-[0_0_20px_rgba(147,51,234,0.3)]">
          Render Selected ({selectedForRender.length})
        </button>
      </div>

      {/* Main Content Area - Cascade View */}
      <div className="flex-1 overflow-y-auto p-12 bg-black custom-scrollbar">
        <div className="max-w-6xl mx-auto flex flex-col gap-12 pb-24">
          {transcript?.clips?.slice(0, 1).map((clip: any, idx: number) => {
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
                    <button onClick={() => { setSelectedClipIdx(idx); setView('editor'); }} className="w-10 h-10 flex items-center justify-center bg-white text-black hover:bg-neutral-200 rounded-xl transition-transform hover:scale-105 shadow-xl">
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
                          inputProps={{ transcript, isPlayer: true }}
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
                            {/* Rendering words (in a real scenario, filter based on clip start/end) */}
                            {transcript?.words?.map((w: any, id: number) => <span key={id} className="hover:text-white transition-colors cursor-default">{w.word} </span>)}
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
              <button className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-neutral-500 hover:text-white transition-all">
                <Upload className="w-4 h-4" /> Upload
              </button>
              <button className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-neutral-500 hover:text-white transition-all">
                <Cloud className="w-4 h-4" /> Google Drive
              </button>
            </div>

            <button
              onClick={handleProcess}
              disabled={status.status !== 'idle' && status.status !== 'failed'}
              className="bg-white text-black px-12 py-5 rounded-[1.5rem] font-black uppercase text-[12px] tracking-tighter hover:bg-neutral-200 transition-all shadow-[0_10px_40px_rgba(255,255,255,0.1)] active:scale-95 disabled:opacity-30"
            >
              {status.status === 'idle' || status.status === 'failed' ? 'Get clips in 1 click' : 'Analyzing...'}
            </button>
          </div>
        </div>
      </div>

      {/* PROJECTS CONTAINER */}
      {(status.status !== 'idle' || transcript) && (
        <div className="mt-16 w-full max-w-2xl grid grid-cols-2 gap-6 animate-in fade-in slide-in-from-bottom-8 duration-700">
          <div
            onClick={() => transcript && setView('results')}
            className={`relative group h-48 rounded-[2rem] border overflow-hidden p-6 flex flex-col justify-end transition-all cursor-pointer ${transcript ? 'bg-neutral-900 border-white/10 hover:border-white/30' : status.status === 'failed' ? 'bg-red-500/5 border-red-500/20' : 'bg-black border-white/5'}`}
          >
            {status.status === 'failed' && <div className="absolute inset-0 bg-red-500/5 z-0" />}
            {transcript ? (
              <div className="absolute inset-0 bg-gradient-to-t from-black via-black/20 to-transparent z-10" />
            ) : (
              <div className="absolute inset-0 bg-[#050505] animate-pulse z-0" />
            )}

            {/* Fake thumbnail content */}
            <div className="absolute inset-0 flex items-center justify-center opacity-10">
              <Video className="w-24 h-24" />
            </div>

            <div className="relative z-20">
              <h4 className={`text-xs font-black uppercase tracking-widest mb-1 ${status.status === 'failed' ? 'text-red-500' : 'text-white/50'}`}>
                {transcript ? 'Current Project' : status.status === 'failed' ? 'Pipeline Failed' : 'Processing...'}
              </h4>
              <p className={`text-sm font-bold truncate max-w-[200px] ${status.status === 'failed' ? 'text-red-400' : 'text-white'}`}>
                {transcript?.clips?.[0]?.title || url || 'Inbound Video Job'}
              </p>
            </div>

            {/* Progress/Loading Bar at the bottom */}
            {!transcript && (
              <div className="absolute bottom-0 left-0 right-0 h-1 bg-white/5 overflow-hidden">
                <div className="h-full bg-white transition-all duration-1000" style={{ width: `${status.progress}%` }} />
              </div>
            )}
            {transcript && (
              <div className="absolute top-6 right-6 z-20 p-2 bg-purple-600 rounded-full shadow-2xl scale-0 group-hover:scale-100 transition-transform">
                <ChevronRight className="w-4 h-4" />
              </div>
            )}
          </div>
        </div>
      )}

      {/* ERROR FOOTER */}
      {status.status === 'failed' && (
        <div className="mt-8 w-full max-w-2xl animate-in fade-in slide-in-from-top-4 duration-500">
          <div className="bg-red-500/10 border border-red-500/20 px-8 py-6 rounded-[2.5rem] flex items-center justify-between gap-6">
            <div className="flex items-center gap-4">
              <ShieldAlert className="w-6 h-6 text-red-500" />
              <div className="flex flex-col">
                <span className="text-[10px] font-black uppercase text-red-500 tracking-widest">Aviso del Sistema</span>
                <span className="text-xs font-bold text-red-400/80 leading-relaxed">Hubo un fallo en el proceso, estamos trabajando para solucionarlo.</span>
              </div>
            </div>
            <button
              onClick={handleReset}
              className="px-6 py-3 bg-red-500/20 hover:bg-red-500/40 text-red-500 text-[9px] font-black uppercase rounded-xl transition-all"
            >
              Reintentar
            </button>
          </div>
        </div>
      )}
    </main>
  );

  const editorView = (
    <main className="min-h-screen bg-black text-white font-sans flex flex-col">
      <nav className="border-b border-white/10 px-8 flex items-center justify-between h-16">
        <div className="flex items-center gap-4">
          <button onClick={() => setView('results')} className="p-2 hover:bg-white/5 rounded-full transition-all">
            <ChevronRight className="w-5 h-5 rotate-180" />
          </button>
          <h1 className="text-xl font-bold tracking-tighter uppercase">RocotoClip <span className="text-neutral-500">Editor</span></h1>
        </div>
        <div className="flex items-center gap-6">
          <button onClick={handleReset} className="text-[10px] font-bold uppercase text-neutral-500 hover:text-red-500 transition-colors flex items-center gap-2">
            <RotateCcw className="w-3 h-3" /> Reset Project
          </button>
          <button className="bg-white text-black px-6 py-2 rounded-xl text-[10px] font-black uppercase hover:bg-neutral-200 transition-all">
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
              <Player ref={playerRef} component={Main} durationInFrames={Math.ceil((transcript?.duration || 30) * 30)}
                compositionWidth={1080} compositionHeight={1920} fps={30} style={{ width: '100%', height: '100%' }} controls
                inputProps={{ transcript, isPlayer: true }} />
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
                      <button onClick={(e) => { e.stopPropagation(); removeEmoji(idx); }} className="p-0.5 hover:bg-black/50 rounded-full text-red-400 opacity-50 hover:opacity-100 transition-opacity">
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
              <button className="w-full mt-2 py-3 border border-white/10 hover:bg-white/10 text-white rounded-xl text-[9px] font-black uppercase tracking-widest transition-all">
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
    <GlobalErrorBoundary>
      {view === 'dashboard' && dashboardView}
      {view === 'results' && resultsLayout}
      {view === 'editor' && editorView}
      <style jsx global>{`
        body { background: black; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
        input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; height: 24px; width: 24px; border-radius: 50%; background: #ffffff; cursor: pointer; border: 4px solid #000; box-shadow: 0 0 15px rgba(255,255,255,0.3); }
      `}</style>
    </GlobalErrorBoundary>
  );
}
