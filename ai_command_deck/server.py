"""Loopback-only HTTP and read-only ALiS live stream for asciinema player."""
import asyncio
import contextlib
import json
from pathlib import Path
import re
from aiohttp import web, WSMsgType
from .storage import active
from .compact import CompactOutput

STATIC = Path(__file__).parent / "static"
ANSI = re.compile(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|[()][A-Z0-9]|[=>])')
CSP = "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"


def clean(raw):
    text = ANSI.sub('', raw.decode('utf-8', 'replace')).replace('\r\n', '\n').replace('\r', '\n')
    return ''.join(c for c in text if c in '\n\t' or ord(c) >= 32)


def uleb(value):
    value = max(0, int(value))
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def string(value):
    data = value.encode('utf-8')
    return uleb(len(data)) + data


def init_packet(header, ident=0, timestamp=0, content=''):
    return b'\x01' + uleb(ident) + uleb(timestamp) + uleb(header['width']) + uleb(header['height']) + b'\x00' + string(content)


def event_packet(event, ident, previous):
    timestamp, kind, data = event
    delta = max(0, round((timestamp-previous)*1_000_000))
    prefix = kind.encode('ascii') + uleb(ident) + uleb(delta)
    if kind == 'r':
        cols, rows = map(int, data.split('x'))
        return prefix + uleb(cols) + uleb(rows)
    return prefix + string(data)


def create_app(store):
    @web.middleware
    async def local_only(request, handler):
        # Reject DNS rebinding and cross-origin WebSocket connections.
        if request.host != f'127.0.0.1:{request.url.port}' and request.host != f'localhost:{request.url.port}':
            raise web.HTTPForbidden(text='Loopback host required')
        origin = request.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{request.url.port}', f'http://localhost:{request.url.port}'):
            raise web.HTTPForbidden(text='Same-origin access required')
        if request.method not in ('GET', 'HEAD'):
            raise web.HTTPMethodNotAllowed(request.method, ['GET', 'HEAD'])
        try:
            response = await handler(request)
        except (FileNotFoundError, KeyError):
            raise web.HTTPNotFound(text='Session not found')
        except ValueError:
            raise web.HTTPBadRequest(text='Invalid request')
        if not isinstance(response, web.WebSocketResponse):
            response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': CSP})
        return response

    app = web.Application(middlewares=[local_only])

    async def index(request):
        return web.FileResponse(STATIC / 'index.html')

    async def asset(request):
        name = request.match_info['path']
        allowed = {'app.js', 'style.css', 'vendor/asciinema-player.min.js', 'vendor/asciinema-player.css', 'vendor/asciinema-player.wasm'}
        if name not in allowed:
            raise web.HTTPNotFound()
        return web.FileResponse(STATIC / name)

    async def sessions(request):
        return web.json_response(store.sessions())

    async def config(request):
        return web.json_response({'retention_days': store.days, 'version': '0.1.0'})

    async def recording(request):
        ident = request.match_info['id']
        path = store.file(ident, '.cast')
        store.read(ident)
        if request.query.get('compact') == '1' and request.query.get('download') != '1':
            response = web.StreamResponse(headers={'Content-Type': 'application/x-asciicast', 'Cache-Control': 'no-store', 'Content-Security-Policy': CSP})
            normalizer = CompactOutput()
            with path.open(encoding='utf-8') as source:
                header = source.readline()
                if not header:
                    raise web.HTTPConflict(text='Recording is initializing')
                await response.prepare(request)
                await response.write(header.encode())
                last_time = 0
                for line in source:
                    if not line.endswith('\n'):
                        break
                    event = json.loads(line)
                    last_time = event[0]
                    if event[1] == 'o':
                        event[2] = normalizer.feed(event[2])
                        if not event[2]:
                            continue
                    await response.write((json.dumps(event, ensure_ascii=False)+'\n').encode())
                tail = normalizer.finish()
                if tail:
                    await response.write((json.dumps([last_time, 'o', tail])+'\n').encode())
            await response.write_eof()
            return response
        response = web.FileResponse(path, headers={'Content-Type': 'application/x-asciicast'})
        if request.query.get('download') == '1':
            response.headers['Content-Disposition'] = f'attachment; filename="{ident}.cast"'
        return response

    async def log(request):
        path = store.file(request.match_info['id'], '.log')
        with path.open('rb') as file:
            file.seek(max(0, path.stat().st_size-500_000))
            text = clean(file.read())
            if request.query.get('compact') == '1':
                text = '\n'.join(line for line in text.splitlines() if line.strip())
            return web.Response(text=text, content_type='text/plain')

    async def live(request):
        ident = request.match_info['id']
        store.read(ident)
        # Open before upgrading so a missing legacy recording returns HTTP 404.
        file = store.file(ident, '.cast').open(encoding='utf-8')
        ws = web.WebSocketResponse(protocols=['v1.alis'], heartbeat=20)
        normalizer = CompactOutput() if request.query.get('compact') == '1' else None
        def displayed(event):
            if normalizer and event[1] == 'o':
                event[2] = normalizer.feed(event[2])
            return event
        try:
            header_line = file.readline()
            if not header_line:
                raise web.HTTPConflict(text='Recording is initializing')
            header = json.loads(header_line)
            await ws.prepare(request)
            await ws.send_bytes(b'ALiS\x01')
            # Reconstruct terminal state from the whole recorded prefix immediately.
            # Reading only a byte tail would corrupt ANSI cursor/alternate-screen state.
            # Separate reset packets for resize events keep reconstruction in order.
            await ws.send_bytes(init_packet(header))
            seq, previous = 0, 0.0
            # Restore complete ANSI state by fast-forwarding all existing events.
            initial_end = file.seek(0, 2)
            file.seek(len(header_line.encode('utf-8')))
            while file.tell() < initial_end:
                pos = file.tell()
                line = file.readline()
                if not line.endswith('\n'):
                    file.seek(pos)
                    break
                event = displayed(json.loads(line))
                seq += 1
                await ws.send_bytes(event_packet([previous, event[1], event[2]], seq, previous))
                previous = event[0]
            async def reject_input():
                async for message in ws:
                    if message.type in (WSMsgType.TEXT, WSMsgType.BINARY):
                        await ws.close(code=1008, message=b'Read-only viewer')
                        return
            reader = asyncio.create_task(reject_input())
            try:
                while not ws.closed:
                    pos = file.tell()
                    line = file.readline()
                    if line.endswith('\n'):
                        event = displayed(json.loads(line))
                        seq += 1
                        # Live output is delivered immediately; preserve original timing in .cast.
                        await ws.send_bytes(event_packet([0, event[1], event[2]], seq, 0))
                        previous = event[0]
                        continue
                    file.seek(pos)
                    if not active(store.read(ident)):
                        await ws.send_bytes(b'\x04')
                        await reader  # Keep ended state visible until browser disconnects.
                        break
                    await asyncio.sleep(0.1)
            finally:
                reader.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await reader
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            file.close()
        return ws

    async def maintenance(app):
        store.cleanup()
        async def loop():
            while True:
                await asyncio.sleep(3600)
                await asyncio.to_thread(store.cleanup)
        task = asyncio.create_task(loop())
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    app.cleanup_ctx.append(maintenance)
    app.router.add_get('/', index)
    app.router.add_get('/static/{path:.*}', asset)
    app.router.add_get('/api/config', config)
    app.router.add_get('/api/sessions', sessions)
    app.router.add_get('/api/log/{id}', log)
    app.router.add_get('/api/cast/{id}', recording)
    app.router.add_get('/api/live/{id}', live)
    return app


def serve(store, port):
    web.run_app(create_app(store), host='127.0.0.1', port=port, print=lambda text: print(text, flush=True))
