import React from 'react';
import { AbsoluteFill } from 'remotion';

interface WatermarkProps {
    text?: string;
    opacity?: number;
}

export const Watermark: React.FC<WatermarkProps> = ({
    text = 'ROCOTOCLIP',
    opacity = 1
}) => {
    return (
        <AbsoluteFill style={{
            justifyContent: 'flex-end',
            alignItems: 'center',
            paddingBottom: '600px', // Lowered position
            pointerEvents: 'none',
        }}>
            <div style={{
                color: 'rgba(255, 255, 255, 0.3)', // More faded (increased transparency)
                fontSize: '48px',
                fontWeight: 800, // Exact weight of subtitles
                letterSpacing: '1px',
                opacity: opacity,
                fontFamily: '"Segoe UI", system-ui, sans-serif',
                textTransform: 'lowercase',
                textShadow: '0 2px 10px rgba(0,0,0,0.3)', // Even softer shadow
            }}>
                {text}
            </div>
        </AbsoluteFill>
    );
};
