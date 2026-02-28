#!/usr/bin/env python3
"""CLI para Cendoj PDF Discovery."""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

import click
from sqlalchemy import func

# Add project root to path (kept for backward compatibility when running as script)
sys.path.insert(0, str(Path(__file__).parent))

from cendoj.config.settings import Config
from cendoj.scraper.discovery_scanner import DiscoveryScanner
from cendoj.storage.database import get_session, init_db
from cendoj.storage.schemas import PDFLink, DiscoverySession
from cendoj.utils.logger import get_logger

logger = get_logger(__name__)


@click.group()
@click.option('--config', default='config/sites.yaml', help='Ruta al archivo de configuración')
@click.pass_context
def cli(ctx, config):
    """CLI para descubrimiento masivo de enlaces PDF del Cendoj."""
    ctx.ensure_object(dict)
    ctx.obj['config_path'] = config


@cli.command()
@click.option('--mode', type=click.Choice(['shallow', 'deep', 'full']), default='full',
              help='Modo de discovery: shallow (tablas), deep (BFS limitado), full (BFS sin límite)')
@click.option('--validate/--no-validate', default=True,
              help='Validar URLs con HEAD request tras descubrir')
@click.option('--resume', is_flag=True,
              help='Reanudar última sesión interrumpida')
@click.option('--limit', type=int, default=0,
              help='Límite de páginas a visitar (0 = sin límite)')
@click.pass_context
def discover(ctx, mode: str, validate: bool, resume: bool, limit: int):
    """Descubrir todos los enlaces PDF del Cendoj."""
    config_path = ctx.obj['config_path']
    config = Config(config_path)
    
    # Override config from CLI
    config._config['discovery'] = config._config.get('discovery', {})
    config._config['discovery']['mode'] = mode
    config._config['discovery']['validate_on_discovery'] = validate
    
    click.echo(f"\n🚀 Iniciando Cendoj PDF Discovery")
    click.echo(f"   Modo: {mode.upper()}")
    click.echo(f"   Validación: {'SÍ' if validate else 'NO'}")
    click.echo(f"   Resume: {'SÍ' if resume else 'NO'}")
    if limit > 0:
        click.echo(f"   Límite: {limit} páginas")
    click.echo("=" * 80)
    
    async def run():
        scanner = DiscoveryScanner(config)
        
        resume_session_id = None
        if resume:
            # Get last interrupted session
            db = get_session()
            last = db.query(DiscoverySession).filter_by(
                status='interrupted'
            ).order_by(DiscoverySession.start_time.desc()).first()
            if last:
                resume_session_id = last.id
                click.echo(f"📋 Reanudando sesión: {resume_session_id}")
            else:
                click.echo("⚠️  No hay sesiones interrumpidas para reanudar")
        
        try:
            await scanner.initialize(resume_session_id)
            
            count = 0
            async for pdf in scanner.run():
                count += 1
                
                # Show progress
                if count % 10 == 0:
                    validation = pdf.get('validation') or {}
                    status = "✅" if validation.get('accessible') else "❌"
                    click.echo(f"   {count}. {pdf['url'][:80]}... {status}")
                
                if limit > 0 and count >= limit:
                    click.echo(f"\n⏹️  Límite alcanzado: {limit} páginas")
                    break
            
            click.echo("\n" + "=" * 80)
            click.echo("✅ Discovery completado")
            click.echo(f"   Session ID: {scanner.session_id}")
            click.echo(f"   Total PDFs encontrados: {count}")
            click.echo(f"   Páginas visitadas: {scanner.stats['pages_visited']}")
            
        except KeyboardInterrupt:
            click.echo("\n\n⚠️  Interrumpido por usuario")
            click.echo(f"   Session ID: {scanner.session_id}")
            click.echo("   Puedes reanudar con: python cli.py discover --resume")
            sys.exit(0)
        except Exception as e:
            click.echo(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            await scanner.cleanup()
    
    asyncio.run(run())


@cli.command()
@click.pass_context
def stats(ctx):
    """Mostrar estadísticas de discovery."""
    config_path = ctx.obj['config_path']
    config = Config(config_path)
    init_db(config.database_path)
    
    db = get_session()
    
    # PDF Link stats
    total = db.query(PDFLink).count()
    accessible = db.query(PDFLink).filter_by(status='accessible').count()
    broken = db.query(PDFLink).filter_by(status='broken').count()
    blocked = db.query(PDFLink).filter_by(status='blocked').count()
    validated = db.query(PDFLink).filter(PDFLink.validated_at.isnot(None)).count()
    
    # Session stats
    sessions_total = db.query(DiscoverySession).count()
    sessions_completed = db.query(DiscoverySession).filter_by(status='completed').count()
    sessions_failed = db.query(DiscoverySession).filter_by(status='failed').count()
    sessions_running = db.query(DiscoverySession).filter_by(status='running').count()
    
    click.echo("\n📊 ESTADÍSTICAS DE DISCOVERY")
    click.echo("=" * 80)
    
    click.echo("\n📄 Enlaces PDF:")
    click.echo(f"   Total descubiertos: {total:,}")
    if total > 0:
        click.echo(f"   Accesibles: {accessible:,} ({accessible/total*100:.1f}%)")
        click.echo(f"   Rotos: {broken:,} ({broken/total*100:.1f}%)")
        click.echo(f"   Bloqueados: {blocked:,} ({blocked/total*100:.1f}%)")
        click.echo(f"   Validados: {validated:,} ({validated/total*100:.1f}%)")
    
    click.echo("\n🔄 Sesiones:")
    click.echo(f"   Total: {sessions_total:,}")
    click.echo(f"   Completadas: {sessions_completed:,}")
    click.echo(f"   Fallidas: {sessions_failed:,}")
    click.echo(f"   En ejecución: {sessions_running:,}")
    
    # Latest session
    latest = db.query(DiscoverySession).order_by(DiscoverySession.start_time.desc()).first()
    if latest:
        click.echo("\n📅 Última sesión:")
        click.echo(f"   ID: {latest.id}")
        click.echo(f"   Modo: {latest.mode}")
        click.echo(f"   Estado: {latest.status}")
        click.echo(f"   Inicio: {latest.start_time}")
        if latest.end_time:
            duration = latest.end_time - latest.start_time
            click.echo(f"   Duración: {duration}")
        click.echo(f"   Páginas visitadas: {latest.total_pages_visited:,}")
        click.echo(f"   Enlaces encontrados: {latest.total_links_found:,}")
    
    db.close()


@cli.command()
@click.pass_context
def proxies(ctx):
    """Mostrar estado del pool de proxies."""
    try:
        from cendoj.utils.proxy_manager import ProxyManager
        
        config = Config(ctx.obj['config_path'])
        pm = ProxyManager({'min_proxies_required': 100}, cache_file='data/proxies_cache.json')
        
        stats = pm.get_stats()
        
        click.echo("\n🔌 POOL DE PROXIES")
        click.echo("=" * 80)
        click.echo(f"   Proxies totales: {stats['total_proxies']:,}")
        click.echo(f"   Saludables: {stats['healthy_proxies']:,}")
        click.echo(f"   Alto score (>70): {stats['high_score_proxies']:,}")
        click.echo(f"   Última actualización: {stats.get('last_refresh', 'N/A')}")
        
        if stats.get('countries'):
            click.echo("\n🌍 Por país (top 10):")
            for country, count in sorted(stats['countries'].items(), key=lambda x: x[1], reverse=True)[:10]:
                click.echo(f"   {country}: {count}")
        
        click.echo("\n💡 Para refrescar: python scripts/setup_proxies.py")
        click.echo("   Para testear: python scripts/test_proxies.py")
        
    except Exception as e:
        click.echo(f"❌ Error: {e}")


@cli.command()
@click.option('--output', default='cendoj_links.csv',
              help='Archivo de salida (csv, json, txt)')
@click.option('--status', default='accessible',
              type=click.Choice(['discovered', 'validated', 'accessible', 'broken', 'blocked', 'downloaded']),
              help='Filtrar por estado')
@click.option('--limit', type=int, default=0,
              help='Límite de enlaces a exportar (0 = todos)')
@click.pass_context
def export(ctx, output: str, status: str, limit: int):
    """Exportar enlaces descubiertos."""
    config_path = ctx.obj['config_path']
    config = Config(config_path)
    init_db(config.database_path)
    
    db = get_session()
    query = db.query(PDFLink).filter_by(status=status).order_by(PDFLink.discovered_at.desc())
    
    if limit > 0:
        query = query.limit(limit)
    
    links = query.all()
    
    if not links:
        click.echo("⚠️  No hay enlaces para exportar con ese filtro")
        return
    
    click.echo(f"📤 Exportando {len(links)} enlaces a {output}...")
    
    output_path = Path(output)
    ext = output_path.suffix.lower()
    
    if ext == '.csv':
        import csv
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'url', 'normalized_url', 'source_url', 'discovered_at',
                           'status', 'http_status', 'content_length', 'extraction_method'])
            for link in links:
                writer.writerow([
                    link.id,
                    link.url,
                    link.normalized_url,
                    link.source_url,
                    link.discovered_at.isoformat() if link.discovered_at else '',
                    link.status,
                    link.http_status,
                    link.content_length,
                    link.extraction_method
                ])
    
    elif ext == '.json':
        data = []
        for link in links:
            data.append({
                'id': link.id,
                'url': link.url,
                'normalized_url': link.normalized_url,
                'source_url': link.source_url,
                'discovered_at': link.discovered_at.isoformat() if link.discovered_at else None,
                'status': link.status,
                'http_status': link.http_status,
                'content_type': link.content_type,
                'content_length': link.content_length,
                'final_url': link.final_url,
                'extraction_method': link.extraction_method,
                'extraction_confidence': link.extraction_confidence,
                'metadata': link.metadata_json,
            })
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    elif ext == '.txt':
        with open(output_path, 'w', encoding='utf-8') as f:
            for link in links:
                f.write(link.url + '\n')
    
    else:
        click.echo(f"❌ Formato no soportado: {ext}")
        click.echo("   Usa: .csv, .json, o .txt")
        db.close()
        return
    
    click.echo(f"✅ Exportado completado: {len(links)} enlaces")
    db.close()


@cli.command()
@click.pass_context
def sessions(ctx):
    """Listar sesiones de discovery."""
    config_path = ctx.obj['config_path']
    config = Config(config_path)
    init_db(config.database_path)
    
    db = get_session()
    sessions = db.query(DiscoverySession).order_by(DiscoverySession.start_time.desc()).limit(20).all()
    
    if not sessions:
        click.echo("📭 No hay sesiones registradas")
        return
    
    click.echo("\n📅 SESIONES RECIENTES")
    click.echo("=" * 80)
    
    for sess in sessions:
        start = sess.start_time.strftime('%Y-%m-%d %H:%M') if sess.start_time else 'N/A'
        status_icon = {'completed': '✅', 'failed': '❌', 'running': '🟢',
                      'interrupted': '⏸️', 'cancelled': '🚫'}.get(sess.status, '⚪')
        
        click.echo(f"{status_icon} {sess.id[:8]} | {sess.mode:6} | {sess.status:10} | {start}")
        if sess.total_pages_visited or sess.total_links_found:
            click.echo(f"    📄 Páginas: {sess.total_pages_visited:,} | 🔗 Enlaces: {sess.total_links_found:,}")
    
    db.close()


@cli.command()
@click.pass_context
def proxy_stats(ctx):
    """Alias para 'proxies'."""
    ctx.forward(proxies)


@cli.command()
@click.pass_context
def help(ctx):
    """Mostrar ayuda detallada."""
    click.echo("""
🆘 CENDOJ PDF DISCOVERY - AYUDA

COMANDOS PRINCIPALES:
  discover        Iniciar discovery de enlaces PDF
  stats           Mostrar estadísticas de enlaces descubiertos
  proxies         Mostrar estado del pool de proxies
  export          Exportar enlaces a CSV/JSON/TXT
  sessions        Listar sesiones de discovery

EJEMPLOS DE USO:
  
  # Discovery completo (full mode) sin límites
  python cli.py discover --mode full
  
  # Discovery profundo (deep) con validación, reanudando si hay interrupción
  python cli.py discover --mode deep --validate --resume
  
  # Discovery rápido (shallow) solo tablas, límite 100 páginas
  python cli.py discover --mode shallow --limit 100
  
  # Ver estadísticas
  python cli.py stats
  
  # Exportar todos los enlaces accesibles a CSV
  python cli.py export --status accessible --output all_links.csv
  
  # Exportar solo losbroken a JSON
  python cli.py export --status broken --output broken.json

PRIMERA EJECUCIÓN:
  1. python scripts/setup_proxies.py    # Preparar pool de proxies
  2. python scripts/harvest_agents.py   # Actualizar user agents
  3. python cli.py discover --mode full # Iniciar discovery

NOTAS:
  - El discovery puede durar varios días según el sitio
  - Se guarda automáticamente en data/cendoj.db
  - Puedes interrumpir con Ctrl+C y reanudar con --resume
  - Los proxies se rotan automáticamente
  - Se detectan CAPTCHAs automáticamente (pausa manual)
    """)
    click.echo("=" * 80)


if __name__ == '__main__':
    cli()
