'use client';

import React, { useEffect } from 'react';
import { ErrorView } from '@/components/ErrorView';

export default function Error({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    useEffect(() => {
        // Log the error to an error reporting service
        console.error('App Error:', error);
    }, [error]);

    return (
        <div className="min-h-screen bg-[#080f11]">
            <ErrorView />
        </div>
    );
}
