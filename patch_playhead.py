"""
Replace the broken playhead tracking useEffect with a robust rAF loop that reads video.currentTime directly.
"""
import re

with open(r'frontend/src/app/page.tsx', 'rb') as f:
    content = f.read().decode('utf-8')

# Remove the broken useEffect that uses frameupdate event (lines 167-189)
# We'll find it by its unique markers
old_block = '''    useEffect(() => {
        const player = playerRef.current;
        if (!player || view !== 'results') return;

        const onFrameUpdate = (e: any) => {
            const frame = e.frame;
            const duration = transcript?.clips?.[selectedClipIdx]?.duration || 30;
            let pct = ((frame / 30) / duration) * 100;
            if (!isFinite(pct) || isNaN(pct)) pct = 0;

            const line = document.getElementById('rct-playhead-line') as HTMLElement;
            if (line) line.style.left = pct + '%';

            const label = document.getElementById('rct-playhead-label') as HTMLElement;
            if (label) label.textContent = (frame / 30).toFixed(1) + 's';

            const inp = document.getElementById('rct-playhead-input') as HTMLInputElement;
            if (inp && document.activeElement !== inp) inp.value = (frame / 30).toFixed(2);
        };

        player.addEventListener('frameupdate', onFrameUpdate);
        return () => { player.removeEventListener('frameupdate', onFrameUpdate); };
    }, [view, playerRef.current, transcript, selectedClipIdx]);'''

new_block = '''    // Track playhead using the actual <video> element's currentTime via requestAnimationFrame.
    // This is the most reliable approach - bypasses Remotion abstraction issues entirely.
    useEffect(() => {
        if (view !== 'results') return;
        let rafId: number;
        let lastTime = -1;

        const tick = () => {
            // Find the video element inside the Remotion player container
            const videoEl = document.querySelector('[data-remotion-canvas] video') as HTMLVideoElement
                         || document.querySelector('video') as HTMLVideoElement;

            if (videoEl) {
                const currentTime = videoEl.currentTime;
                // Only update DOM if time changed (avoid unnecessary repaints)
                if (Math.abs(currentTime - lastTime) > 0.016) {
                    lastTime = currentTime;
                    const duration = videoEl.duration || 1;
                    const pct = (currentTime / duration) * 100;

                    const lineEl = document.getElementById('rct-playhead-line') as HTMLElement;
                    if (lineEl) lineEl.style.left = pct + '%';

                    const labelEl = document.getElementById('rct-playhead-label') as HTMLElement;
                    if (labelEl) labelEl.textContent = currentTime.toFixed(1) + 's';

                    const inpEl = document.getElementById('rct-playhead-input') as HTMLInputElement;
                    if (inpEl && document.activeElement !== inpEl) {
                        inpEl.value = currentTime.toFixed(2);
                    }
                }
            }
            rafId = requestAnimationFrame(tick);
        };

        rafId = requestAnimationFrame(tick);
        return () => cancelAnimationFrame(rafId);
    }, [view]);'''

# Try with CRLF
old_crlf = old_block.replace('\n', '\r\n')
new_crlf = new_block.replace('\n', '\r\n')

if old_crlf in content:
    print('FOUND (CRLF) — replacing...')
    content = content.replace(old_crlf, new_crlf, 1)
    with open(r'frontend/src/app/page.tsx', 'wb') as f:
        f.write(content.encode('utf-8'))
    print('SUCCESS')
elif old_block in content:
    print('FOUND (LF) — replacing...')
    content = content.replace(old_block, new_block, 1)
    with open(r'frontend/src/app/page.tsx', 'wb') as f:
        f.write(content.encode('utf-8'))
    print('SUCCESS')
else:
    print('NOT FOUND — dumping nearby text:')
    idx = content.find('onFrameUpdate')
    print(repr(content[max(0,idx-200):idx+500]))
