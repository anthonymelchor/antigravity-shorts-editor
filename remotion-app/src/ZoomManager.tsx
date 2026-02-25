import React from 'react';
import { interpolate, useCurrentFrame, useVideoConfig, spring, AbsoluteFill } from 'remotion';

interface ZoomEvent {
    time: number;
    type: 'in' | 'out' | 'shake' | 'ken-burns';
    intensity?: number; // 0-1
}

interface ZoomManagerProps {
    children: React.ReactNode;
    zooms: ZoomEvent[];
}

export const ZoomManager: React.FC<ZoomManagerProps> = ({ children, zooms }) => {
    const frame = useCurrentFrame();
    const { fps, durationInFrames } = useVideoConfig();

    // Default base transform
    let transform = 'scale(1)';

    // Find the current active event
    const relevantEvents = [...zooms]
        .sort((a, b) => a.time - b.time)
        .filter((z) => (z.time * fps) <= frame);

    if (relevantEvents.length > 0) {
        const lastEvent = relevantEvents[relevantEvents.length - 1];
        const eventStartFrame = lastEvent.time * fps;
        const localFrame = frame - eventStartFrame;
        const intensity = lastEvent.intensity || 0.3;

        if (lastEvent.type === 'in' || lastEvent.type === 'out') {
            const targetScale = lastEvent.type === 'in' ? 1.08 : 1.0;
            const fromScale = lastEvent.type === 'in' ? 1.0 : 1.08;

            const scale = spring({
                frame: localFrame,
                fps,
                config: { damping: 20, stiffness: 100 },
                from: fromScale,
                to: targetScale,
            });
            transform = `scale(${scale}) translate3d(0,0,0)`;
        }
        else if (lastEvent.type === 'ken-burns') {
            // Smooth, noticeable cinematic zoom
            // Combines an immediate scale jump with a slow drift
            const baseScale = 1.02 + (intensity * 0.02); // e.g., 1.03
            const slowDrift = interpolate(localFrame, [0, fps * 10], [1, 1.02], { extrapolateRight: 'clamp' });

            transform = `scale(${baseScale * slowDrift})`;
        }
    }

    return (
        <AbsoluteFill style={{
            transform,
            transformOrigin: '50% 50%',
            overflow: 'hidden',
            backfaceVisibility: 'hidden', // Forces hardware acceleration
            WebkitBackfaceVisibility: 'hidden',
        }}>
            {children}
        </AbsoluteFill>
    );
};
