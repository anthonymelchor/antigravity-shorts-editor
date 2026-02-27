'use client';

import React from 'react';
import { ErrorView } from '@/components/ErrorView';

export default function GlobalError({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    return (
        <html>
            <body>
                <ErrorView />
            </body>
        </html>
    );
}
