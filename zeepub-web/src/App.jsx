import React, { useState, useEffect, useCallback } from 'react';
import WebApp from '@twa-dev/sdk';
import { fetchFeed, searchBooks } from './api';
import BookCard from './components/BookCard';
import SearchBar from './components/SearchBar';
import debounce from 'lodash.debounce';

// Simple debounce implementation if lodash is not available or to keep it light
const useDebounce = (callback, delay) => {
  const callbackRef = React.useRef(callback);
  React.useLayoutEffect(() => {
    callbackRef.current = callback;
  });
  return React.useMemo(
    () => (...args) => {
      if (window.debounceTimer) clearTimeout(window.debounceTimer);
      window.debounceTimer = setTimeout(() => callbackRef.current(...args), delay);
    },
    [delay]
  );
};

function App() {
  const [books, setBooks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Initialize Telegram WebApp
    WebApp.ready();
    WebApp.expand(); // Expand to full height

    // Load initial feed
    loadFeed();
  }, []);

  const loadFeed = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchFeed();
      if (data && data.entries) {
        setBooks(data.entries);
      } else {
        setError('No se pudieron cargar los libros.');
      }
    } catch (err) {
      setError('Error de conexión.');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (query) => {
    if (!query.trim()) {
      loadFeed();
      return;
    }

    setLoading(true);
    try {
      const data = await searchBooks(query);
      if (data && data.entries) {
        setBooks(data.entries);
      } else {
        setBooks([]);
      }
    } catch (err) {
      console.error(err);
      setError('Error en la búsqueda.');
    } finally {
      setLoading(false);
    }
  };

  // Debounce search input
  const debouncedSearch = useDebounce(handleSearch, 500);

  const handleDownload = (book) => {
    // Send data back to Telegram Bot
    // The bot will receive this in a "web_app_data" service message
    // We send the book ID or download link
    const data = JSON.stringify({
      action: 'download',
      book_id: book.id,
      title: book.title
    });

    WebApp.sendData(data);
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white p-4">
      <header className="mb-6 text-center">
        <h1 className="text-3xl font-bold mb-2 bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
          ZeePub Mini
        </h1>
        <p className="text-gray-400">Tu biblioteca personal en Telegram</p>
      </header>

      <SearchBar onSearch={debouncedSearch} />

      {loading ? (
        <div className="flex justify-center items-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
        </div>
      ) : error ? (
        <div className="text-center text-red-400 p-4 bg-red-900/20 rounded-lg">
          {error}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {books.map((book, index) => (
            <BookCard
              key={book.id || index}
              book={book}
              onDownload={handleDownload}
            />
          ))}
        </div>
      )}

      {!loading && books.length === 0 && !error && (
        <div className="text-center text-gray-500 mt-10">
          No se encontraron libros.
        </div>
      )}
    </div>
  );
}

export default App;
