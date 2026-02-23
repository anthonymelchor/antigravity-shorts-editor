import { AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate } from 'remotion';
import transcriptData from './transcript_data.json';

interface Word {
    word: string;
    start: number;
    end: number;
}

export const Subtitles: React.FC = () => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();
    const currentTime = frame / fps;

    const currentWord = transcriptData.words.find(
        (w: any) => currentTime >= w.start && currentTime <= w.end
    );

    if (!currentWord) return null;

    const startFrame = currentWord.start * fps;
    const scale = spring({
        frame: frame - startFrame,
        fps,
        config: {
            stiffness: 200,
            damping: 10,
            mass: 0.5
        },
    });

    return (
        <AbsoluteFill
            style={{
                justifyContent: 'center',
                alignItems: 'center',
                top: '55%',
                height: '25%',
                pointerEvents: 'none'
            }}
        >
            <div
                style={{
                    color: 'white',
                    fontSize: '85px',
                    fontWeight: '900',
                    textTransform: 'uppercase',
                    textAlign: 'center',
                    textShadow: `4px 4px 0px black, -4px -4px 0px black, 4px -4px 0px black, -4px 4px 0px black, 0px 8px 15px rgba(0,0,0,0.8)`,
                    padding: '20px',
                    lineHeight: '1',
                    fontFamily: '"Arial Black", sans-serif',
                }}
            >
                {currentWord.word}
            </div>
        </AbsoluteFill>
    );
};
