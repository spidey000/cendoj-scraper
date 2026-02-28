#!/usr/bin/env python3
"""Harvest/update user agents from online sources."""

import asyncio
import sys
from pathlib import Path
import json
import re
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import aiohttp

# Sources for real user agents
UA_SOURCES = {
    'useragentstring': 'https://www.useragentstring.com/pages/useragentstring.php?name=All',
    'whatismybrowser': 'https://developers.whatismybrowser.com/useragents/explore/',
}

# Known good UAs (hardcoded fallback)
DEFAULT_UAS = [
    # Chrome
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7; rv:109.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/120.0",
    # Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]

async def fetch_from_httpbin():
    """Get sample UAs from httpbin.org/user_agent (just one)."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://httpbin.org/user_agent') as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [data.get('user_agent')]
    except:
        pass
    return []

async def main():
    print("=" * 80)
    print("🔄 HARVEST USER AGENTS")
    print("=" * 80)
    
    ua_file = Path('config/user_agents.txt')
    
    print("\n📡 Fetching fresh user agents...")
    
    all_uas = set()
    
    # Method 1: httpbin
    print("   - From httpbin.org...")
    uas = await fetch_from_httpbin()
    all_uas.update(uas)
    print(f"     Found: {len(uas)}")
    
    # Method 2: Use default list (most reliable)
    print("   - Using default curated list...")
    all_uas.update(DEFAULT_UAS)
    print(f"     Added: {len(DEFAULT_UAS)}")
    
    # Remove duplicates, empty strings, and sort
    uas_final = sorted([ua.strip() for ua in all_uas if ua and len(ua) > 10])
    
    # Remove too similar ones (basic dedup)
    unique_uas = []
    for ua in uas_final:
        # Simple fingerprint: browser name + major version
        if re.search(r'Chrome/(\d+)', ua):
            major = re.search(r'Chrome/(\d+)', ua).group(1)
            fingerprint = f"Chrome/{major}"
        elif re.search(r'Firefox/(\d+)', ua):
            major = re.search(r'Firefox/(\d+)', ua).group(1)
            fingerprint = f"Firefox/{major}"
        elif re.search(r'Safari/(\d+)', ua):
            major = re.search(r'Safari/(\d+)', ua).group(1)
            fingerprint = f"Safari/{major}"
        elif re.search(r'Edg/(\d+)', ua):
            major = re.search(r'Edg/(\d+)', ua).group(1)
            fingerprint = f"Edge/{major}"
        else:
            fingerprint = ua[:50]
        
        if not any(fingerprint in existing for existing in unique_uas):
            unique_uas.append(ua)
    
    # Save to file
    header = f"""# User-Agent Pool for Cendoj Scraper
# Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
# Source: Harvested from multiple sources + curated defaults
# Total: {len(unique_uas)} user agents

"""
    
    with open(ua_file, 'w') as f:
        f.write(header)
        for ua in unique_uas:
            f.write(ua + '\n')
    
    print(f"\n✅ Saved {len(unique_uas)} user agents to {ua_file}")
    print("\n📊 Breakdown:")
    
    browsers = defaultdict(int)
    for ua in unique_uas:
        if 'Chrome' in ua and 'Edg' not in ua:
            browsers['Chrome'] += 1
        elif 'Firefox' in ua:
            browsers['Firefox'] += 1
        elif 'Safari' in ua and 'Chrome' not in ua:
            browsers['Safari'] += 1
        elif 'Edg' in ua:
            browsers['Edge'] += 1
        else:
            browsers['Other'] += 1
    
    for browser, count in sorted(browsers.items(), key=lambda x: x[1], reverse=True):
        print(f"   {browser}: {count}")
    
    print("=" * 80)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
