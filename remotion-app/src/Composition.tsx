import { AbsoluteFill, OffthreadVideo, staticFile, useVideoConfig, getInputProps } from 'remotion';
import { Subtitles } from './Subtitles';
import { ZoomManager } from './ZoomManager';
import { DynamicLayer } from './DynamicLayer';
import transcriptData from './transcript_data.json';

interface Transcript {
    layout?: 'single' | 'split';
    center?: number;
    center_top?: number;
    center_bottom?: number;
    text: string;
    words: any[];
    edit_events?: {
        zooms: any[];
        icons: any[];
        b_rolls: any[];
        backgrounds: any[];
    };
}

const transcript = transcriptData as unknown as Transcript;

export const Main: React.FC = () => {
    const { width, height } = useVideoConfig();

    const layout = transcript.layout || 'single';
    const center = transcript.center || 0.5;
    const centerTop = transcript.center_top || 0.5;
    const centerBottom = transcript.center_bottom || 0.5;
    const editEvents = transcript.edit_events || { zooms: [], icons: [], b_rolls: [], backgrounds: [] };

    const videoWidth = layout === 'split' ? (height / 2) * (16 / 9) : height * (16 / 9);

    const calculateVideoTranslation = (c: number) => {
        // Pixel-perfect centering: (ScreenCenter - VideoPoint)
        let tx = (width / 2) - (videoWidth * c);

        // Clamp to avoid showing black bars
        const minTx = width - videoWidth;
        const maxTx = 0;

        return Math.round(Math.max(minTx, Math.min(maxTx, tx)));
    };

    const videoSrc = staticFile('output_vertical_clip.mp4');

    return (
        <AbsoluteFill style={{ backgroundColor: 'black' }}>
            <ZoomManager zooms={editEvents.zooms}>
                {layout === 'split' ? (
                    <AbsoluteFill>
                        {/* Top Half */}
                        <div style={{ position: 'absolute', top: 0, width: '100%', height: '50%', overflow: 'hidden' }}>
                            <OffthreadVideo
                                src={videoSrc}
                                muted
                                style={{
                                    position: 'absolute',
                                    height: '100%',
                                    width: 'auto',
                                    left: 0,
                                    transform: `translate3d(${calculateVideoTranslation(centerTop)}px, 0, 0)`,
                                    objectFit: 'cover'
                                }}
                            />
                        </div>
                        {/* Bottom Half */}
                        <div style={{ position: 'absolute', bottom: 0, width: '100%', height: '50%', overflow: 'hidden' }}>
                            <OffthreadVideo
                                src={videoSrc}
                                style={{
                                    position: 'absolute',
                                    height: '100%',
                                    width: 'auto',
                                    left: 0,
                                    transform: `translate3d(${calculateVideoTranslation(centerBottom)}px, 0, 0)`,
                                    objectFit: 'cover'
                                }}
                            />
                        </div>
                    </AbsoluteFill>
                ) : (
                    <OffthreadVideo
                        src={videoSrc}
                        style={{
                            position: 'absolute',
                            height: '100%',
                            width: 'auto',
                            left: 0,
                            transform: `translate3d(${calculateVideoTranslation(center)}px, 0, 0)`,
                            objectFit: 'cover'
                        }}
                    />
                )}
            </ZoomManager>

            {/* Editing Layers */}
            <DynamicLayer events={editEvents} />
            <Subtitles />
        </AbsoluteFill>
    );
};

