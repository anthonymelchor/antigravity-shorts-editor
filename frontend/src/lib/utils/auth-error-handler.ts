/**
 * RocotoClip Global Auth Error Sanitizer
 * This utility prevents technical/leakage errors from reaching the UI.
 */

const SENSITIVE_WORDS = [
    'forbidden', 'secret', 'api', 'key', 'database', 'table',
    'column', 'query', 'anonymous', 'disabled', 'row', 'policy',
    'rls', 'auth', 'uid', 'uuid'
];

export const sanitizeAuthError = (message: string): string => {
    if (!message) return "Ha ocurrido un error inesperado.";

    const lowercaseMsg = message.toLowerCase();

    // Check for technical leakage
    const isTechnical = SENSITIVE_WORDS.some(word => lowercaseMsg.includes(word));

    if (isTechnical) {
        console.error("[Security Leak Prevented]:", message);
        return "Ha ocurrido un error en la comunicación con el motor AI. Por favor, intenta de nuevo.";
    }

    // Friendly translations for common errors
    if (lowercaseMsg.includes('invalid login credentials')) {
        return "Credenciales incorrectas. Verifica tu email y contraseña.";
    }

    if (lowercaseMsg.includes('email not confirmed')) {
        return "Por favor, confirma tu cuenta en el enlace que enviamos a tu email.";
    }

    if (lowercaseMsg.includes('user already registered')) {
        return "Este email ya tiene una cuenta activa.";
    }

    return message;
};
