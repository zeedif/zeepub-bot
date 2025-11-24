const API_BASE = import.meta.env.VITE_API_URL || '/api';

// Helper para obtener headers con autenticación
const getAuthHeaders = () => {
    const headers = {
        'Content-Type': 'application/json',
    };

    // Obtener initData de Telegram WebApp
    if (window.Telegram?.WebApp?.initData) {
        headers['X-Telegram-Data'] = window.Telegram.WebApp.initData;
    }

    return headers;
};

export const fetchFeed = async (url = null, uid = null) => {
    try {
        let endpoint = url ? `${API_BASE}/feed?url=${encodeURIComponent(url)}` : `${API_BASE}/feed`;

        // Append UID if provided (aún se usa para lógica de negocio, pero la seguridad va en el header)
        if (uid) {
            const separator = endpoint.includes('?') ? '&' : '?';
            endpoint += `${separator}uid=${uid}`;
        }

        const response = await fetch(endpoint, {
            headers: getAuthHeaders()
        });

        if (response.status === 403 || response.status === 401) {
            throw new Error('ACCESS_DENIED');
        }

        if (!response.ok) throw new Error('Network response was not ok');
        return await response.json();
    } catch (error) {
        if (error.message === 'ACCESS_DENIED') throw error;
        console.error('Error fetching feed:', error);
        return null;
    }
};

export const searchBooks = async (query) => {
    try {
        const response = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`, {
            headers: getAuthHeaders()
        });
        if (!response.ok) throw new Error('Network response was not ok');
        return await response.json();
    } catch (error) {
        console.error('Error searching books:', error);
        return null;
    }
};
