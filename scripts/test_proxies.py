#!/usr/bin/env python3
"""Test and benchmark proxy pool performance."""

import asyncio
import sys
import time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from cendoj.utils.proxy_manager import ProxyManager
from cendoj.config.settings import Config

async def stress_test(pm: ProxyManager, duration_minutes: int = 5, requests_per_proxy: int = 10):
    """
    Run stress test on proxy pool.
    
    Args:
        pm: ProxyManager instance
        duration_minutes: How long to run test
        requests_per_proxy: Max requests per proxy
    """
    print("=" * 80)
    print("⚡ PROXY STRESS TEST")
    print("=" * 80)
    print(f"Duration: {duration_minutes} minutes")
    print(f"Requests per proxy: {requests_per_proxy}")
    print("=" * 80)
    
    import aiohttp
    
    test_url = "http://httpbin.org/ip"
    timeout = aiohttp.ClientTimeout(total=10)
    
    # Track stats per proxy
    proxy_stats = defaultdict(lambda: {'success': 0, 'fail': 0, 'times': []})
    
    end_time = asyncio.get_event_loop().time() + duration_minutes * 60
    total_requests = 0
    total_success = 0
    
    print("\n🚀 Starting stress test...")
    
    while asyncio.get_event_loop().time() < end_time:
        proxy = pm.get_next_proxy()
        if not proxy:
            print("❌ No proxies available!")
            break
        
        proxy_url = proxy.proxy_url
        start = time.time()
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(test_url, proxy=proxy_url) as resp:
                    elapsed = time.time() - start
                    
                    if resp.status == 200:
                        total_success += 1
                        proxy_stats[proxy_url]['success'] += 1
                        proxy_stats[proxy_url]['times'].append(elapsed)
                        pm.mark_result(proxy, True, elapsed)
                    else:
                        total_requests += 1
                        proxy_stats[proxy_url]['fail'] += 1
                        pm.mark_result(proxy, False, error=f"HTTP {resp.status}")
                        
        except Exception as e:
            total_requests += 1
            proxy_stats[proxy_url]['fail'] += 1
            pm.mark_result(proxy, False, error=str(e))
        
        total_requests += 1
        
        # Progress update every 30 seconds
        if total_requests % 100 == 0:
            elapsed_test = time.time() - (asyncio.get_event_loop().time() - duration_minutes * 60)
            rps = total_requests / max(1, elapsed_test)
            success_rate = (total_success / total_requests * 100) if total_requests else 0
            print(f"   Progress: {total_requests} requests, {rps:.1f} R/s, {success_rate:.1f}% success")
    
    # Final stats
    print("\n" + "=" * 80)
    print("📊 STRESS TEST RESULTS")
    print("=" * 80)
    print(f"Total requests: {total_requests}")
    print(f"Successful: {total_success}")
    print(f"Failed: {total_requests - total_success}")
    print(f"Overall success rate: {(total_success/total_requests*100):.1f}%" if total_requests else "N/A")
    
    # Top 10 performing proxies
    print("\n🏆 Top 10 Proxies (by success rate):")
    sorted_proxies = sorted(
        proxy_stats.items(),
        key=lambda x: (x[1]['success'] / (x[1]['success'] + x[1]['fail']) if (x[1]['success'] + x[1]['fail']) > 0 else 0),
        reverse=True
    )[:10]
    
    for proxy_url, stats in sorted_proxies:
        total = stats['success'] + stats['fail']
        rate = (stats['success'] / total * 100) if total else 0
        avg_time = sum(stats['times']) / len(stats['times']) if stats['times'] else 0
        print(f"   {proxy_url}: {stats['success']}/{total} ({rate:.1f}%), avg {avg_time:.2f}s")
    
    # Save updated proxy cache
    pm._save_cache()
    print(f"\n✅ Proxy pool updated and saved to cache")
    print("=" * 80)

async def quick_test(pm: ProxyManager, num_proxies: int = 20):
    """Quick test of top N proxies."""
    print("=" * 80)
    print("🔬 QUICK PROXY TEST")
    print("=" * 80)
    print(f"Testing top {num_proxies} proxies...")
    
    import aiohttp
    test_url = "http://httpbin.org/ip"
    timeout = aiohttp.ClientTimeout(total=5)
    
    tasks = []
    for i in range(min(num_proxies, len(pm.proxies))):
        proxy = pm.proxies[i]
        tasks.append(test_single_proxy(proxy, test_url, timeout))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success_count = sum(1 for r in results if isinstance(r, dict) and r.get('success'))
    print(f"\n✅ Working proxies: {success_count}/{len(tasks)}")
    
    for i, (proxy, result) in enumerate(zip(pm.proxies[:num_proxies], results)):
        if isinstance(result, Exception):
            print(f"   {i+1}. {proxy.proxy_url}: ❌ Error - {result}")
        elif result.get('success'):
            print(f"   {i+1}. {proxy.proxy_url}: ✅ OK - {result['response_time']:.2f}s")
        else:
            print(f"   {i+1}. {proxy.proxy_url}: ❌ Failed - {result.get('error')}")

async def test_single_proxy(proxy, test_url: str, timeout) -> dict:
    """Test a single proxy."""
    import aiohttp
    start = time.time()
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(test_url, proxy=proxy.proxy_url) as resp:
                elapsed = time.time() - start
                if resp.status == 200:
                    return {'success': True, 'response_time': elapsed}
                else:
                    return {'success': False, 'error': f"HTTP {resp.status}"}
    except Exception as e:
        return {'success': False, 'error': str(e)}

async def main():
    print("Select test mode:")
    print("  1. Quick test (top 20 proxies)")
    print("  2. Stress test (5 minutes)")
    print("  3. Custom stress test")
    
    choice = input("\nEnter choice [1-3]: ").strip()
    
    config = Config()
    pm = ProxyManager({'min_proxies_required': 100}, cache_file='data/proxies_cache.json')
    await pm.initialize()
    
    if len(pm.proxies) == 0:
        print("\n❌ No proxies available! Run setup_proxies.py first.")
        sys.exit(1)
    
    if choice == '1':
        await quick_test(pm, num_proxies=20)
    elif choice == '2':
        await stress_test(pm, duration_minutes=5, requests_per_proxy=10)
    elif choice == '3':
        try:
            minutes = int(input("Duration (minutes): "))
            requests = int(input("Requests per proxy: "))
            await stress_test(pm, duration_minutes=minutes, requests_per_proxy=requests)
        except ValueError:
            print("Invalid input")
            sys.exit(1)
    else:
        print("Invalid choice")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
