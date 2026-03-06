import React, { useMemo } from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { loadFont } from '@remotion/google-fonts/Inter';

const { fontFamily } = loadFont();

interface Word {
    word: string;
    start: number;
    end: number;
}

interface SubtitlesProps {
    transcript: {
        words: Word[];
        words_es?: Word[];
    };
    currentLayout?: 'single' | 'split';
    preferredLanguage?: 'en' | 'es';
}

export const Subtitles: React.FC<SubtitlesProps> = ({
    transcript,
    currentLayout = 'single',
    preferredLanguage = 'en'
}) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();
    const currentTime = frame / fps;

    const words = (preferredLanguage === 'es' && transcript?.words_es)
        ? transcript.words_es
        : (transcript?.words || []);


    // --- CHUNKING LOGIC ---
    // Group words into chunks of up to 4 words.
    const chunks = useMemo(() => {
        const result: any[][] = [];
        let currentChunk: any[] = [];
        for (let i = 0; i < words.length; i++) {
            currentChunk.push(words[i]);
            // Create a new chunk every 4 words, OR if it's the last word
            if (currentChunk.length === 4 || i === words.length - 1) {
                result.push(currentChunk);
                currentChunk = [];
            }
        }
        return result;
    }, [words]);

    // Find the active chunk based on the current time
    const activeChunkIndex = chunks.findIndex((chunk, index) => {
        const firstWordStart = chunk[0].start;
        const nextChunk = chunks[index + 1];

        // Let the current text stay on screen during short pauses.
        // It clears out ONLY if the next chunk starts or if the video ends.
        const endTime = nextChunk ? nextChunk[0].start : chunk[chunk.length - 1].end + 0.5;

        return currentTime >= firstWordStart && currentTime < endTime;
    });

    const activeChunk = activeChunkIndex !== -1 ? chunks[activeChunkIndex] : null;

    if (!activeChunk) return null;

    return (
        <AbsoluteFill style={{
            justifyContent: currentLayout === 'split' ? 'center' : 'flex-end',
            alignItems: 'center',
            paddingBottom: currentLayout === 'split' ? '0px' : '300px', // Higher position for single mode
            pointerEvents: 'none',
        }}>
            {/* Gradient Overlay Behind Text (Only in single mode to avoid cluttering the split center) */}
            {currentLayout === 'single' && (
                <div style={{
                    position: 'absolute',
                    bottom: 0,
                    width: '100%',
                    height: '40%',
                    background: 'linear-gradient(to bottom, transparent, rgba(0,0,0,0.85))',
                    zIndex: -1,
                }} />
            )}

            <div style={{
                display: 'flex',
                flexWrap: 'wrap',
                justifyContent: 'center',
                alignItems: 'center',
                gap: '24px', // Word gap: 24pt ~ 24px
                width: '80%',
                textAlign: 'center',
            }}>
                {activeChunk.map((wordObj, i) => {
                    // --- STYLING LOGIC ---
                    const isPast = currentTime > wordObj.end;
                    const isCurrent = currentTime >= wordObj.start && currentTime <= wordObj.end;

                    let color = 'rgba(255, 255, 255, 0.5)'; // Future default
                    let textShadow = '0 4px 20px rgba(0,0,0,0.8)'; // default text shadow
                    let transform = 'scale(1)';

                    if (isCurrent) {
                        color = '#BFF549'; // Neon green
                        textShadow = '0 0 40px rgba(191,245,73,0.8), 0 4px 20px rgba(0,0,0,0.8)'; // Glow effect
                        transform = 'scale(1.1)'; // Scale 1.1 pop
                    } else if (isPast) {
                        color = '#FFFFFF'; // White for already spoken
                    }

                    return (
                        <span
                            key={i}
                            style={{
                                fontFamily,
                                fontSize: '72px',
                                fontWeight: 800,
                                letterSpacing: '0.02em',
                                color,
                                textShadow,
                                transform,
                                transition: 'all 0.1s ease-out', // Smooth transition between states
                                display: 'inline-block',
                                lineHeight: '1.2',
                            }}
                        >
                            {wordObj.word}
                        </span>
                    );
                })}
            </div>
        </AbsoluteFill>
    );
};
