const { spawn } = require('child_process');
const http = require('http');

const MCP_DIR = 'D:\\Codex\\TraderLens';
const PORT = 3000;

// 启动 MCP 服务器进程
const mcpServer = spawn('npx.cmd', ['-y', '@modelcontextprotocol/server-filesystem', MCP_DIR], {
  stdio: ['pipe', 'pipe', 'pipe'],
  shell: true
});

let buffer = '';

mcpServer.stderr.on('data', (data) => {
  console.error('MCP stderr:', data.toString());
});

// 创建 HTTP 服务器
const server = http.createServer((req, res) => {
  if (req.method === 'POST') {
    let body = '';

    req.on('data', chunk => {
      body += chunk.toString();
    });

    req.on('end', () => {
      console.log('Request:', body);

      // 发送到 MCP 服务器
      mcpServer.stdin.write(body + '\n');

      // 读取响应
      const onData = (data) => {
        const response = data.toString();
        console.log('Response:', response);

        res.writeHead(200, {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*'
        });
        res.end(response);

        mcpServer.stdout.removeListener('data', onData);
      };

      mcpServer.stdout.once('data', onData);
    });
  } else if (req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('MCP HTTP Adapter Running\n');
  } else if (req.method === 'OPTIONS') {
    res.writeHead(200, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type'
    });
    res.end();
  }
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`✅ MCP HTTP Adapter running on http://0.0.0.0:${PORT}`);
  console.log(`📁 Directory: ${MCP_DIR}`);
  console.log(`🌐 Access via: https://chatgpt-mcp.illyazhang.top`);
});

process.on('SIGINT', () => {
  console.log('\n🛑 Shutting down...');
  mcpServer.kill();
  server.close();
  process.exit(0);
});
