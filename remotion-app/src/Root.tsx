import { Composition, getInputProps } from 'remotion';
import { Main } from './Composition';
import './style.css';
import transcriptData from './transcript_data.json';

export const RemotionRoot: React.FC = () => {
    // Priority: Props passed via command line (--props) > Imported JSON file
    const inputProps = getInputProps() as any;
    const data = inputProps.transcript || transcriptData;

    // Calculate duration based on the dynamic data
    const fps = 30;
    const words = data.words || [];
    const durationInSeconds = data.duration || (words.length > 0 ? words[words.length - 1].end : 30);
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
                    transcript: data,
                    preferredLanguage: inputProps.preferredLanguage || data.preferredLanguage || 'es',
                }}
            />
        </>
    );
};
