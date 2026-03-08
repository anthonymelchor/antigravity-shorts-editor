'use client';

import React from 'react';
import Link from 'next/link';
import { Download, Sparkles } from 'lucide-react';

export const NewFeaturesNav = () => {
    return (
        <React.Fragment>
            <Link href="/new_functionalities/video_downloads" className="hover:text-purple-400 transition-colors flex items-center gap-2">
                <Download className="w-3 h-3 text-purple-400 shadow-[0_0_10px_rgba(168,85,247,0.3)]" />
                Descargas de Videos
            </Link>
        </React.Fragment>
    );
};

export const DiscoveryLink = () => {
    return (
        <Link href="/discovery" className="hover:text-white transition-colors flex items-center gap-2">
            <Sparkles className="w-3 h-3" />
            Discovery Engine
        </Link>
    );
};
