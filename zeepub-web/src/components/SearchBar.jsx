import React from 'react';

const SearchBar = ({ onSearch }) => {
    return (
        <div className="w-full max-w-md mx-auto mb-8">
            <div className="relative">

                <input
                    type="text"
                    className="block w-full h-14 pl-10 pr-3 border border-gray-600 rounded-lg leading-tight bg-gray-700 text-white placeholder-gray-400 focus:outline-none focus:bg-gray-600 focus:border-blue-500 transition duration-150 ease-in-out text-lg text-center"
                    placeholder="🔍 Buscar título o autor..."
                    onChange={(e) => onSearch(e.target.value)}
                />
            </div>
        </div>
    );
};

export default SearchBar;
