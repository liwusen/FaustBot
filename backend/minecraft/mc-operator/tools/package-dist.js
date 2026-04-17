const fs = require('fs');
const path = require('path');

const projectRoot = path.resolve(__dirname, '..');
const distRoot = path.join(projectRoot, 'dist', 'faust-mc-operator');
const appRoot = path.join(distRoot, 'app');
const runtimeRoot = path.join(distRoot, 'runtime');
const nodeExeSource = process.execPath;
const nodeExeTarget = path.join(runtimeRoot, path.basename(nodeExeSource));

function removeIfExists(targetPath) {
  if (fs.existsSync(targetPath)) {
    fs.rmSync(targetPath, { recursive: true, force: true });
  }
}

function ensureDir(targetPath) {
  fs.mkdirSync(targetPath, { recursive: true });
}

function copyIntoApp(relativePath) {
  const source = path.join(projectRoot, relativePath);
  const target = path.join(appRoot, relativePath);
  if (!fs.existsSync(source)) {
    throw new Error(`Missing required path: ${source}`);
  }
  fs.cpSync(source, target, { recursive: true });
}

function writeLauncher() {
  const launcherPath = path.join(distRoot, 'mc.bat');
  const launcher = [
    '@echo off',
    'title FAUST Backend Minecraft Operator Service',
    'cd /d "%~dp0"',
    'if exist "%~dp0runtime\\node.exe" (',
    '  "%~dp0runtime\\node.exe" "%~dp0app\\src\\index.js"',
    ') else (',
    '  node "%~dp0app\\src\\index.js"',
    ')',
  ].join('\r\n');
  fs.writeFileSync(launcherPath, launcher + '\r\n', 'utf8');
}

function writeReadme() {
  const readmePath = path.join(distRoot, 'README.txt');
  const lines = [
    'Faust mc-operator 目录版发布包',
    '',
    '启动方式：',
    '1. 双击 mc.bat',
    '2. 或在命令行中运行 runtime\\node.exe app\\src\\index.js',
    '',
    '此目录已包含 Node Runtime，无需系统额外安装 Node.js。',
  ];
  fs.writeFileSync(readmePath, lines.join('\r\n') + '\r\n', 'utf8');
}

function main() {
  console.log('[package-dist] preparing dist directory...');
  removeIfExists(distRoot);
  ensureDir(appRoot);
  ensureDir(runtimeRoot);

  console.log('[package-dist] copying application files...');
  copyIntoApp('src');
  copyIntoApp('node_modules');
  copyIntoApp('package.json');
  if (fs.existsSync(path.join(projectRoot, 'package-lock.json'))) {
    copyIntoApp('package-lock.json');
  }

  console.log(`[package-dist] bundling node runtime from ${nodeExeSource}`);
  fs.copyFileSync(nodeExeSource, nodeExeTarget);

  console.log('[package-dist] writing launcher...');
  writeLauncher();
  writeReadme();

  console.log(`[package-dist] done: ${distRoot}`);
}

main();