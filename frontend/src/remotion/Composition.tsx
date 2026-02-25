import { AbsoluteFill, Video, OffthreadVideo, Audio, staticFile, useVideoConfig, useCurrentFrame, interpolate } from 'remotion';
import { Subtitles } from './Subtitles';
import { ZoomManager } from './ZoomManager';
import { DynamicLayer } from './DynamicLayer';
import transcriptData from './transcript_data.json';

export interface FramingSegment {
    start: number;
    end: number;
    center: number;
    center_top?: number;
    center_bottom?: number;
    layout?: 'single' | 'split';
}

export interface Transcript {
    layout?: 'single' | 'split';
    center?: number;
    center_top?: number;
    center_bottom?: number;
    framing_segments?: FramingSegment[];
    text: string;
    words: any[];
    edit_events?: {
        zooms: any[];
        icons: any[];
        b_rolls: any[];
        backgrounds: any[];
    };
}

interface MainProps {
    transcript?: Transcript;
    videoSrcOverride?: string;
    isPlayer?: boolean;
}

const defaultTranscript: Transcript = transcriptData as unknown as Transcript;

export const Main: React.FC<MainProps> = ({ transcript: propTranscript, videoSrcOverride, isPlayer = false }) => {
    const { fps } = useVideoConfig();
    const frame = useCurrentFrame();
    const currentTime = frame / fps;
    const transcript = propTranscript || defaultTranscript;

    if (!transcript || !transcript.words) {
        return <AbsoluteFill style={{ backgroundColor: '#0c0c0c' }} />;
    }

    const VideoComp = isPlayer ? Video : OffthreadVideo;

    // --- DYNAMIC SEGMENTED FRAMING ENGINE ---
    let activeLayout = transcript.layout || 'single';
    let activeCenter = transcript.center ?? 0.5;
    let activeCenterTop = transcript.center_top ?? 0.5;
    let activeCenterBottom = transcript.center_bottom ?? 0.5;

    if (transcript.framing_segments && transcript.framing_segments.length > 0) {
        const activeSegment = transcript.framing_segments.find(
            s => currentTime >= s.start && currentTime < s.end
        );
        if (activeSegment) {
            activeLayout = activeSegment.layout || 'single';
            activeCenter = activeSegment.center;
            activeCenterTop = activeSegment.center_top ?? 0.5;
            activeCenterBottom = activeSegment.center_bottom ?? 0.5;
        }
    }

    const editEvents = transcript.edit_events || { zooms: [], icons: [], b_rolls: [], backgrounds: [] };

    const finalWidth = 1080;
    const finalHeight = 1920;

    const renderVideo = (c: number, containerHeight: number, opacity: number = 1) => {
        // Safety Zoom (1.2x) gives us more 'room' to move and center people near the edges
        const scale = 1.25;
        const vHeight = containerHeight * scale;
        const vWidth = vHeight * (16 / 9);
        const focus = c ?? 0.5;

        // Centering math
        const targetX = finalWidth / 2;
        const currentFocusX = focus * vWidth;
        let tx = targetX - currentFocusX;

        // Clamp to edges (now with more room thanks to scale)
        const minTx = finalWidth - vWidth;
        const maxTx = 0;
        const finalTx = Math.max(minTx, Math.min(maxTx, tx));

        // Vertical adjustment to center the person vertically in their slot
        const ty = (containerHeight - vHeight) / 2;

        return (
            <div style={{ position: 'absolute', inset: 0, overflow: 'hidden', opacity }}>
                <VideoComp
                    src={videoSrc}
                    muted
                    style={{
                        position: 'absolute',
                        height: `${vHeight}px`,
                        width: `${vWidth}px`,
                        left: 0,
                        top: 0,
                        transform: `translate3d(${finalTx}px, ${ty}px, 0)`,
                        maxWidth: 'none',
                        objectFit: 'cover',
                    }}
                />
            </div>
        );
    };

    const videoSrc = videoSrcOverride || staticFile('output_vertical_clip.mp4');
    const audioSrc = staticFile('output_vertical_clip.wav');

    // Centering logic: ALWAYS 0.5 for Single mode as requested.
    // DYNAMIC focus for Split mode to center the subjects.
    const finalActiveCenter = activeLayout === 'single' ? 0.5 : activeCenter;

    return (
        <AbsoluteFill style={{ backgroundColor: '#000', display: 'block' }}>
            <Audio src={audioSrc} />
            <ZoomManager zooms={editEvents?.zooms || []}>
                <div style={{ position: 'absolute', inset: 0 }}>
                    {activeLayout === 'split' ? (
                        <div style={{ position: 'absolute', inset: 0 }}>
                            {/* TOP SLOT (Person A) */}
                            <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '50%', overflow: 'hidden' }}>
                                {renderVideo(activeCenterTop, finalHeight / 2)}
                            </div>
                            {/* BOTTOM SLOT (Person B) */}
                            <div style={{ position: 'absolute', bottom: 0, left: 0, width: '100%', height: '50%', overflow: 'hidden', borderTop: '4px solid rgba(255,255,255,0.4)' }}>
                                {renderVideo(activeCenterBottom, finalHeight / 2)}
                            </div>
                        </div>
                    ) : (
                        /* FULL SCREEN (Person Focus Fixed at 50%) */
                        renderVideo(finalActiveCenter, finalHeight)
                    )}
                </div>
            </ZoomManager>
            <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
                <DynamicLayer events={editEvents} />
                <Subtitles transcript={transcript} />
            </div>
        </AbsoluteFill>
    );
};
