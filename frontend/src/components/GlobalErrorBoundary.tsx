'use client';

import React from 'react';
import { ErrorView } from './ErrorView';

const API_BASE = '';

const logErrorToBackend = async (error: any, context?: string) => {
    try {
        await fetch(`${API_BASE}/api/log-error`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: error.message || String(error),
                stack: error.stack,
                context: context || 'Global Boundary Catch',
                url: window.location.href,
                userAgent: navigator.userAgent
            })
        });
    } catch (err) {
        console.error("Critical: Failed to report error to backend", err);
    }
};

export class GlobalErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean }> {
    constructor(props: { children: React.ReactNode }) {
        super(props);
        this.state = { hasError: false };
    }

    static getDerivedStateFromError() {
        return { hasError: true };
    }

    componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
        logErrorToBackend(error, errorInfo.componentStack ?? undefined);
    }

    render() {
        if (this.state.hasError) {
            return <ErrorView />;
        }

        return this.props.children;
    }
}

