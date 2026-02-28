'use client';

import React, { useState } from 'react';
import { createClientComponentClient } from '@supabase/auth-helpers-nextjs';
import { useRouter } from 'next/navigation';
import { Mail, Lock, LogIn, Chrome, AlertCircle } from 'lucide-react';
import { sanitizeAuthError } from '@/lib/utils/auth-error-handler';

export default function LoginPage() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const router = useRouter();
    const supabase = createClientComponentClient();

    const validateEmail = (email: string) => {
        return String(email)
            .toLowerCase()
            .match(
                /^(([^<>()[\]\\.,;:\s@"]+(\.[^<>()[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/
            );
    };

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        // Standard World-Class Validations
        if (!email.trim() || !password.trim()) {
            setError("Por favor, completa todos los campos.");
            return;
        }

        if (!validateEmail(email)) {
            setError("El formato del correo electrónico no es válido.");
            return;
        }

        if (password.length < 6) {
            setError("La contraseña debe tener al menos 6 caracteres.");
            return;
        }

        setLoading(true);

        try {
            const { data: authData, error: authError } = await supabase.auth.signInWithPassword({
                email: email.trim(),
                password: password.trim(),
            });

            if (authError) {
                setError(sanitizeAuthError(authError.message));
                setLoading(false);
                return;
            }

            // check subscription expiration
            const { data: profile, error: profileError } = await supabase
                .from('profiles')
                .select('subscription_expires_at')
                .eq('id', authData.user.id)
                .single();

            if (profileError) {
                // If profile doesn't exist yet, we might want to create it or just allow entry
                // For now, if there's no expiration set, we follow the "no expiration = pass" rule
                console.error("Profile fetch error:", profileError);
            }

            if (profile?.subscription_expires_at) {
                const expirationDate = new Date(profile.subscription_expires_at);
                const now = new Date();

                if (now > expirationDate) {
                    await supabase.auth.signOut();
                    setError("Tu suscripción ha caducado. Por favor, renueva tu cuenta para entrar.");
                    setLoading(false);
                    return;
                }
            }

            // Success
            router.push('/');
            router.refresh();

        } catch (err) {
            setError("Error de conexión. Inténtalo de nuevo.");
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-black text-white font-outfit flex flex-col items-center justify-center p-6 relative overflow-hidden">

            {/* Background Minimalist Branding */}
            <div className="absolute top-12 left-12 opacity-40 select-none">
                <h2 className="text-2xl font-black tracking-tighter uppercase italic text-white pointer-events-none">RocotoClip</h2>
            </div>

            <div className="w-full max-w-md z-10">
                <div className="bg-[#0a0a0a] border border-white/10 rounded-[2.5rem] p-10 shadow-2xl relative overflow-hidden">

                    {/* Security Badge */}
                    <div className="absolute top-0 right-10 bg-white/5 border-x border-b border-white/10 px-4 py-2 rounded-b-xl">
                        <span className="text-[8px] font-black uppercase tracking-widest text-neutral-500 flex items-center gap-2">
                            <div className="w-1 h-1 bg-green-500 rounded-full animate-pulse" />
                            Secure Node
                        </span>
                    </div>

                    <div className="mb-10 text-center">
                        <h1 className="text-4xl font-bold tracking-tight mb-2 text-white">Bienvenido</h1>
                        <p className="text-neutral-500 text-sm font-medium uppercase tracking-widest">Inicia sesión en el motor AI</p>
                    </div>

                    <form onSubmit={handleLogin} className="space-y-6">
                        {error && (
                            <div className="bg-red-500/10 border border-red-500/20 text-red-500 text-xs py-4 px-5 rounded-2xl flex items-center gap-3 animate-in fade-in slide-in-from-top-2 duration-300">
                                <AlertCircle className="w-4 h-4 shrink-0" />
                                <span className="font-bold leading-relaxed">{error}</span>
                            </div>
                        )}

                        <div className="space-y-2">
                            <label className="text-[10px] font-black uppercase tracking-[0.2em] text-neutral-500 px-1">Email</label>
                            <div className="relative group">
                                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-600 group-focus-within:text-white transition-colors" />
                                <input
                                    type="email"
                                    autoComplete="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    className="w-full bg-black border border-white/5 rounded-2xl py-4 pl-12 pr-4 text-sm focus:border-white/20 focus:outline-none transition-all placeholder:text-neutral-800"
                                    placeholder="admin@rocotoclip.ai"
                                    required
                                />
                            </div>
                        </div>

                        <div className="space-y-2">
                            <div className="flex justify-between items-center px-1">
                                <label className="text-[10px] font-black uppercase tracking-[0.2em] text-neutral-500">Contraseña</label>
                                <button type="button" className="text-[10px] text-neutral-600 hover:text-white uppercase font-black transition-colors cursor-pointer">Olvidé mi clave</button>
                            </div>
                            <div className="relative group">
                                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-600 group-focus-within:text-white transition-colors" />
                                <input
                                    type="password"
                                    autoComplete="current-password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="w-full bg-black border border-white/5 rounded-2xl py-4 pl-12 pr-4 text-sm focus:border-white/20 focus:outline-none transition-all placeholder:text-neutral-800"
                                    placeholder="••••••••"
                                    required
                                />
                            </div>
                        </div>

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full bg-white text-black font-black uppercase tracking-widest py-5 rounded-2xl hover:bg-neutral-200 active:scale-[0.98] transition-all disabled:opacity-20 flex items-center justify-center gap-3 text-xs cursor-pointer"
                        >
                            {loading ? 'Validando Acceso...' : (
                                <>
                                    <span>Entrar al Dashboard</span>
                                    <LogIn className="w-4 h-4" />
                                </>
                            )}
                        </button>
                    </form>

                    <div className="mt-8">
                        <div className="relative flex items-center justify-center py-4">
                            <div className="absolute inset-0 flex items-center">
                                <div className="w-full border-t border-white/5"></div>
                            </div>
                            <span className="relative bg-[#0a0a0a] px-4 text-[10px] font-black uppercase tracking-widest text-neutral-700 select-none">O continúa con</span>
                        </div>

                        <button
                            type="button"
                            disabled
                            className="w-full bg-black border border-white/5 py-5 rounded-2xl transition-all flex items-center justify-center gap-4 text-xs font-bold text-neutral-800 cursor-not-allowed opacity-50 mb-2"
                        >
                            <Chrome className="w-4 h-4" />
                            <span>Google Account (Próximamente)</span>
                        </button>
                        <p className="text-[8px] text-center font-black uppercase tracking-widest text-neutral-800">Acceso externo temporalmente deshabilitado</p>
                    </div>

                    <div className="mt-10 pt-8 border-t border-white/5 text-center">
                        <p className="text-[10px] font-bold text-neutral-700 uppercase tracking-widest select-none">
                            ¿Nuevo en RocotoClip?
                            <span className="ml-2 text-neutral-800 italic">(Registro desactivado)</span>
                        </p>
                    </div>
                </div>
            </div>

            {/* Footer Decorative Credits */}
            <div className="absolute bottom-12 text-[10px] font-black uppercase tracking-[0.4em] text-neutral-800">
                RocotoClip AI Engine • 2026
            </div>
        </div>
    );
}
