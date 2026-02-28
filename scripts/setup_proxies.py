#!/usr/bin/env python3
"""Setup and validate proxy pool for Cendoj scraper."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cendoj.utils.proxy_manager import ProxyManager
from cendoj.config.settings import Config

async def main():
    """Main entry point."""
    print("=" * 80)
    print("🔧 CENDOJ PROXY SETUP")
    print("=" * 80)

    # Load config
    config = Config()
    
    # Create proxy manager
    proxy_config = {
        'min_proxies_required': 100,
        'min_score': 30,
    }
    pm = ProxyManager(proxy_config, cache_file='data/proxies_cache.json')

    # Initialize and fetch proxies
    print("\n📡 Fetching proxies from public sources...")
    await pm.initialize()

    # Show stats
    stats = pm.get_stats()
    print("\n📊 Proxy Pool Statistics:")
    print(f"   Total proxies: {stats['total_proxies']}")
    print(f"   Healthy proxies: {stats['healthy_proxies']}")
    print(f"   High score (>70): {stats['high_score_proxies']}")
    
    if stats['countries']:
        print("\n🌍 Countries:")
        for country, count in sorted(stats['countries'].items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"   {country}: {count}")
    
    print("\n✅ Proxy setup complete!")
    print(f"   Cache saved to: data/proxies_cache.json")
    print("\n💡 Next steps:")
    print("   1. Run: python scripts/test_proxies.py (to benchmark)")
    print("   2. Run: python cli.py discover --mode full (to start discovery)")
    print("=" * 80)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
