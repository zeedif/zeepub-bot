import React from 'react';

const BookListItem = ({ book, onDownload, isFacebookPublisher, onFacebookPost }) => {
    const { title, author, summary, cover_url } = book;

    // Extraer formato del summary si existe
    const formatMatch = summary?.match(/Format:\s*(\w+)/i);
    const format = formatMatch ? formatMatch[1] : null;
    const cleanSummary = summary?.replace(/Format:\s*\w+\s*/i, '').trim();

    return (
        <div
            className="bg-gray-800 rounded-lg overflow-hidden shadow-md hover:shadow-lg transition-shadow duration-200 flex p-2 cursor-pointer"
            style={{ gap: '16px' }}
            onClick={() => onDownload(book)}
        >
            <div className="flex-shrink-0 bg-gray-700 rounded overflow-hidden" style={{ width: '30%', maxWidth: '120px', aspectRatio: '2/3' }}>
                {cover_url ? (
                    <img
                        src={cover_url}
                        alt={title}
                        className="w-full h-full object-contain"
                        loading="lazy"
                    />
                ) : (
                    <div className="w-full h-full flex items-center justify-center text-gray-500 text-xl">
                        📚
                    </div>
                )}
            </div>

            <div className="flex-1 min-w-0 overflow-hidden">
                <h3 className="text-xs font-bold text-white mb-1 break-words leading-tight">
                    {title}
                </h3>
                <p className="text-xs text-gray-400 mb-1 break-words leading-tight">
                    {author}
                </p>
                {format && (
                    <p className="text-xs text-blue-400 mb-1 break-words leading-tight">
                        Format: {format}
                    </p>
                )}
                {cleanSummary && (
                    <p className="text-xs text-gray-500 line-clamp-2 break-words leading-tight">
                        {cleanSummary}
                    </p>
                )}
            </div>

            {isFacebookPublisher && (
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        onFacebookPost(book);
                    }}
                    className="flex-shrink-0 bg-blue-600 hover:bg-blue-700 text-white p-2 rounded-full self-center ml-2 transition-colors"
                    title="Publicar en Facebook"
                >
                    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.791-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
                    </svg>
                </button>
            )}
        </div>
    );
};

export default BookListItem;
