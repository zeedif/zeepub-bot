const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export const fetchFeed = async (url = null) => {
    try {
        const endpoint = url ? `${API_BASE}/feed?url=${encodeURIComponent(url)}` : `${API_BASE}/feed`;
        const response = await fetch(endpoint);
        if (!response.ok) throw new Error('Network response was not ok');
        return await response.json();
    } catch (error) {
        console.error('Error fetching feed:', error);
        return null;
    }
};

export const searchBooks = async (query) => {
    try {
        const response = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`);
        if (!response.ok) throw new Error('Network response was not ok');
        return await response.json();
    } catch (error) {
        console.error('Error searching books:', error);
        return null;
    }
};
