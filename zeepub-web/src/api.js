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
export const fetchConfig = async (uid = null) => {
    try {
        const url = uid ? `${API_BASE}/config?uid=${uid}` : `${API_BASE}/config`;

        const response = await fetch(url, {
            headers: getAuthHeaders()
        });
        if (!response.ok) throw new Error('Network response was not ok');
        return await response.json();
    } catch (error) {
        console.error('Error fetching config:', error);
        return null;
    }
};

export const downloadBook = async (book, targetChatId = null) => {
    try {
        const downloadLink = book.links?.find(l =>
            l.rel === 'http://opds-spec.org/acquisition' ||
            l.type?.includes('epub')
        );

        if (!downloadLink || !downloadLink.href) {
            throw new Error('No download link found');
        }

        const body = {
            title: book.title,
            author: book.author,
            download_url: downloadLink.href,
            cover_url: book.cover_url,
            user_id: window.Telegram?.WebApp?.initDataUnsafe?.user?.id
        };

        if (targetChatId) {
            body.target_chat_id = targetChatId;
        }

        const response = await fetch(`${API_BASE}/download`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(body)
        });

        if (!response.ok) throw new Error('Download failed');
        return true;
    } catch (error) {
        console.error('Error downloading book:', error);
        return false;
    }
};
