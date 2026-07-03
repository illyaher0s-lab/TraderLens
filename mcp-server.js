const { spawn } = require('child_process');
const http = require('http');

const MCP_DIR = 'D:\\Codex\\TraderLens';
const PORT = 3002;

console.log('🚀 Starting MCP HTTP Adapter...');
console.log(`📁 Directory: ${MCP_DIR}`);
console.log(`🌐 Port: ${PORT}`);

// 创建简单的 HTTP 服务器
const server = http.createServer(async (req, res) => {
  // 添加 CORS 头
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end();
    return;
  }

  if (req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('MCP HTTP Adapter Running\n');
    return;
  }

  if (req.method === 'POST') {
    let body = '';

    req.on('data', chunk => {
      body += chunk.toString();
    });

    req.on('end', async () => {
      try {
        console.log('📨 Received request:', body.substring(0, 100));

        // 启动 filesystem server 处理请求
        const child = spawn('npx', ['-y', '@modelcontextprotocol/server-filesystem', MCP_DIR], {
          stdio: ['pipe', 'pipe', 'pipe']
        });

        let response = '';
        let errorOutput = '';

        child.stdout.on('data', (data) => {
          response += data.toString();
        });

        child.stderr.on('data', (data) => {
          errorOutput += data.toString();
          console.error('MCP stderr:', data.toString());
        });

        child.on('close', (code) => {
          if (code === 0 && response) {
            console.log('✅ Response received');
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(response);
          } else {
            console.error('❌ MCP process failed:', errorOutput);
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'MCP server error', details: errorOutput }));
          }
        });

        // 发送请求到 MCP server
        child.stdin.write(body + '\n');
        child.stdin.end();

      } catch (error) {
        console.error('❌ Error:', error);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: error.message }));
      }
    });
  } else {
    res.writeHead(405);
    res.end();
  }
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`✅ MCP HTTP Adapter running on http://0.0.0.0:${PORT}`);
  console.log(`🌐 Access via: https://chatgpt-mcp.illyazhang.top`);
  console.log('');
  console.log('Press Ctrl+C to stop');
});

process.on('SIGINT', () => {
  console.log('\n🛑 Shutting down...');
  server.close();
  process.exit(0);
});
