import asyncio
import datetime as dt
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from aiohttp.test_utils import TestClient, TestServer
from aiohttp import WSMsgType
from ai_command_deck.storage import Store, utcnow
from ai_command_deck.server import create_app


class StorageTests(unittest.TestCase):
    def test_retention_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory, 7)
            now=time.time()
            for n, days, running, crashed in [(1,8,False,False),(2,6,False,False),(3,10,True,False),(4,9,False,True)]:
                ident=f'{n:032x}'
                meta=dict(id=ident,name='test',created=utcnow(),pid=os.getpid() if running else 99999999)
                if not running and not crashed:meta['ended']=dt.datetime.fromtimestamp(now-days*86400,dt.timezone.utc).isoformat()
                store.save(meta)
                for suffix in ('.log','.cast'):
                    store.file(ident,suffix).write_text('test')
                for suffix in ('.json','.log','.cast'):
                    os.utime(store.file(ident,suffix),(now-days*86400,now-days*86400))
            self.assertEqual(set(store.cleanup(now)),{f'{1:032x}',f'{4:032x}'})
            self.assertEqual({p.stem for p in Path(directory).glob('*.json')},{f'{2:032x}',f'{3:032x}'})
            self.assertEqual(Path(directory).stat().st_mode&0o777,0o700)
            self.assertEqual(store.file(f'{2:032x}','.json').stat().st_mode&0o777,0o600)
            with self.assertRaises(ValueError):store.file('../../bad','.log')
            with self.assertRaises(ValueError):Store(directory,0)


class RecorderTests(unittest.TestCase):
    def test_real_pty_utf8_and_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            env={**os.environ,'TERMINAL_VIEWER_DATA':directory}
            script="import os,time; b='中文 ✓'.encode(); os.write(1,b[:2]); time.sleep(.05); os.write(1,b[2:]); raise SystemExit(7)"
            result=subprocess.run([sys.executable,'-m','ai_command_deck','run','--name','本机测试','--',sys.executable,'-c',script],env=env,input=b'',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
            self.assertEqual(result.returncode,7,result.stderr)
            meta=json.loads(next(Path(directory).glob('*.json')).read_text())
            self.assertEqual(meta['exit_code'],7)
            lines=next(Path(directory).glob('*.cast')).read_text().splitlines()
            header,*events=map(json.loads,lines)
            self.assertEqual(header['version'],2)
            text=''.join(e[2] for e in events if e[1]=='o')
            self.assertTrue(text.endswith('中文 ✓'),repr(text))
            self.assertNotIn('\ufffd',text)
            self.assertTrue(all(a[0]<=b[0] for a,b in zip(events,events[1:])))
            self.assertTrue(all(e[1]!='i' for e in events))
            self.assertEqual(next(Path(directory).glob('*.cast')).stat().st_mode&0o777,0o600)

    def test_terminal_resize_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            env={**os.environ,'TERMINAL_VIEWER_DATA':directory}
            script="import time; print('READY',flush=True); time.sleep(.5); print('DONE',flush=True)"
            proc=subprocess.Popen([sys.executable,'-m','ai_command_deck','run','--',sys.executable,'-c',script],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
            try:
                buf=b'';deadline=time.monotonic()+5
                while b'READY' not in buf and time.monotonic()<deadline:
                    if select.select([proc.stdout],[],[],.2)[0]:buf+=os.read(proc.stdout.fileno(),4096)
                self.assertIn(b'READY',buf)
                os.kill(proc.pid,signal.SIGWINCH)
                proc.communicate(timeout=5)
                lines=next(Path(directory).glob('*.cast')).read_text().splitlines()
                self.assertTrue(any(json.loads(line)[1]=='r' for line in lines[1:]))
            finally:
                if proc.poll() is None:proc.kill();proc.wait()

    def test_hidden_input_is_never_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            env={**os.environ,'TERMINAL_VIEWER_DATA':directory}
            script="import termios; s=termios.tcgetattr(0); s[3]&=~termios.ECHO; termios.tcsetattr(0,termios.TCSANOW,s); print('READY',flush=True); input(); print('ACCEPTED',flush=True)"
            proc=subprocess.Popen([sys.executable,'-m','ai_command_deck','run','--',sys.executable,'-c',script],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
            try:
                buf=b'';deadline=time.monotonic()+8
                while b'READY' not in buf and time.monotonic()<deadline:
                    if select.select([proc.stdout],[],[],.2)[0]:buf+=os.read(proc.stdout.fileno(),4096)
                self.assertIn(b'READY',buf)
                out,err=proc.communicate(b'synthetic-secret-for-test\n',timeout=8)
                self.assertEqual(proc.returncode,0,err)
                self.assertIn(b'ACCEPTED',out)
                for path in Path(directory).glob('*'):
                    self.assertNotIn(b'synthetic-secret-for-test',path.read_bytes())
            finally:
                if proc.poll() is None:proc.kill();proc.wait()


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name,7)
        self.ident='1'*32
        self.store.save(dict(id=self.ident,name='synthetic demo',created=utcnow(),pid=os.getpid()))
        self.store.file(self.ident,'.log').write_bytes(b'\x1b[32mhello\x1b[0m\n')
        self.store.file(self.ident,'.cast').write_text(json.dumps(dict(version=2,width=100,height=30))+'\n'+json.dumps([.1,'o','hello'])+'\n')
        self.client=TestClient(TestServer(create_app(self.store)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close();self.temp.cleanup()

    async def test_read_only_routes_and_old_logs(self):
        response=await self.client.get('/api/sessions');data=await response.json()
        self.assertTrue(data[0]['active']);self.assertTrue(data[0]['recording'])
        self.assertNotIn('pid',data[0])
        response=await self.client.get('/api/log/'+self.ident)
        self.assertEqual(await response.text(),'hello\n')
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        for path in ['/api/cast/'+self.ident,'/','/static/app.js','/static/vendor/asciinema-player.min.js']:
            response=await self.client.get(path);self.assertEqual(response.status,200,path)
        response=await self.client.get('/api/cast/'+self.ident+'?download=1')
        self.assertIn('attachment',response.headers['Content-Disposition'])
        for method,path,kwargs,status in [
            ('post','/api/sessions',{},405),
            ('get','/api/config',{'headers':{'Host':'evil.example'}},403),
            ('get','/api/config',{'headers':{'Origin':'https://evil.example'}},403),
            ('get','/api/log/not-valid',{},400),
            ('get','/api/cast/'+'2'*32,{},404),
            ('get','/static/secret.json',{},404),
        ]:
            response=await getattr(self.client,method)(path,**kwargs)
            self.assertEqual(response.status,status,(path,await response.text()))
        self.store.file(self.ident,'.cast').unlink()
        response=await self.client.get('/api/sessions');self.assertFalse((await response.json())[0]['recording'])

    async def test_websocket_live_append_reconnect_and_end(self):
        async def connect():
            ws=await self.client.ws_connect('/api/live/'+self.ident,protocols=['v1.alis'])
            self.assertEqual(ws.protocol,'v1.alis')
            self.assertEqual((await ws.receive(timeout=3)).data,b'ALiS\x01')
            self.assertEqual((await ws.receive(timeout=3)).data[0],1)
            self.assertIn(b'hello',(await ws.receive(timeout=3)).data)
            return ws
        ws=await connect()
        with self.store.file(self.ident,'.cast').open('a') as out:out.write(json.dumps([.3,'o','new 中文'])+'\n')
        packet=await ws.receive(timeout=3)
        self.assertIn('new 中文'.encode(),packet.data)
        await ws.close()
        ws=await connect()
        self.assertIn('new 中文'.encode(),(await ws.receive(timeout=3)).data)
        meta=self.store.read(self.ident);meta['ended']=utcnow();self.store.save(meta)
        self.assertEqual((await ws.receive(timeout=3)).data,b'\x04')
        await ws.close()

    async def test_websocket_rejects_input_and_foreign_origin(self):
        with self.assertRaises(Exception):
            await self.client.ws_connect('/api/live/'+self.ident,headers={'Origin':'http://evil.example'})
        ws=await self.client.ws_connect('/api/live/'+self.ident,protocols=['v1.alis'])
        await ws.send_str('echo do-not-execute')
        for _ in range(6):
            msg=await ws.receive(timeout=3)
            if msg.type==WSMsgType.CLOSE:break
        self.assertEqual(ws.close_code,1008)
        self.assertNotIn('do-not-execute',self.store.file(self.ident,'.log').read_text())
        await ws.close()


if __name__=='__main__':unittest.main()
