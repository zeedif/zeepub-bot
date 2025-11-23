import React, { useState, useEffect } from 'react';
import WebApp from '@twa-dev/sdk';
import { fetchFeed, searchBooks } from './api';
import BookListItem from './components/BookListItem';
import NavigationListItem from './components/NavigationListItem';
import SearchBar from './components/SearchBar';

const ITEMS_PER_PAGE = 20;

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
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [navigationStack, setNavigationStack] = useState([]);
  const [currentTitle, setCurrentTitle] = useState('ZeePub Mini');
  const [currentPage, setCurrentPage] = useState(1);
  const [nextPageUrl, setNextPageUrl] = useState(null);
  const [prevPageUrl, setPrevPageUrl] = useState(null);

  const scrollContainerRef = React.useRef(null);

  useEffect(() => {
    WebApp.ready();
    WebApp.expand();
    WebApp.BackButton.onClick(() => handleBack());
    loadFeed();
  }, []);

  const loadFeed = async (url = null, depth = 0) => {
    setLoading(true);
    setError(null);
    // Reset client-side page only if loading a new URL (not just searching)
    setCurrentPage(1);
    if (scrollContainerRef.current) scrollContainerRef.current.scrollTop = 0;

    const uid = WebApp.initDataUnsafe?.user?.id;

    try {
      const data = await fetchFeed(url, uid);
      if (data && data.entries) {
        // Auto-navegación: saltar automáticamente si hay elementos de navegación y estamos en niveles iniciales
        if (depth < 2 && data.entries.length > 0) {
          // Buscar un elemento de navegación (preferiblemente "Todas las bibliotecas" o "ZeePubs")
          const navItems = data.entries.filter(item =>
            item.links?.some(l =>
              l.rel === 'subsection' ||
              (l.type?.includes('opds-catalog') && l.type?.includes('navigation'))
            )
          );

          if (navItems.length > 0) {
            // Priorizar "Todas las bibliotecas" o el primer elemento de navegación
            const targetItem = navItems.find(item =>
              item.title?.toLowerCase().includes('biblioteca') ||
              item.title?.toLowerCase().includes('zeepub')
            ) || navItems[0];

            const navLink = targetItem.links?.find(l =>
              l.rel === 'subsection' || l.type?.includes('opds-catalog')
            );

            if (navLink && navLink.href) {
              // Navegar automáticamente al siguiente nivel
              loadFeed(navLink.href, depth + 1);
              return;
            }
          }
        }

        setItems(data.entries);
        if (data.title) setCurrentTitle(data.title);

        // Capture pagination links - Relaxed check for OPDS spec
        const nextLink = data.links?.find(l => l.rel?.includes('next'));
        const prevLink = data.links?.find(l => l.rel?.includes('previous') || l.rel?.includes('prev'));

        setNextPageUrl(nextLink ? nextLink.href : null);
        setPrevPageUrl(prevLink ? prevLink.href : null);

      } else {
        setError('No se pudieron cargar los datos.');
      }
    } catch (err) {
      if (err.message === 'ACCESS_DENIED') {
        setError('ACCESS_DENIED');
      } else {
        setError('Error de conexión.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (query) => {
    if (!query.trim()) {
      loadFeed();
      setNavigationStack([]);
      WebApp.BackButton.hide();
      return;
    }

    setLoading(true);
    setCurrentPage(1);
    if (scrollContainerRef.current) scrollContainerRef.current.scrollTop = 0;
    try {
      const data = await searchBooks(query);
      if (data && data.entries) {
        setItems(data.entries);
        setCurrentTitle('Resultados de búsqueda');
      } else {
        setItems([]);
      }
    } catch (err) {
      console.error(err);
      setError('Error en la búsqueda.');
    } finally {
      setLoading(false);
    }
  };

  const debouncedSearch = useDebounce(handleSearch, 500);

  const handleNavigate = (item) => {
    const navLink = item.links?.find(l =>
      l.rel === 'subsection' || l.type?.includes('opds-catalog')
    );

    if (navLink && navLink.href) {
      setNavigationStack(prev => [...prev, {
        items,
        title: currentTitle,
        page: currentPage,
        nextPageUrl, // Save next page URL
        prevPageUrl  // Save prev page URL
      }]);
      WebApp.BackButton.show();
      loadFeed(navLink.href);
    }
  };

  const handleBack = () => {
    if (navigationStack.length > 0) {
      const previous = navigationStack[navigationStack.length - 1];
      setItems(previous.items);
      setCurrentTitle(previous.title);
      setCurrentPage(previous.page || 1);
      setNextPageUrl(previous.nextPageUrl || null); // Restore next page URL
      setPrevPageUrl(previous.prevPageUrl || null); // Restore prev page URL
      setNavigationStack(prev => prev.slice(0, -1));
      if (scrollContainerRef.current) scrollContainerRef.current.scrollTop = 0;

      if (navigationStack.length === 1) {
        WebApp.BackButton.hide();
      }
    }
  };

  const handleDownload = async (book) => {
    const downloadLink = book.links?.find(l =>
      l.rel === 'http://opds-spec.org/acquisition' ||
      l.type?.includes('epub')
    );

    if (!downloadLink || !downloadLink.href) {
      WebApp.showAlert('No se encontró el enlace de descarga para este libro.');
      return;
    }

    // Mostrar confirmación antes de descargar
    WebApp.showConfirm(
      `¿Deseas descargar "${book.title}"?`,
      async (confirmed) => {
        if (confirmed) {
          try {
            // Mostrar mensaje de carga
            WebApp.showAlert('Iniciando descarga...');

            // Hacer llamada directa al backend para procesar la descarga
            const response = await fetch('/api/download', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                title: book.title,
                author: book.author,
                download_url: downloadLink.href,
                cover_url: book.cover_url,
                user_id: WebApp.initDataUnsafe?.user?.id
              })
            });

            if (response.ok) {
              WebApp.showAlert('✅ Descarga iniciada. Revisa el chat del bot.');
            } else {
              WebApp.showAlert('❌ Error al iniciar la descarga.');
            }
          } catch (error) {
            console.error('Error downloading:', error);
            WebApp.showAlert('❌ Error de conexión.');
          }
        }
      }
    );
  };

  const isNavigationItem = (item) => {
    return item.links?.some(l =>
      l.rel === 'subsection' ||
      (l.type?.includes('opds-catalog') && l.type?.includes('navigation'))
    );
  };

  const isBook = (item) => {
    return item.links?.some(l =>
      l.rel === 'http://opds-spec.org/acquisition' ||
      l.type?.includes('epub')
    );
  };

  // Paginación para todos los items
  const totalPages = Math.max(1, Math.ceil(items.length / ITEMS_PER_PAGE));
  const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
  const endIndex = startIndex + ITEMS_PER_PAGE;
  const currentItems = items.slice(startIndex, endIndex);

  const goToNextPage = () => {
    if (currentPage < totalPages) {
      // Client-side next page
      setCurrentPage(prev => prev + 1);
      if (scrollContainerRef.current) scrollContainerRef.current.scrollTop = 0;
    } else if (nextPageUrl) {
      // Server-side next page
      // Pass depth=2 to prevent auto-navigation logic from triggering on the new page results
      loadFeed(nextPageUrl, 2);
      if (scrollContainerRef.current) scrollContainerRef.current.scrollTop = 0;
    }
  };

  const goToPrevPage = () => {
    if (currentPage > 1) {
      // Client-side prev page
      setCurrentPage(prev => prev - 1);
      if (scrollContainerRef.current) scrollContainerRef.current.scrollTop = 0;
    } else if (prevPageUrl) {
      // Server-side prev page
      // Pass depth=2 to prevent auto-navigation logic
      loadFeed(prevPageUrl, 2);
      if (scrollContainerRef.current) scrollContainerRef.current.scrollTop = 0;
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-900 text-white overflow-hidden">
      <header className="flex-none bg-blue-600 shadow-lg z-10 p-4">
        <SearchBar onSearch={debouncedSearch} />
      </header>

      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto px-2 py-3">
        {loading ? (
          <div className="flex justify-center items-center h-64">
            <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
          </div>
        ) : error === 'ACCESS_DENIED' ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-6 space-y-4">
            <div className="text-6xl">🚫</div>
            <h2 className="text-xl font-bold text-white">Acceso Restringido</h2>
            <p className="text-gray-300">
              Esta función solo está disponible para usuarios <b>VIP</b>, <b>Premium</b> o <b>Patrocinadores</b>.
            </p>
            <p className="text-sm text-gray-500">
              Contacta al administrador si crees que esto es un error.
            </p>
          </div>
        ) : error ? (
          <div className="text-center text-red-400 p-4 bg-red-900/20 rounded-lg">
            {error}
          </div>
        ) : (
          <div className="space-y-3 pb-4">
            {currentItems.map((item, index) => {
              if (isNavigationItem(item)) {
                return (
                  <NavigationListItem
                    key={item.id || index}
                    item={item}
                    onNavigate={handleNavigate}
                  />
                );
              } else if (isBook(item)) {
                return (
                  <BookListItem
                    key={item.id || index}
                    book={item}
                    onDownload={handleDownload}
                  />
                );
              }
              return null;
            })}

            {items.length === 0 && (
              <div className="text-center text-gray-500 mt-10">
                No se encontraron elementos.
              </div>
            )}
          </div>
        )}
      </div>

      {/* Barra de Navegación (Flex Item) - Alto 5% de la pantalla */}
      <div className="flex-none bg-gray-800 border-t border-gray-700 z-50 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.3)] h-[5vh] min-h-[40px]">
        <div className="flex items-center justify-between w-full h-full">

          {/* Botón Atrás (Página Anterior) */}
          <button
            onClick={goToPrevPage}
            disabled={loading || (currentPage === 1 && !prevPageUrl)}
            className="flex-1 h-full flex flex-col items-center justify-center bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-gray-700 active:bg-gray-600 transition-colors border-r border-gray-700 last:border-r-0"
            title="Página Anterior"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>

          {/* Botón Subir (Nivel Superior) */}
          <button
            onClick={handleBack}
            disabled={loading || navigationStack.length === 0}
            className="flex-1 h-full flex flex-col items-center justify-center bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-gray-700 active:bg-gray-600 transition-colors border-r border-gray-700 last:border-r-0"
            title="Subir / Volver"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
            </svg>
          </button>

          {/* Botón Adelante (Página Siguiente) */}
          <button
            onClick={goToNextPage}
            disabled={loading || (currentPage >= totalPages && !nextPageUrl)}
            className="flex-1 h-full flex flex-col items-center justify-center bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-gray-700 active:bg-gray-600 transition-colors border-r border-gray-700 last:border-r-0"
            title="Página Siguiente"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>

          {/* Botón Salir */}
          <button
            onClick={() => WebApp.close()}
            className="flex-1 h-full flex flex-col items-center justify-center bg-red-900/20 text-red-200 hover:bg-red-900/40 active:bg-red-900/60 transition-colors"
            title="Cerrar Mini App"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>

        </div>

        {/* Info de paginación pequeña */}
        {!loading && items.length > 0 && (
          <div className="absolute bottom-full left-0 right-0 bg-gray-800/90 text-center py-0.5 border-t border-gray-700 backdrop-blur-sm">
            <span className="text-[9px] text-gray-400">
              Pág {currentPage}/{totalPages} • {items.length} items
              {nextPageUrl && " • +"}
              {/* Debug info */}
              <span className="text-yellow-500 ml-2">Next: {nextPageUrl ? 'Yes' : 'No'}</span>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
