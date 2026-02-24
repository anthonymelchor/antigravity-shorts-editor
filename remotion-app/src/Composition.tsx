import { AbsoluteFill, Video, OffthreadVideo, Audio, staticFile, useVideoConfig, useCurrentFrame } from 'remotion';
import { Subtitles } from './Subtitles';
import { ZoomManager } from './ZoomManager';
import { DynamicLayer } from './DynamicLayer';
import transcriptData from './transcript_data.json';

export interface FramingSegment {
    start: number;
    end: number;
    center: number;
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
    isWorkspaceView?: boolean;
    isPlayer?: boolean;
}

const defaultTranscript: Transcript = transcriptData as unknown as Transcript;

export const Main: React.FC<MainProps> = ({ transcript: propTranscript, videoSrcOverride, isWorkspaceView = false, isPlayer = false }) => {
    const { fps } = useVideoConfig();
    const frame = useCurrentFrame();
    const currentTime = frame / fps;
    const transcript = propTranscript || defaultTranscript;

    if (!transcript || !transcript.words) {
        return <AbsoluteFill style={{ backgroundColor: '#0c0c0c' }} />;
    }

    const VideoComp = isPlayer ? Video : OffthreadVideo;

    const layout = transcript.layout || 'single';
    const editEvents = transcript.edit_events || { zooms: [], icons: [], b_rolls: [], backgrounds: [] };

    // Segmented Framing Logic
    let center = transcript.center ?? 0.5;
    if (transcript.framing_segments && transcript.framing_segments.length > 0) {
        const activeSegment = transcript.framing_segments.find(
            s => currentTime >= s.start && currentTime < s.end
        );
        if (activeSegment) {
            center = activeSegment.center;
        }
    }

    const centerTop = transcript.center_top ?? 0.5;
    const centerBottom = transcript.center_bottom ?? 0.5;

    // MATH FOR FINAL 9:16 CROP
    const finalWidth = 1080;
    const finalHeight = 1920;
    const currentVideoHeight = layout === 'split' ? finalHeight / 2 : finalHeight;
    const videoWidth = currentVideoHeight * (16 / 9);

    const calculateVideoTranslation = (c: number) => {
        const minTx = finalWidth - videoWidth;
        return c * minTx;
    };

    const videoSrc = videoSrcOverride || staticFile('output_vertical_clip.mp4');
    const audioSrc = staticFile('output_vertical_clip.wav');

    const renderFinalComposition = () => (
        <AbsoluteFill style={{ backgroundColor: '#000' }}>
            <Audio src={audioSrc} />
            <ZoomManager zooms={editEvents?.zooms || []}>
                {layout === 'split' ? (
                    <AbsoluteFill>
                        <div style={{ position: 'absolute', top: 0, width: '100%', height: '50%', overflow: 'hidden' }}>
                            <VideoComp src={videoSrc} muted style={{ position: 'absolute', height: '100%', width: `${videoWidth}px`, left: 0, transform: `translate3d(${calculateVideoTranslation(centerTop)}px, 0, 0)`, objectFit: 'cover' }} />
                        </div>
                        <div style={{ position: 'absolute', bottom: 0, width: '100%', height: '50%', overflow: 'hidden', borderTop: '4px solid rgba(255,255,255,0.2)' }}>
                            <VideoComp src={videoSrc} muted style={{ position: 'absolute', height: '100%', width: `${videoWidth}px`, left: 0, transform: `translate3d(${calculateVideoTranslation(centerBottom)}px, 0, 0)`, objectFit: 'cover' }} />
                        </div>
                    </AbsoluteFill>
                ) : (
                    <VideoComp src={videoSrc} muted style={{ position: 'absolute', height: '100%', width: `${videoWidth}px`, left: 0, transform: `translate3d(${calculateVideoTranslation(center)}px, 0, 0)`, objectFit: 'cover' }} />
                )}
            </ZoomManager>
            <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
                <DynamicLayer events={editEvents} />
                <Subtitles transcript={transcript} />
            </div>
        </AbsoluteFill>
    );

    // If rendering the final video via command line, output the normal 9:16 crop
    if (!isWorkspaceView) {
        return renderFinalComposition();
    }

    // --- WORKSPACE PANORAMA VIEW (1920x1080) ---
    const BOX_WIDTH = 1080 * (9 / 16); // 607.5
    const MAX_X = 1920 - BOX_WIDTH;
    const currentX = center * MAX_X;
    const scaleFactor = 1080 / 1920;

    return (
        <AbsoluteFill style={{ backgroundColor: '#050505', overflow: 'hidden' }}>
            <Audio src={audioSrc} />

            {/* The Full 16:9 Panorama Video (Dimmed, Background) */}
            <AbsoluteFill style={{ filter: 'grayscale(0.5) brightness(0.2)' }}>
                <ZoomManager zooms={editEvents?.zooms || []}>
                    <VideoComp src={videoSrc} muted style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                </ZoomManager>
            </AbsoluteFill>

            {/* The Full 16:9 Panorama Video (Bright, Foreground), perfectly aligned and clipped to the camera box precisely! */}
            <AbsoluteFill style={{
                clipPath: `inset(0px ${1920 - (currentX + BOX_WIDTH)}px 0px ${currentX}px)`
            }}>
                <ZoomManager zooms={editEvents?.zooms || []}>
                    <VideoComp src={videoSrc} muted style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                </ZoomManager>
                {/* Notice we render the Subtitles and VFX right over the bright section! */}
                {/* Scale down the 1080x1920 UI to fit inside the 607.5x1080 Box */}
                <div style={{
                    position: 'absolute',
                    top: 0,
                    left: currentX,
                    width: finalWidth,
                    height: finalHeight,
                    transform: `scale(${scaleFactor})`,
                    transformOrigin: 'top left',
                    pointerEvents: 'none'
                }}>
                    <DynamicLayer events={editEvents} />
                    <Subtitles transcript={transcript} />
                </div>
            </AbsoluteFill>

            {/* The 9:16 Camera Box Viewer (Border) */}
            <div style={{
                position: 'absolute',
                top: 0,
                left: currentX,
                width: BOX_WIDTH,
                height: 1080,
                border: '6px solid #A855F7',
                boxShadow: '0 0 60px rgba(168,85,247,0.4), inset 0 0 20px rgba(0,0,0,0.8)',
                pointerEvents: 'none',
                borderRadius: '8px',
            }} />

            {/* Canvas HUD */}
            <div style={{ position: 'absolute', top: 40, left: 40, color: 'rgba(255,255,255,0.4)', fontFamily: 'sans-serif', fontSize: 18, fontWeight: '900', letterSpacing: '4px' }}>
                16:9 RAW PANORAMA
            </div>
            <div style={{
                position: 'absolute',
                top: 40,
                left: currentX + BOX_WIDTH + 40,
                color: '#A855F7',
                fontFamily: 'sans-serif',
                fontSize: 18,
                fontWeight: '900',
                letterSpacing: '4px',
            }}>
                9:16 CAMERA
            </div>
        </AbsoluteFill>
    );
};
