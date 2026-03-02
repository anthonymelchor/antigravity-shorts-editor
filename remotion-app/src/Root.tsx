import { Composition } from 'remotion';
import { Main } from './Composition';
import './style.css';
import transcriptData from './transcript_data.json';

export const RemotionRoot: React.FC = () => {
    // Calculate duration based on the last word's end time
    const fps = 30;
    const words = (transcriptData as any).words || [];
    const durationInSeconds = (transcriptData as any).duration || (words.length > 0 ? words[words.length - 1].end : 30);
    const durationInFrames = Math.ceil(durationInSeconds * fps);

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
                    preferredLanguage: (transcriptData as any).preferredLanguage || 'en',
                }}
            />
        </>
    );
};
