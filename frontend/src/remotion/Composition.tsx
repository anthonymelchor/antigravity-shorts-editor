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
    video_url?: string;
    audio_url?: string;
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

    // --- FINAL RENDER MATH (9:16) ---
    const finalWidth = 1080;
    const finalHeight = 1920;

    // Zoom factor: 1.0 is standard to avoid "over-zooming" in close-ups
    const zoomFactor = 1.0;

    // Calculate dimensions based on layout
    const containerHeight = activeLayout === 'split' ? finalHeight / 2 : finalHeight;
    const renderedVideoHeight = containerHeight * zoomFactor;
    const renderedVideoWidth = renderedVideoHeight * (16 / 9);

    const calculateVideoTranslation = (c: number) => {
        // --- ABSOLUTE PIXEL-PERFECT CENTERING ---
        // 1. Where is the subject in the video space?
        const subjectX = c * renderedVideoWidth;

        // 2. We want subjectX to be exactly at 540px
        const screenCenterX = finalWidth / 2;
        let offset = screenCenterX - subjectX;

        // 3. Safety: Video must cover the 1080 width
        const minOffset = finalWidth - renderedVideoWidth;
        const maxOffset = 0;

        return Math.max(minOffset, Math.min(maxOffset, offset));
    };

    // Vertical offset - keep it at 0 to respect the original camera framing
    const verticalOffset = 0;

    const videoUrl = transcript.video_url?.startsWith('http')
        ? transcript.video_url
        : (transcript.video_url ? staticFile(transcript.video_url) : staticFile('output_vertical_clip.mp4'));
    const videoSrc = videoSrcOverride || videoUrl;

    const audioSrc = transcript.audio_url?.startsWith('http')
        ? transcript.audio_url
        : (transcript.audio_url ? staticFile(transcript.audio_url) : staticFile('output_vertical_clip.wav'));

    const renderVideoLayer = (c: number, yOffset: number) => {
        const leftValue = calculateVideoTranslation(c);
        return (
            <VideoComp
                src={videoSrc}
                muted
                style={{
                    position: 'absolute',
                    height: `${renderedVideoHeight}px`,
                    width: `${renderedVideoWidth}px`,
                    left: `${leftValue}px`,
                    top: `${yOffset}px`,
                    objectFit: 'cover', // ABSOLUTE REQUIREMENT FOR BROWSER PREVIEW MATCH
                    maxWidth: 'none', // Critical to override Tailwind/Next.js default max-width: 100%
                }}
            />
        );
    };

    return (
        <AbsoluteFill style={{ backgroundColor: '#000' }}>
            <Audio src={audioSrc} />
            <ZoomManager zooms={editEvents?.zooms || []}>
                {activeLayout === 'split' ? (
                    <AbsoluteFill>
                        {/* TOP SECTION */}
                        <div style={{ position: 'absolute', top: 0, width: '100%', height: '50%', overflow: 'hidden' }}>
                            {renderVideoLayer(activeCenterTop, verticalOffset)}
                        </div>
                        {/* BOTTOM SECTION */}
                        <div style={{ position: 'absolute', bottom: 0, width: '100%', height: '50%', overflow: 'hidden', borderTop: '4px solid rgba(255,255,255,0.2)' }}>
                            {renderVideoLayer(activeCenterBottom, verticalOffset)}
                        </div>
                    </AbsoluteFill>
                ) : (
                    <AbsoluteFill style={{ overflow: 'hidden' }}>
                        {renderVideoLayer(activeCenter, verticalOffset)}
                    </AbsoluteFill>
                )}
            </ZoomManager>
            <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
                <DynamicLayer events={editEvents} />
                <Subtitles transcript={transcript} currentLayout={activeLayout} />
            </div>
        </AbsoluteFill>
    );
};
