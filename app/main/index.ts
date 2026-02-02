/**
 * Electron Main Process
 *
 * Responsibilities:
 * - Create browser window with Next.js UI
 * - Spawn and manage Python backend process
 * - Handle IPC communication
 * - Manage app lifecycle
 */

import { app, BrowserWindow, ipcMain, dialog, shell } from 'electron';
import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

// =============================================================================
// Configuration
// =============================================================================

// Use app.isPackaged for reliable production detection
// NODE_ENV isn't always set correctly in packaged apps
const isDev = !app.isPackaged;
const BACKEND_PORT = 8001;
const FRONTEND_URL = 'http://localhost:3001';  // Only used in dev mode

// =============================================================================
// Global State
// =============================================================================

let mainWindow: BrowserWindow | null = null;
let pythonProcess: ChildProcess | null = null;

// =============================================================================
// Python Backend Management
// =============================================================================

function getBackendPath(): string {
  if (isDev) {
    // Development: backend is in sibling directory
    // __dirname is app/main/dist, so go up 3 levels to project root
    return path.join(__dirname, '../../../backend');
  } else {
    // Production: backend is bundled in resources
    return path.join(process.resourcesPath, 'backend');
  }
}

function getBackendExecutable(): string | null {
  if (isDev) {
    // Development: use Python
    return null;
  }

  // Production: use bundled youresearch-backend executable
  const backendPath = getBackendPath();
  const executablePath = path.join(backendPath, 'youresearch-backend');

  if (fs.existsSync(executablePath)) {
    return executablePath;
  }

  console.warn('Bundled backend executable not found, falling back to Python');
  return null;
}

function getPythonExecutable(): string {
  // Try to find Python in common locations
  const candidates = [
    'python3',
    'python',
    '/usr/bin/python3',
    '/usr/local/bin/python3',
    '/opt/homebrew/bin/python3',
  ];

  for (const candidate of candidates) {
    try {
      const result = require('child_process').execSync(`which ${candidate}`, { encoding: 'utf8' });
      if (result.trim()) {
        return result.trim();
      }
    } catch {
      // Try next candidate
    }
  }

  return 'python3'; // Default fallback
}

async function checkBackendHealth(): Promise<boolean> {
  const http = require('http');
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/api/health`, (res: any) => {
      resolve(res.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(1000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function startPythonBackend(): Promise<void> {
  // First check if backend is already running (started by start.sh or another process)
  const isAlreadyRunning = await checkBackendHealth();
  if (isAlreadyRunning) {
    console.log('Backend is already running, skipping spawn');
    return;
  }

  const backendPath = getBackendPath();
  const bundledExecutable = getBackendExecutable();

  console.log(`Starting backend from: ${backendPath}`);

  // Check if backend directory exists
  if (!fs.existsSync(backendPath)) {
    console.error(`Backend directory not found: ${backendPath}`);
    return;
  }

  if (bundledExecutable) {
    // Production: use bundled executable
    console.log(`Using bundled executable: ${bundledExecutable}`);

    pythonProcess = spawn(
      bundledExecutable,
      ['--host', '127.0.0.1', '--port', String(BACKEND_PORT)],
      {
        cwd: backendPath,
        env: {
          ...process.env,
          AURA_RESOURCES_PATH: process.resourcesPath,
        },
        stdio: ['pipe', 'pipe', 'pipe'],
      }
    );
  } else {
    // Development: use Python
    const pythonExe = getPythonExecutable();
    console.log(`Using Python: ${pythonExe}`);

    pythonProcess = spawn(
      pythonExe,
      ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)],
      {
        cwd: backendPath,
        env: {
          ...process.env,
          PYTHONUNBUFFERED: '1',
          AURA_RESOURCES_PATH: isDev ? path.join(__dirname, '../../../') : process.resourcesPath,
        },
        stdio: ['pipe', 'pipe', 'pipe'],
      }
    );
  }

  pythonProcess.stdout?.on('data', (data) => {
    console.log(`[Backend] ${data.toString().trim()}`);
  });

  pythonProcess.stderr?.on('data', (data) => {
    console.error(`[Backend] ${data.toString().trim()}`);
  });

  pythonProcess.on('error', (error) => {
    console.error('Failed to start backend:', error);
  });

  pythonProcess.on('exit', (code, signal) => {
    console.log(`Backend exited with code ${code}, signal ${signal}`);
    pythonProcess = null;
  });

  // Wait for backend to be ready
  await waitForBackend();
}

async function waitForBackend(maxAttempts = 30): Promise<boolean> {
  const http = require('http');

  for (let i = 0; i < maxAttempts; i++) {
    try {
      await new Promise<void>((resolve, reject) => {
        const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/api/health`, (res: any) => {
          if (res.statusCode === 200) {
            resolve();
          } else {
            reject(new Error(`Status ${res.statusCode}`));
          }
        });
        req.on('error', reject);
        req.setTimeout(1000, () => {
          req.destroy();
          reject(new Error('Timeout'));
        });
      });
      console.log('Backend is ready!');
      return true;
    } catch {
      console.log(`Waiting for backend... (${i + 1}/${maxAttempts})`);
      await new Promise((r) => setTimeout(r, 1000));
    }
  }

  console.error('Backend failed to start');
  return false;
}

function stopPythonBackend(): void {
  if (pythonProcess) {
    console.log('Stopping Python backend...');
    pythonProcess.kill('SIGTERM');

    // Force kill after timeout
    setTimeout(() => {
      if (pythonProcess) {
        pythonProcess.kill('SIGKILL');
      }
    }, 5000);
  }
}

// =============================================================================
// Window Management
// =============================================================================

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 1200,
    minHeight: 700,
    title: 'YouResearch',
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 15, y: 4 },
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Load the app
  if (isDev) {
    mainWindow.loadURL(FRONTEND_URL);
    mainWindow.webContents.openDevTools();
  } else {
    // In production, the out folder is unpacked from asar
    // It's located at: app.asar.unpacked/out/index.html
    // __dirname is inside app.asar/main/dist
    // So we need: go up to app.asar, replace with app.asar.unpacked, then out/
    const asarPath = path.join(__dirname, '../..');  // app.asar
    const unpackedPath = asarPath + '.unpacked';
    const indexPath = path.join(unpackedPath, 'out/index.html');
    console.log('Loading production index from:', indexPath);
    mainWindow.loadFile(indexPath);
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// =============================================================================
// IPC Handlers
// =============================================================================

function setupIpcHandlers(): void {
  // Get backend URL
  ipcMain.handle('get-backend-url', () => {
    return `http://127.0.0.1:${BACKEND_PORT}`;
  });

  // Open project dialog
  ipcMain.handle('open-project', async () => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ['openDirectory'],
      title: 'Open LaTeX Project',
      message: 'Select a LaTeX project directory',
    });

    if (!result.canceled && result.filePaths.length > 0) {
      return result.filePaths[0];
    }
    return null;
  });

  // Create new project dialog
  ipcMain.handle('new-project', async (_event, name: string) => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ['openDirectory', 'createDirectory'],
      title: 'Choose Location for New Project',
    });

    if (!result.canceled && result.filePaths.length > 0) {
      const projectPath = path.join(result.filePaths[0], name);

      // Create project directory
      if (!fs.existsSync(projectPath)) {
        fs.mkdirSync(projectPath, { recursive: true });
      }

      return projectPath;
    }
    return null;
  });

  // Get projects directory
  ipcMain.handle('get-projects-dir', () => {
    const homeDir = app.getPath('home');
    const projectsDir = path.join(homeDir, 'youresearch-projects');

    // Create if doesn't exist
    if (!fs.existsSync(projectsDir)) {
      fs.mkdirSync(projectsDir, { recursive: true });
    }

    return projectsDir;
  });

  // Reveal file in Finder/Explorer
  ipcMain.handle('reveal-in-finder', async (_event, filePath: string) => {
    shell.showItemInFolder(filePath);
  });

  // Open URL in default system browser
  ipcMain.handle('open-external', async (_event, url: string) => {
    if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
      await shell.openExternal(url);
    }
  });

  // Settings storage (persistent across app restarts)
  const settingsPath = path.join(app.getPath('userData'), 'settings.json');

  ipcMain.handle('get-settings', async () => {
    try {
      if (fs.existsSync(settingsPath)) {
        const data = fs.readFileSync(settingsPath, 'utf-8');
        return JSON.parse(data);
      }
    } catch (e) {
      console.error('Failed to load settings:', e);
    }
    return null;
  });

  ipcMain.handle('save-settings', async (_event, settings: Record<string, unknown>) => {
    try {
      fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2), 'utf-8');
      return true;
    } catch (e) {
      console.error('Failed to save settings:', e);
      return false;
    }
  });
}

// =============================================================================
// App Lifecycle
// =============================================================================

app.whenReady().then(async () => {
  console.log('YouResearch starting...');

  // Start backend first
  await startPythonBackend();

  // Setup IPC
  setupIpcHandlers();

  // Create window
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  stopPythonBackend();
});

app.on('quit', () => {
  stopPythonBackend();
});
