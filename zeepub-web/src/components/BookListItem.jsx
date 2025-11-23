import React from 'react';

const BookListItem = ({ book, onDownload }) => {
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
        </div>
    );
};

export default BookListItem;
