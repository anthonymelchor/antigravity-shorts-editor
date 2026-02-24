import React from 'react';
import { interpolate, useCurrentFrame, spring, useVideoConfig } from 'remotion';

export const PopAnimation: React.FC<{ children: React.ReactNode; delay?: number }> = ({ children, delay = 0 }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();

    const scale = spring({
        frame: frame - delay,
        fps,
        config: { damping: 12, stiffness: 200, mass: 0.5 },
    });

    return <div style={{ transform: `scale(${scale})` }}>{children}</div>;
};

export const FloatingAnimation: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const frame = useCurrentFrame();
    const y = Math.sin(frame * 0.1) * 10;
    return <div style={{ transform: `translateY(${y}px)` }}>{children}</div>;
};

export const PulseAnimation: React.FC<{ children: React.ReactNode; color: string }> = ({ children, color }) => {
    const frame = useCurrentFrame();
    const scale = 1 + Math.sin(frame * 0.2) * 0.05;
    const glow = Math.sin(frame * 0.2) * 20 + 20;

    return (
        <div style={{
            transform: `scale(${scale})`,
            filter: `drop-shadow(0 0 ${glow}px ${color})`
        }}>
            {children}
        </div>
    );
};
