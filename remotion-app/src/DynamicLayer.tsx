import React, { useMemo } from 'react';
import { AbsoluteFill, OffthreadVideo, useCurrentFrame, useVideoConfig, interpolate, spring } from 'remotion';
import { PopAnimation, FloatingAnimation } from './EffectsLibrary';

interface EditEvents {
    icons: any[];
    b_rolls: any[];
    backgrounds?: any[];
}

export const DynamicLayer: React.FC<{ events: EditEvents }> = ({ events }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();

    return (
        <AbsoluteFill>
            {/* 1. Background Manager (Removed to stop visual distortion over video) */}

            {/* 2. B-rolls (Higher priority than background) */}
            {events.b_rolls.map((br, i) => {
                const startFrame = br.time * fps;
                const endFrame = startFrame + (br.duration * fps);
                if (frame >= startFrame && frame < endFrame && br.url) {
                    return (
                        <AbsoluteFill key={`broll-${i}`} style={{ zIndex: 5 }}>
                            <OffthreadVideo
                                src={br.url}
                                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            />
                        </AbsoluteFill>
                    );
                }
                return null;
            })}

            {/* 3. Icon Grid / Overlays */}
            {events.icons.map((icon, i) => {
                const startFrame = icon.time * fps;
                const duration = icon.duration || 1.5;
                const active = frame >= startFrame && frame < startFrame + (fps * duration);

                if (active) {
                    const layout = icon.layout || 'center';
                    const localFrame = frame - startFrame;

                    // Multi-icon layout (Grid)
                    if (layout === 'grid' || layout === 'scattered') {
                        return (
                            <AbsoluteFill key={`icon-grid-${i}`} style={{ zIndex: 20 }}>
                                <IconGrid
                                    emoji={getIconEmoji(icon.keyword)}
                                    layout={layout}
                                    localFrame={localFrame}
                                    fps={fps}
                                />
                            </AbsoluteFill>
                        );
                    }

                    // Single icon (Center/Corner)
                    return (
                        <div key={`icon-${i}`} style={{
                            position: 'absolute',
                            top: layout === 'top' ? '20%' : '50%',
                            left: '50%',
                            transform: 'translate(-50%, -50%)',
                            zIndex: 25,
                        }}>
                            <PopAnimation delay={0}>
                                <FloatingAnimation>
                                    <span style={{ fontSize: '180px', textShadow: '0 20px 50px rgba(0,0,0,0.6)' }}>
                                        {getIconEmoji(icon.keyword)}
                                    </span>
                                </FloatingAnimation>
                            </PopAnimation>
                        </div>
                    );
                }
                return null;
            })}
        </AbsoluteFill>
    );
};

const IconGrid: React.FC<{ emoji: string; layout: string; localFrame: number; fps: number }> = ({ emoji, layout, localFrame, fps }) => {
    const items = useMemo(() => {
        const count = layout === 'grid' ? 9 : 6;
        return Array.from({ length: count }).map((_, i) => ({
            id: i,
            x: layout === 'grid' ? (15 + (i % 3) * 35) : (10 + Math.random() * 80),
            y: layout === 'grid' ? (20 + Math.floor(i / 3) * 30) : (10 + Math.random() * 80),
            delay: i * 3,
            scale: 0.5 + Math.random() * 0.5
        }));
    }, [layout]);

    return (
        <>
            {items.map((it) => (
                <div key={it.id} style={{
                    position: 'absolute',
                    left: `${it.x}%`,
                    top: `${it.y}%`,
                    transform: 'translate(-50%, -50%)',
                }}>
                    <PopAnimation delay={it.delay}>
                        <span style={{ fontSize: `${80 * it.scale}px`, opacity: 0.6 }}>{emoji}</span>
                    </PopAnimation>
                </div>
            ))}
        </>
    );
};

const getIconEmoji = (keyword: string) => {
    const map: Record<string, string> = {
        'money': '💰', 'cash': '💵', 'rich': '🤑',
        'idea': '💡', 'think': '🧠',
        'warning': '⚠️', 'stop': '🚫',
        'time': '⏳', 'fast': '⚡',
        'heart': '❤️', 'love': '🔥',
        'rocket': '🚀', 'growth': '📈',
        'work': '💼', 'success': '🏆'
    };
    return map[keyword.toLowerCase()] || '✨';
};
