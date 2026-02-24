import { AbsoluteFill, useCurrentFrame, useVideoConfig, spring } from 'remotion';
import { Transcript } from './Composition';

interface SubtitlesProps {
    transcript: Transcript;
}

export const Subtitles: React.FC<SubtitlesProps> = ({ transcript }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();
    const currentTime = frame / fps;

    const currentWord = transcript.words.find(
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
                pointerEvents: 'none',
            }}
        >
            <div
                style={{
                    color: 'white',
                    fontSize: '85px',
                    fontWeight: '900',
                    textTransform: 'uppercase',
                    textAlign: 'center',
                    textShadow: `4px 4px 0px black`,
                    padding: '20px',
                    lineHeight: '1',
                    fontFamily: '"Arial Black", sans-serif',
                    transform: `scale(${scale.toFixed(4)}) translateZ(0)`,
                }}
            >
                {currentWord.word}
            </div>
        </AbsoluteFill>
    );
};
