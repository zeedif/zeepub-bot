import React from 'react';

const NavigationCard = ({ item, onNavigate }) => {
    const { title, summary } = item;

    return (
        <div
            onClick={() => onNavigate(item)}
            className="bg-gray-800 rounded-lg overflow-hidden shadow-lg hover:shadow-2xl transition-all duration-300 cursor-pointer hover:scale-105 p-6 flex flex-col items-center justify-center text-center min-h-[150px]"
        >
            <div className="text-4xl mb-3">📚</div>
            <h3 className="text-lg font-bold text-white mb-2">
                {title}
            </h3>
            {summary && (
                <p className="text-sm text-gray-400 line-clamp-2">
                    {summary}
                </p>
            )}
        </div>
    );
};

export default NavigationCard;
