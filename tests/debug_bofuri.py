#!/usr/bin/env python3
"""Test script to extract metadata from an EPUB URL and see what gets extracted."""

import asyncio
import sys
sys.path.insert(0, '/app')

from utils.http_client import fetch_bytes
from services.epub_service import parse_opf_from_epub, extract_internal_title
from urllib.parse import unquote, urlparse

async def test_epub_metadata():
    # Bofuri URL from logs
    url = "https://zeepubs.com/api/opds/0f7c40c7-633e-4c66-9221-eccc11c84fd6/series/165/volume/468/chapter/468/download/Bofuri.%20No%20quiero%20lastimarme%2C%20as%C3%AD%20que%20maxear%C3%A9%20mi%20defensa%20-%20V01%20%5BShinsengumiTL%5D.epub"
    
    print(f"Fetching EPUB from: {url}")
    epub_bytes = await fetch_bytes(url, timeout=60)
    
    if not epub_bytes:
        print("Failed to fetch EPUB")
        return
    
    if isinstance(epub_bytes, str):
        print(f"EPUB saved to temp file: {epub_bytes}")
        with open(epub_bytes, 'rb') as f:
            epub_bytes = f.read()
    
    print(f"\nEPUB size: {len(epub_bytes)} bytes")
    
    # Parse OPF
    print("\n=== OPF Metadata ===")
    opf_meta = await parse_opf_from_epub(epub_bytes)
    if opf_meta:
        for key, value in opf_meta.items():
            print(f"{key}: {value}")
    else:
        print("No OPF metadata found")
    
    # Extract internal title
    print("\n=== Internal Title ===")
    internal_title = extract_internal_title(epub_bytes)
    print(f"internal_title: {internal_title}")
    
    # Extract filename title
    print("\n=== Filename Title ===")
    filename_title = unquote(urlparse(url).path.split("/")[-1]).replace(".epub", "")
    print(f"filename_title: {filename_title}")
    
    # Check what would be used
    print("\n=== Format Check ===")
    print(f"titulo_serie (collection): {opf_meta.get('titulo_serie') if opf_meta else None}")
    print(f"internal_title: {internal_title}")
    
    if internal_title and opf_meta and opf_meta.get('titulo_serie'):
        print("\n✅ Would use NEW format (Epub de: ...)")
    else:
        print("\n❌ Would use OLD format (fallback)")
        print(f"Missing: ", end="")
        if not internal_title:
            print("internal_title ", end="")
        if not opf_meta or not opf_meta.get('titulo_serie'):
            print("titulo_serie")

if __name__ == "__main__":
    asyncio.run(test_epub_metadata())
