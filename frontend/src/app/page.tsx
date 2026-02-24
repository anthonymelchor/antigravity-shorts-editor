'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Player, PlayerRef } from '@remotion/player';
import { Main } from '../remotion/Composition';
import {
  Play,
  Youtube,
  Cpu,
  Download,
  Settings,
  CheckCircle2,
  XCircle,
  Loader2,
  Rocket,
  MoveHorizontal,
  LayoutTemplate,
  Scissors,
  Split,
  Trash2,
  Clock,
  Maximize2,
  Minimize2,
  Zap,
  Eye,
  EyeOff,
  SkipBack,
  SkipForward,
  RotateCcw,
  Type,
  Check,
  Eraser
} from 'lucide-react';

export default function Home() {
  const [url, setUrl] = useState('');
  const [status, setStatus] = useState({
    status: 'idle',
    progress: 0,
    message: 'Ready',
    error: null as string | null
  });
  const [transcript, setTranscript] = useState<any>(null);
  const [previewKey, setPreviewKey] = useState(0);
  const [showGuides, setShowGuides] = useState(true); // Default ON
  const playerRef = useRef<PlayerRef>(null);

  const [currentTime, setCurrentTime] = useState(0);
  const [activeSegmentIdx, setActiveSegmentIdx] = useState<number>(0);
  const [showTranscriptEditor, setShowTranscriptEditor] = useState(false);

  useEffect(() => {
    checkInitialStatus();
  }, []);

  const checkInitialStatus = async () => {
    try {
      const transRes = await fetch('http://127.0.0.1:8000/api/transcript');
      const transData = await transRes.json();
      if (transData && !transData.error) {
        if (!transData.framing_segments) {
          const duration = transData.words[transData.words.length - 1]?.end || 30;
          transData.framing_segments = [{ start: 0, end: duration, center: transData.center || 0.5 }];
        }
        setTranscript(transData);
        setStatus(prev => ({ ...prev, status: 'completed', progress: 100 }));
      }
    } catch (err) {
      console.log("Empty project");
    }
  };

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (status.status !== 'idle' && status.status !== 'completed' && status.status !== 'failed') {
      interval = setInterval(async () => {
        try {
          const res = await fetch('http://127.0.0.1:8000/api/status');
          const data = await res.json();
          setStatus(data);

          if (data.status === 'completed') {
            checkInitialStatus();
            setPreviewKey(prev => prev + 1);
          }
        } catch (err) { console.error("Poll failed", err); }
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [status.status]);

  useEffect(() => {
    const player = playerRef.current;
    if (!player) return;
    const interval = setInterval(() => {
      const frame = player.getCurrentFrame();
      const time = frame / 30;
      setCurrentTime(time);
      if (transcript?.framing_segments) {
        const idx = transcript.framing_segments.findIndex((s: any) => time >= s.start && time < s.end);
        if (idx !== -1 && idx !== activeSegmentIdx) setActiveSegmentIdx(idx);
      }
    }, 33);
    return () => clearInterval(interval);
  }, [transcript, activeSegmentIdx]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'TEXTAREA') return;
      if (!playerRef.current) return;
      const f = playerRef.current.getCurrentFrame();
      if (e.key === 'ArrowRight' || e.key === 'l') playerRef.current.seekTo(f + (e.shiftKey ? 30 : 2));
      else if (e.key === 'ArrowLeft' || e.key === 'j') playerRef.current.seekTo(Math.max(0, f - (e.shiftKey ? 30 : 2)));
      else if (e.key === ' ') { e.preventDefault(); playerRef.current.isPlaying() ? playerRef.current.pause() : playerRef.current.play(); }
      else if (e.key === 's') addCut();
      else if (e.key === 'g') setShowGuides(prev => !prev);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [transcript]);

  const handleProcess = async () => {
    if (!url.trim()) {
      setStatus({ ...status, status: 'failed', error: 'Please enter a valid YouTube URL first.' });
      return;
    }
    try {
      const res = await fetch('http://127.0.0.1:8000/api/process', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      });
      setStatus({ status: 'processing', progress: 0, message: 'Waking up engine...', error: null });
    } catch (err: any) { setStatus({ ...status, status: 'failed', error: err.message }); }
  };

  const handleReset = async () => {
    if (!confirm("HARD RESET: Deleting all project data and temporary files. Continue?")) return;
    try {
      await fetch('http://127.0.0.1:8000/api/reset', { method: 'POST' });
      setTranscript(null); setUrl('');
      setStatus({ status: 'idle', progress: 0, message: 'Project Cleared', error: null });
    } catch (err) { console.error("Reset failed"); }
  };

  const handleRender = async () => {
    try {
      await fetch('http://127.0.0.1:8000/api/render', { method: 'POST' });
      setStatus({ status: 'rendering', progress: 10, message: 'Generating Final Clip...', error: null });
    } catch (err: any) { setStatus({ ...status, status: 'failed', error: err.message }); }
  };

  const saveToBackend = async (data: any) => {
    try {
      await fetch('http://127.0.0.1:8000/api/update-framing', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
    } catch (err) { console.error("Update failed", err); }
  };

  const updateSegmentCenter = (idx: number, center: number) => {
    const newSegments = [...transcript.framing_segments];
    newSegments[idx].center = center;
    const updated = { ...transcript, framing_segments: newSegments };
    setTranscript(updated);
    saveToBackend(updated);
  };

  const deleteWord = (wordIdx: number) => {
    const newWords = [...transcript.words];
    newWords.splice(wordIdx, 1);
    const updated = { ...transcript, words: newWords };
    setTranscript(updated);
    saveToBackend(updated);
  };

  const removeVFXFromCurrentSegment = () => {
    // Deletes VFX elements that occur within the active segment
    if (!transcript) return;
    const seg = transcript.framing_segments[activeSegmentIdx];
    const newZooms = transcript.edit_events.zooms.filter((z: any) => z.time < seg.start || z.time > seg.end);
    const newIcons = transcript.edit_events.icons.filter((i: any) => i.time < seg.start || i.time > seg.end);

    const updated = {
      ...transcript,
      edit_events: { ...transcript.edit_events, zooms: newZooms, icons: newIcons }
    };
    setTranscript(updated);
    saveToBackend(updated);
  };

  const addCut = () => {
    if (!playerRef.current || !transcript) return;
    const t = playerRef.current.getCurrentFrame() / 30;
    const idx = transcript.framing_segments.findIndex((s: any) => t > s.start && t < s.end);
    if (idx === -1) return;
    const old = transcript.framing_segments[idx];
    const newSegs = [...transcript.framing_segments.slice(0, idx + 1), { start: t, end: old.end, center: old.center }, ...transcript.framing_segments.slice(idx + 1)];
    newSegs[idx].end = t;
    const updated = { ...transcript, framing_segments: newSegs };
    setTranscript(updated);
    setActiveSegmentIdx(idx + 1);
    saveToBackend(updated);
  };

  const deleteSegment = (idx: number) => {
    if (transcript.framing_segments.length <= 1) return;
    const newSegs = [...transcript.framing_segments];
    if (idx > 0) { newSegs[idx - 1].end = newSegs[idx].end; newSegs.splice(idx, 1); setActiveSegmentIdx(idx - 1); }
    else { newSegs[idx + 1].start = newSegs[idx].start; newSegs.splice(idx, 1); setActiveSegmentIdx(0); }
    const updated = { ...transcript, framing_segments: newSegs };
    setTranscript(updated);
    saveToBackend(updated);
  };

  const getDuration = () => {
    if (!transcript) return 30;
    if (transcript.duration) return transcript.duration;
    if (transcript.words && transcript.words.length > 0) return transcript.words[transcript.words.length - 1].end;
    return 30;
  };

  const handleTimelineClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    playerRef.current?.seekTo(Math.round(((x / rect.width) * getDuration()) * 30));
  };

  const inputProps = useMemo(() => {
    return {
      transcript,
      videoSrcOverride: '/output_vertical_clip.mp4',
      isWorkspaceView: showGuides,
      isPlayer: true
    };
  }, [transcript, showGuides]);

  return (
    <main className="min-h-screen bg-[#020202] text-neutral-100 font-sans selection:bg-purple-500/30 overflow-hidden flex flex-col">
      <div className="fixed inset-0 pointer-events-none opacity-20" style={{ backgroundImage: 'url("https://grainy-gradients.vercel.app/noise.svg")' }} />

      {/* Navbar */}
      <nav className="relative z-50 border-b border-white/5 bg-black/60 backdrop-blur-3xl px-8 flex items-center justify-between h-16 shadow-2xl">
        <div className="flex items-center gap-5">
          <div className="w-10 h-10 bg-gradient-to-tr from-purple-600 via-indigo-500 to-blue-500 rounded-[12px] flex items-center justify-center shadow-2xl shadow-purple-500/30 ring-1 ring-white/20">
            <Zap className="w-5 h-5 text-white fill-current" />
          </div>
          <div className="flex flex-col">
            <span className="text-lg font-black tracking-tighter uppercase leading-none">Antigravity <span className="text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-indigo-400">PRO V5.0</span></span>
            <span className="text-[9px] text-neutral-600 font-bold tracking-[0.3em] uppercase mt-1">Master Editor Engine</span>
          </div>
        </div>

        <div className="flex items-center gap-8">
          <button onClick={handleReset} disabled={!transcript && status.status === 'idle'} className={`flex items-center gap-2 text-[10px] font-black uppercase tracking-widest transition-all group ${(!transcript && status.status === 'idle') ? 'text-neutral-700 cursor-not-allowed' : 'text-neutral-500 hover:text-red-400'}`}>
            <RotateCcw className={`w-4 h-4 ${(!transcript && status.status === 'idle') ? '' : 'group-hover:rotate-[-45deg]'} transition-transform`} /> Emergency Reset
          </button>
          <div className="h-4 w-px bg-white/10" />
          <button onClick={handleRender} disabled={!transcript || status.status === 'rendering'} className={`text-[10px] font-black uppercase tracking-widest px-8 py-3 rounded-2xl transition-all shadow-xl active:scale-95 ${!transcript ? 'bg-white/10 text-white/20 cursor-not-allowed' : 'bg-white text-black hover:bg-purple-500 hover:text-white disabled:opacity-30'}`}>
            {status.status === 'rendering' ? 'Rendering...' : 'Finalize & Render'}
          </button>
        </div>
      </nav>

      <div className="relative z-10 flex-1 flex overflow-hidden">
        {/* Workspace Body */}
        <div className="flex-1 flex flex-col bg-[#050505] border-r border-white/5 relative">

          <div className="flex-1 flex items-center justify-center p-8">
            <div className={`aspect-video w-full max-w-5xl bg-black rounded-3xl overflow-hidden shadow-[0_0_120px_rgba(0,0,0,1)] border border-white/10 relative transition-all duration-500`}>
              {transcript ? (
                <Player ref={playerRef} key={previewKey} component={Main} durationInFrames={Math.ceil(getDuration() * 30)}
                  compositionWidth={showGuides ? 1920 : 1080}
                  compositionHeight={showGuides ? 1080 : 1920}
                  fps={30} style={{ width: '100%', height: '100%' }} controls
                  inputProps={inputProps} />
              ) : (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-12">
                  <div className="w-16 h-16 bg-white/5 rounded-3xl flex items-center justify-center mb-8 border border-white/10 animate-pulse">
                    <Youtube className="w-8 h-8 text-neutral-700" />
                  </div>
                  <h3 className="text-xl font-black uppercase tracking-tighter mb-4 text-white/50">Ready for Input</h3>
                  <div className="w-full max-w-sm space-y-4">
                    <input type="text" placeholder="Paste Video Link..." className="w-full bg-black/60 border border-white/10 rounded-2xl px-6 py-4 text-xs font-mono focus:ring-2 focus:ring-purple-500/50 outline-none transition-all placeholder:text-neutral-700" value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && (status.status === 'idle' || status.status === 'failed') && handleProcess()} disabled={status.status !== 'idle' && status.status !== 'failed'} />
                    <button onClick={handleProcess} disabled={(status.status !== 'idle' && status.status !== 'failed') || !url.trim()} className="w-full bg-purple-600 text-white py-4 rounded-3xl font-black uppercase text-[10px] tracking-widest hover:bg-purple-500 transition-all shadow-2xl disabled:opacity-50 disabled:cursor-not-allowed transition-opacity duration-300">
                      {status.status === 'idle' || status.status === 'failed' ? 'Load Engine' : 'Processing...'}
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* View Mode Switcher */}
            {transcript && (
              <div className="absolute top-12 left-12 flex bg-black/80 backdrop-blur-3xl rounded-full border border-white/10 p-1 shadow-2xl">
                <button onClick={() => setShowGuides(true)} className={`px-6 py-2 rounded-full text-[10px] font-black uppercase tracking-widest transition-all ${showGuides ? 'bg-purple-600 shadow-lg text-white' : 'text-neutral-600 hover:text-white'}`}>
                  Panorama 16:9
                </button>
                <button onClick={() => setShowGuides(false)} className={`px-6 py-2 rounded-full text-[10px] font-black uppercase tracking-widest transition-all ${!showGuides ? 'bg-purple-600 shadow-lg text-white' : 'text-neutral-600 hover:text-white'}`}>
                  Preview 9:16
                </button>
              </div>
            )}

            {transcript && (
              <div className="absolute top-12 right-12 flex flex-col gap-4">
                <button onClick={() => setShowTranscriptEditor(prev => !prev)} className={`p-4 rounded-3xl border transition-all ${showTranscriptEditor ? 'bg-indigo-600 border-indigo-400 shadow-xl' : 'bg-black/60 border-white/10 text-neutral-500 hover:text-white'}`}>
                  <Type className="w-6 h-6" />
                </button>
              </div>
            )}
          </div>

          {/* New Multi-Track Timeline */}
          {transcript && (
            <div className="h-64 bg-black/80 backdrop-blur-3xl border-t border-white/10 p-6 flex flex-col gap-4">
              <div className="flex items-center gap-8">
                <div className="text-4xl font-mono font-black text-white/90 tabular-nums w-48">{Math.floor(currentTime / 60)}:{(currentTime % 60).toFixed(2).padStart(5, '0')}</div>
                <button onClick={addCut} className="bg-gradient-to-r from-purple-600 to-indigo-600 text-white px-8 py-3 rounded-2xl font-black uppercase text-[11px] tracking-widest active:scale-95 shadow-2xl hover:brightness-125 transition-all flex items-center gap-3">
                  <Scissors className="w-5 h-5" /> Cut
                </button>
              </div>

              {/* TRACKS CONTAINER */}
              <div className="relative flex-1 flex flex-col gap-1 cursor-crosshair group" onClick={handleTimelineClick}>
                {/* Global Playhead */}
                <div className="absolute top-0 bottom-0 w-[2px] bg-red-600 z-[100] pointer-events-none shadow-[0_0_15px_rgba(220,38,38,1)] transition-none" style={{ left: `${(currentTime / getDuration()) * 100}%` }}>
                  <div className="w-3 h-3 bg-red-600 rotate-45 absolute -top-1.5 -left-[5px] border border-red-300" />
                </div>

                {/* TRACK 1: VFX & Emojis */}
                <div className="h-8 bg-white/5 rounded-lg border border-white/5 relative hover:bg-white/10 transition-all flex items-center overflow-hidden">
                  <div className="absolute left-0 top-0 bottom-0 w-16 bg-black/80 border-r border-white/10 flex items-center justify-center text-[8px] font-black uppercase text-yellow-500 tracking-widest z-50">VFX</div>
                  {transcript?.edit_events?.zooms?.map((z: any, idx: number) => (
                    <div key={`z-${idx}`} className="absolute top-1 bottom-1 w-1 rounded bg-blue-500/80 shadow-[0_0_10px_rgba(59,130,246,0.6)]" style={{ left: `${(z.time / getDuration()) * 100}%` }} />
                  ))}
                  {transcript?.edit_events?.icons?.map((icon: any, idx: number) => (
                    <div key={`i-${idx}`} className="absolute top-1 bottom-1 rounded bg-yellow-400/80 text-[8px] font-black px-1.5 flex items-center shadow-[0_0_10px_rgba(250,204,21,0.6)] whitespace-nowrap overflow-hidden text-black uppercase" style={{ left: `${(icon.time / getDuration()) * 100}%` }}>{icon.keyword}</div>
                  ))}
                </div>

                {/* TRACK 2: Camera Cuts (Segments) */}
                <div className="h-14 bg-black/50 rounded-xl border border-white/5 relative hover:bg-[#0a0a0a] transition-all">
                  <div className="absolute left-0 top-0 bottom-0 w-16 bg-black/80 border-r border-white/10 flex items-center justify-center text-[8px] font-black uppercase text-purple-400 tracking-widest z-50">Cams</div>
                  <div className="absolute inset-0 left-16">
                    {transcript?.framing_segments?.map((seg: any, idx: number) => (
                      <div key={`c-${idx}`} onClick={(e) => { e.stopPropagation(); setActiveSegmentIdx(idx); playerRef.current?.seekTo(Math.round(seg.start * 30)); }}
                        className={`absolute top-1 bottom-1 border-r border-black/40 rounded-[0.4rem] flex flex-col items-center justify-center cursor-pointer transition-all hover:brightness-150 ${activeSegmentIdx === idx ? 'bg-purple-600/40 border border-purple-500 shadow-[inset_0_0_20px_rgba(168,85,247,0.3)] z-10' : 'bg-white/5'}`}
                        style={{ left: `${(seg.start / getDuration()) * 100}%`, width: `${((seg.end - seg.start) / getDuration()) * 100}%` }}>
                        <span className="text-[9px] font-black text-white/50 mb-0.5">SHOT_{idx + 1}</span>
                        <div className="w-1/2 h-[3px] bg-black rounded-full overflow-hidden"><div className="bg-purple-400 h-full w-[4px] rounded-full" style={{ marginLeft: `${seg.center * 100}%`, transform: 'translateX(-50%)' }} /></div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* TRACK 3: Audio/Subtitles Visualizer (Fake wave) */}
                <div className="h-6 bg-white/5 rounded-lg border border-white/5 relative hover:bg-white/10 transition-all overflow-hidden flex items-end">
                  <div className="absolute left-0 top-0 bottom-0 w-16 bg-black/80 border-r border-white/10 flex items-center justify-center text-[8px] font-black uppercase text-indigo-400 tracking-widest z-50">Subs</div>
                  <div className="absolute inset-0 left-16">
                    {transcript?.words?.map((w: any, idx: number) => (
                      <div key={`w-${idx}`} className={`absolute bottom-0 w-[2px] rounded-t-sm transition-all ${currentTime >= w.start && currentTime <= w.end ? 'bg-indigo-400 h-full' : 'bg-white/20'}`} style={{ left: `${(w.start / getDuration()) * 100}%`, height: `${20 + (Math.sin(idx * 5) * 50)}%` }} />
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Pro Inspector */}
        <div className="w-[450px] bg-[#0c0c0c] flex flex-col border-l border-white/5 shadow-2xl overflow-hidden relative z-20">
          {showTranscriptEditor ? (
            <div className="flex-1 flex flex-col bg-black/40">
              <div className="p-10 border-b border-white/5 bg-black/20">
                <h2 className="text-2xl font-black uppercase tracking-tighter italic text-indigo-400 mb-2">Word Lab</h2>
                <p className="text-[10px] text-neutral-600 font-bold uppercase tracking-widest">Edit phrases or delete hallucinations</p>
              </div>
              <div className="flex-1 overflow-y-auto p-8 space-y-3 custom-scrollbar">
                {transcript?.words?.map((w: any, idx: number) => (
                  <div key={idx} className={`group flex items-center gap-4 p-4 rounded-2xl border transition-all ${currentTime >= w.start && currentTime <= w.end ? 'bg-indigo-600/20 border-indigo-500 shadow-xl scale-[1.02]' : 'bg-black/40 border-white/5 opacity-40 hover:opacity-100'}`}>
                    <div className="w-10 text-[9px] font-mono text-neutral-600">{w.start.toFixed(1)}s</div>
                    <input className="flex-1 bg-transparent border-none text-xs font-black text-white focus:outline-none" value={w.word}
                      onChange={(e) => { const nw = [...transcript.words]; nw[idx].word = e.target.value; setTranscript({ ...transcript, words: nw }); }}
                      onBlur={() => saveToBackend(transcript)} />
                    <button onClick={() => deleteWord(idx)} className="opacity-0 group-hover:opacity-100 p-2 hover:bg-red-500/20 rounded-lg text-red-500 transition-all"><Eraser className="w-4 h-4" /></button>
                  </div>
                ))}
              </div>
              <div className="p-8 bg-indigo-900/10 border-t border-indigo-500/20 text-center"><button onClick={() => setShowTranscriptEditor(false)} className="text-[10px] font-black uppercase text-indigo-400 tracking-widest hover:text-white">Close Editor</button></div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col p-12 overflow-y-auto">
              <div className="flex items-center justify-between mb-12">
                <h2 className="text-3xl font-black uppercase tracking-tighter italic">Clip Config</h2>
                <Settings className="w-6 h-6 text-neutral-700" />
              </div>

              {transcript ? (
                <div className="space-y-16">
                  {/* Active Shot Box */}
                  <div className="space-y-4">
                    <label className="text-[10px] font-black uppercase tracking-[0.4em] text-neutral-600">Active Shot Definition</label>
                    <div className="bg-black/40 p-6 rounded-[2rem] border border-white/5 flex flex-col gap-6">
                      <div className="flex items-center justify-between">
                        <div><div className="text-4xl font-black text-white">{activeSegmentIdx + 1} <span className="text-xl text-neutral-800">/ {transcript.framing_segments.length}</span></div></div>
                        <button onClick={() => deleteSegment(activeSegmentIdx)} className="p-4 bg-red-600/5 hover:bg-red-600 border border-red-500/10 rounded-2xl text-red-500 hover:text-white transition-all"><Trash2 className="w-6 h-6" /></button>
                      </div>

                      <div className="pt-6 border-t border-white/5">
                        <div className="flex items-center justify-between mb-4"><span className="text-[10px] font-bold uppercase text-purple-400 tracking-widest">Horizontal Center</span><span className="text-xl font-mono font-black text-white">{(transcript.framing_segments[activeSegmentIdx].center * 100).toFixed(0)}%</span></div>
                        <input type="range" min="0" max="1" step="0.005" value={transcript.framing_segments[activeSegmentIdx].center} onChange={(e) => updateSegmentCenter(activeSegmentIdx, parseFloat(e.target.value))}
                          className="w-full h-3 bg-black border border-white/10 rounded-full appearance-none accent-purple-500 cursor-pointer shadow-lg hover:ring-8 ring-purple-600/10 transition-all" />
                      </div>
                    </div>
                  </div>

                  {/* Effects Manager */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <label className="text-[10px] font-black uppercase tracking-[0.4em] text-neutral-600">Action Events in Shot</label>
                      <button onClick={removeVFXFromCurrentSegment} className="text-[8px] uppercase font-black text-red-400 hover:text-red-300">Clear VFX</button>
                    </div>
                    <div className="bg-black/20 rounded-[1.5rem] border border-white/5 p-4 space-y-2">
                      {transcript.edit_events?.icons?.filter((i: any) => i.time >= transcript.framing_segments[activeSegmentIdx].start && i.time <= transcript.framing_segments[activeSegmentIdx].end).map((icon: any, idx: number) => (
                        <div key={idx} className="flex justify-between items-center bg-white/5 px-4 py-3 rounded-xl"><span className="text-xs font-bold text-yellow-500 uppercase">Icon: {icon.keyword}</span><span className="text-[10px] font-mono text-neutral-600">{icon.time.toFixed(1)}s</span></div>
                      ))}
                      {transcript.edit_events?.zooms?.filter((z: any) => z.time >= transcript.framing_segments[activeSegmentIdx].start && z.time <= transcript.framing_segments[activeSegmentIdx].end).map((z: any, idx: number) => (
                        <div key={idx} className="flex justify-between items-center bg-white/5 px-4 py-3 rounded-xl"><span className="text-xs font-bold text-blue-400 uppercase">Camera {z.type}</span><span className="text-[10px] font-mono text-neutral-600">{z.time.toFixed(1)}s</span></div>
                      ))}
                      {transcript.edit_events?.zooms?.filter((z: any) => z.time >= transcript.framing_segments[activeSegmentIdx].start && z.time <= transcript.framing_segments[activeSegmentIdx].end).length === 0 && transcript.edit_events?.icons?.filter((i: any) => i.time >= transcript.framing_segments[activeSegmentIdx].start && i.time <= transcript.framing_segments[activeSegmentIdx].end).length === 0 && (
                        <div className="text-center p-4 text-[10px] font-bold text-neutral-600 uppercase">No VFX in this shot</div>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex-1 flex items-center justify-center opacity-20"><Cpu className="w-16 h-16 animate-spin" /></div>
              )}

              <div className="mt-auto pt-16 space-y-8">
                {status.status === 'failed' ? (
                  <div className="p-6 bg-red-500/10 border border-red-500/20 rounded-[2.5rem] flex flex-col items-center justify-center text-center">
                    <div className="text-[9px] font-black uppercase text-red-500 mb-2 tracking-[0.2em]">Pipeline Failed</div>
                    <div className="text-xs font-bold text-red-400 break-words">{status.error || 'Unknown Error'}</div>
                  </div>
                ) : status.status !== 'idle' ? (
                  <>
                    <div className="p-6 bg-white/5 border border-white/5 rounded-[2.5rem] flex items-center justify-between">
                      <div><div className="text-[9px] font-black uppercase text-neutral-600 mb-1">Engine Load</div><div className="text-xl font-black text-white/80">{status.progress}%</div></div>
                      <div className="w-32 h-1.5 bg-black rounded-full overflow-hidden"><div className="h-full bg-purple-600 transition-all duration-700" style={{ width: `${status.progress}%` }} /></div>
                    </div>
                    <p className="text-[10px] text-neutral-500 font-bold leading-relaxed px-4 break-words">{status.message}</p>
                  </>
                ) : null}
              </div>
            </div>
          )}
        </div>
      </div>
      <style jsx global>{`
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
        input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; height: 36px; width: 16px; border-radius: 6px; background: #A855F7; border: 3px solid #fff; cursor: pointer; box-shadow: 0 0 20px rgba(168,85,247,0.5); }
      `}</style>
    </main>
  );
}
