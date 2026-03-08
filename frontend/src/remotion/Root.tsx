import { Composition } from 'remotion';
import { Main } from './Composition';
import './style.css';
import transcriptDataJson from './transcript_data.json';

export const RemotionRoot: React.FC = () => {
    // Cast to any to prevent Next.js build from failing on placeholder files
    const transcriptData: any = transcriptDataJson;

    // Calculate duration based on the last word's end time
    const fps = 30;
    const words = transcriptData.words || [];
    const lastWordEnd = words.length > 0 ? words[words.length - 1].end : 60;
    const durationInFrames = Math.ceil(lastWordEnd * fps) + fps; // Add 1s buffer

    return (
        <>
            <Composition
                id="ShortVideo"
                component={Main}
                durationInFrames={durationInFrames}
                fps={fps}
                width={1080}
                height={1920}
                defaultProps={{
                    horizontalOffset: 0,
                }}
            />
        </>
    );
};
