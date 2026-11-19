import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import express from 'express';
import { createServer as createViteServer } from 'vite';

const PORT = 3000;
const ROOT_DIR = process.cwd();
const DATA_DIR = path.join(ROOT_DIR, 'data');
fs.mkdirSync(DATA_DIR, { recursive: true });

class PythonIpcClient {
  private proc: ChildProcessWithoutNullStreams | null = null;
  private rl: readline.Interface | null = null;
  private nextId = 1;
  private pending = new Map<
    number,
    { resolve: (val: unknown) => void; reject: (err: Error) => void }
  >();

  constructor() {
    this.start();
  }

  private start(): void {
    const proc = spawn('python3', ['-u', '-m', 'netscope.ipc_worker'], {
      cwd: ROOT_DIR,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',
      },
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    this.proc = proc;
    this.rl = readline.createInterface({ input: proc.stdout });

    this.rl.on('line', (line) => {
      if (!line.trim()) return;
      try {
        const msg = JSON.parse(line) as {
          id: number;
          ok: boolean;
          result?: unknown;
          error?: string;
        };
        const waiter = this.pending.get(msg.id);
        if (!waiter) return;
        this.pending.delete(msg.id);
        if (msg.ok) {
          waiter.resolve(msg.result);
        } else {
          waiter.reject(new Error(msg.error || 'Python IPC error'));
        }
      } catch {
        // ignore malformed line
      }
    });

    proc.stderr.on('data', (chunk) => {
      process.stderr.write(`[netscope-ipc] ${chunk}`);
    });

    proc.on('exit', () => {
      for (const [, waiter] of this.pending) {
        waiter.reject(new Error('Python IPC worker exited'));
      }
      this.pending.clear();
      this.proc = null;
      setTimeout(() => this.start(), 1000);
    });
  }

  call<T = unknown>(action: string, params: Record<string, unknown> = {}): Promise<T> {
    return new Promise((resolve, reject) => {
      if (!this.proc || !this.proc.stdin.writable) {
        reject(new Error('Python IPC worker not ready'));
        return;
      }
      const id = this.nextId++;
      this.pending.set(id, {
        resolve: resolve as (val: unknown) => void,
        reject,
      });
      this.proc.stdin.write(JSON.stringify({ id, action, params }) + '\n');
    });
  }

  stop(): void {
    this.proc?.kill('SIGTERM');
  }
}

class DaemonSupervisor {
  private proc: ChildProcessWithoutNullStreams | null = null;
  private stopped = false;

  start(): void {
    if (this.stopped) return;
    const proc = spawn('python3', ['-u', '-m', 'netscope.daemon', '--daemon'], {
      cwd: ROOT_DIR,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',
      },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    this.proc = proc;
    proc.stderr.on('data', (chunk) => {
      process.stderr.write(`[netscope-daemon] ${chunk}`);
    });
    proc.on('exit', () => {
      this.proc = null;
      if (!this.stopped) {
        setTimeout(() => this.start(), 2000);
      }
    });
  }

  stop(): void {
    this.stopped = true;
    this.proc?.kill('SIGTERM');
  }
}

async function bootstrap() {
  const daemon = new DaemonSupervisor();
  daemon.start();

  const ipc = new PythonIpcClient();
  const app = express();
  app.use(express.json({ limit: '1mb' }));

  app.get('/api/dashboard', async (_req, res) => {
    try {
      const data = await ipc.call('dashboard');
      res.json(data);
    } catch (err) {
      res.status(500).json({ error: (err as Error).message });
    }
  });

  app.get('/api/live/stream', (req, res) => {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.flushHeaders?.();

    let closed = false;
    let timer: NodeJS.Timeout | null = null;

    const pushTick = async () => {
      if (closed) return;
      let nextMs = 1000;
      try {
        const data = (await ipc.call('dashboard')) as {
          settings?: { refresh_interval_sec?: string };
        };
        const sec = Number(data?.settings?.refresh_interval_sec || '1');
        if (Number.isFinite(sec) && sec >= 1 && sec <= 10) {
          nextMs = sec * 1000;
        }
        if (!closed) {
          res.write(`data: ${JSON.stringify(data)}\n\n`);
        }
      } catch (err) {
        if (!closed) {
          res.write(
            `event: error\ndata: ${JSON.stringify({ error: (err as Error).message })}\n\n`
          );
        }
      }
      if (!closed) {
        timer = setTimeout(pushTick, nextMs);
      }
    };

    void pushTick();

    req.on('close', () => {
      closed = true;
      if (timer) clearTimeout(timer);
    });
  });

  app.get('/api/analytics', async (req, res) => {
    try {
      const data = await ipc.call('analytics', {
        period: typeof req.query.period === 'string' ? req.query.period : 'last_30_days',
        start: typeof req.query.start === 'string' ? req.query.start : undefined,
        end: typeof req.query.end === 'string' ? req.query.end : undefined,
        iface: typeof req.query.iface === 'string' ? req.query.iface : undefined,
      });
      res.json(data);
    } catch (err) {
      res.status(500).json({ error: (err as Error).message });
    }
  });

  app.get('/api/applications/:appId', async (req, res) => {
    try {
      const data = await ipc.call('app_detail', { app_id: req.params.appId });
      res.json(data);
    } catch (err) {
      res.status(500).json({ error: (err as Error).message });
    }
  });

  app.get('/api/capabilities', async (_req, res) => {
    try {
      const data = await ipc.call('capabilities');
      res.json(data);
    } catch (err) {
      res.status(500).json({ error: (err as Error).message });
    }
  });

  app.post('/api/history/import', async (_req, res) => {
    try {
      const data = await ipc.call('history_import', { force: true });
      res.json(data);
    } catch (err) {
      res.status(500).json({ error: (err as Error).message });
    }
  });

  app.post('/api/settings', async (req, res) => {
    try {
      const data = await ipc.call('update_settings', req.body || {});
      res.json(data);
    } catch (err) {
      res.status(500).json({ error: (err as Error).message });
    }
  });

  app.post('/api/limits', async (req, res) => {
    try {
      const data = await ipc.call('create_limit', req.body || {});
      res.json(data);
    } catch (err) {
      res.status(400).json({ error: (err as Error).message });
    }
  });

  app.delete('/api/limits/:id', async (req, res) => {
    try {
      const data = await ipc.call('delete_limit', { id: Number(req.params.id) });
      res.json(data);
    } catch (err) {
      res.status(400).json({ error: (err as Error).message });
    }
  });

  app.post('/api/alerts/ack', async (_req, res) => {
    try {
      const data = await ipc.call('ack_alerts');
      res.json(data);
    } catch (err) {
      res.status(500).json({ error: (err as Error).message });
    }
  });

  app.post('/api/browser/telemetry', async (req, res) => {
    try {
      const data = await ipc.call('browser_telemetry', req.body || {});
      res.json(data);
    } catch (err) {
      res.status(400).json({ error: (err as Error).message });
    }
  });

  app.post('/api/backup', async (_req, res) => {
    try {
      const data = await ipc.call('backup');
      res.json(data);
    } catch (err) {
      res.status(500).json({ error: (err as Error).message });
    }
  });

  app.get('/api/export', async (req, res) => {
    try {
      const fmt = typeof req.query.format === 'string' ? req.query.format : 'csv';
      const scope = typeof req.query.scope === 'string' ? req.query.scope : 'complete';
      const result = (await ipc.call('export', { format: fmt, scope })) as {
        content_type: string;
        data: string;
        encoding: string;
      };
      const ext = fmt === 'pdf' ? 'pdf' : fmt === 'json' ? 'json' : 'csv';
      res.setHeader('Content-Type', result.content_type);
      res.setHeader(
        'Content-Disposition',
        `attachment; filename="netscope-${scope}-report.${ext}"`
      );
      if (result.encoding === 'base64') {
        res.send(Buffer.from(result.data, 'base64'));
      } else {
        res.send(result.data);
      }
    } catch (err) {
      res.status(500).json({ error: (err as Error).message });
    }
  });

  app.get('/api/deb/download', (_req, res) => {
    const debPath = path.join(ROOT_DIR, 'dist-deb', 'netscope_1.0.0_amd64.deb');
    if (!fs.existsSync(debPath)) {
      res.status(404).json({ error: 'Debian package not built yet.' });
      return;
    }
    res.download(debPath, 'netscope_1.0.0_amd64.deb');
  });

  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distDir = path.join(ROOT_DIR, 'dist');
    app.use(express.static(distDir));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distDir, 'index.html'));
    });
  }

  const server = app.listen(PORT, '0.0.0.0', () => {
    console.log(`NETSCOPE server running on http://0.0.0.0:${PORT}`);
  });

  const shutdown = () => {
    daemon.stop();
    ipc.stop();
    server.close(() => process.exit(0));
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
}

void bootstrap();
