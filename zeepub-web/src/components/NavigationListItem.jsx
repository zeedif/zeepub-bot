import React from 'react';

const NavigationListItem = ({ item, onNavigate }) => {
    const { title, summary, cover_url } = item;

    return (
        <div
            onClick={() => onNavigate(item)}
            className="bg-gray-800 rounded-lg overflow-hidden shadow-md hover:shadow-lg transition-shadow duration-200 flex p-2 cursor-pointer"
            style={{ gap: '16px' }}
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
                    <div className="w-full h-full bg-blue-600 rounded flex items-center justify-center text-xl">
                        📚
                    </div>
                )}
            </div>

            <div className="flex-1 min-w-0 overflow-hidden flex items-center justify-between" style={{ gap: '8px' }}>
                <div className="flex-1 min-w-0">
                    <h3 className="text-xs font-bold text-white mb-1 break-words leading-tight">
                        {title}
                    </h3>
                    {summary && (
                        <p className="text-xs text-gray-400 break-words line-clamp-2 leading-tight">
                            {summary}
                        </p>
                    )}
                </div>

                <div className="flex-shrink-0 text-gray-400">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                </div>
            </div>
        </div>
    );
};

export default NavigationListItem;
