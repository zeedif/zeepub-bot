import React from 'react';

const SearchBar = ({ onSearch }) => {
    return (
        <div className="w-full max-w-md mx-auto mb-8">
            <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <span className="text-gray-400">🔍</span>
                </div>
                <input
                    type="text"
                    className="block w-full pl-10 pr-3 py-3 border border-gray-600 rounded-lg leading-5 bg-gray-700 text-white placeholder-gray-400 focus:outline-none focus:bg-gray-600 focus:border-blue-500 transition duration-150 ease-in-out sm:text-sm"
                    placeholder="Buscar libros por título o autor..."
                    onChange={(e) => onSearch(e.target.value)}
                />
            </div>
        </div>
    );
};

export default SearchBar;
