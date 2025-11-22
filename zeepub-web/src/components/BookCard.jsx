import React from 'react';

const BookCard = ({ book, onDownload }) => {
    const { title, author, cover_url, id } = book;

    return (
        <div className="bg-gray-800 rounded-lg overflow-hidden shadow-lg hover:shadow-2xl transition-shadow duration-300 flex flex-col h-full">
            <div className="relative aspect-[2/3] w-full overflow-hidden">
                {cover_url ? (
                    <img
                        src={cover_url}
                        alt={title}
                        className="w-full h-full object-cover transition-transform duration-300 hover:scale-105"
                        loading="lazy"
                    />
                ) : (
                    <div className="w-full h-full bg-gray-700 flex items-center justify-center text-gray-500">
                        <span className="text-4xl">📚</span>
                    </div>
                )}
            </div>

            <div className="p-4 flex flex-col flex-grow">
                <h3 className="text-lg font-bold text-white line-clamp-2 mb-1" title={title}>
                    {title}
                </h3>
                <p className="text-sm text-gray-400 mb-4 line-clamp-1">
                    {author}
                </p>

                <div className="mt-auto">
                    <button
                        onClick={() => onDownload(book)}
                        className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-2 px-4 rounded-md transition-colors duration-200 flex items-center justify-center gap-2"
                    >
                        <span>⬇️</span> Descargar
                    </button>
                </div>
            </div>
        </div>
    );
};

export default BookCard;
