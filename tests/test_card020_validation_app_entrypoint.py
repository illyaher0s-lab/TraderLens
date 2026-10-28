import ast
import subprocess
from pathlib import Path


def test_health_route_is_registered_before_catch_all_research_mount():
    source_path = Path(__file__).resolve().parents[1] / "scripts" / "card020_validation_app.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"))

    health_index = next(
        index for index, node in enumerate(module.body)
        if isinstance(node, ast.FunctionDef)
        and node.name == "health"
        and any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "app"
            and decorator.func.attr == "get"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
            and decorator.args[0].value == "/health"
            for decorator in node.decorator_list
        )
    )
    root_mount_index = next(
        index for index, node in enumerate(module.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "app"
        and node.value.func.attr == "mount"
        and node.value.args
        and isinstance(node.value.args[0], ast.Constant)
        and node.value.args[0].value == "/"
    )

    assert health_index < root_mount_index


def test_validation_launcher_uses_project_env_loader_not_batch_dotenv_parsing():
    project_root = Path(__file__).resolve().parents[1]
    launcher = (project_root / "scripts" / "card020_validation_launcher.cjs").read_text(encoding="utf-8")
    batch = (project_root / "scripts" / "start-card020-validation.bat").read_text(encoding="utf-8")

    assert "loadEnvConfig" in launcher
    assert ":load_env_file" not in batch
    assert "node scripts\\card020_validation_launcher.cjs" in batch


def test_next_config_uses_card020_dist_directory_and_private_tsconfig():
    project_root = Path(__file__).resolve().parents[1]
    script = (
        "process.env.CARD020_NEXT_DIST_DIR='.next-card020-20261027'; "
        "const c=require('./frontend/next.config.js'); "
        "process.stdout.write(JSON.stringify({distDir:c.distDir,tsconfigPath:c.typescript?.tsconfigPath}));"
    )
    result = subprocess.run(
        ["node", "-e", script], cwd=project_root, text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == '{"distDir":".next-card020-20261027","tsconfigPath":"tsconfig.card020.json"}'


def test_launcher_preserves_synthetic_tushare_endpoint_and_proxy_environment():
    project_root = Path(__file__).resolve().parents[1]
    script = r"""
const assert = require('node:assert/strict');
const { configureValidationEnvironment, assertRequiredRealConfiguration } = require('./scripts/card020_validation_launcher.cjs');
const configured = {
  TUSHARE_API_URL: 'https://synthetic.example.invalid/api',
  CARD019_NEXT_DIST_DIR: '.next-card019-20261025',
  HTTP_PROXY: 'http://proxy-a.example.invalid:8080',
  HTTPS_PROXY: 'http://proxy-b.example.invalid:8080',
  ALL_PROXY: 'socks5://proxy-c.example.invalid:1080',
  http_proxy: 'http://proxy-d.example.invalid:8080',
  https_proxy: 'http://proxy-e.example.invalid:8080',
  all_proxy: 'socks5://proxy-f.example.invalid:1080',
};
const original = { ...configured };
configureValidationEnvironment(configured);
for (const [name, value] of Object.entries(original)) assert.equal(configured[name], value);
const missing = { RESEARCH_LLM_API_KEY: 'synthetic-only', TUSHARE_TOKEN: 'synthetic-only' };
configureValidationEnvironment(missing);
assert.equal(Object.hasOwn(missing, 'TUSHARE_API_URL'), false);
assert.equal(Object.hasOwn(missing, 'NEXT_TELEMETRY_DISABLED'), false);
assert.doesNotThrow(() => assertRequiredRealConfiguration(missing));
process.stdout.write('synthetic env preserved');
""";
    node_result = subprocess.run(
        ["node", "-e", script], cwd=project_root, text=True, encoding="utf-8", capture_output=True, check=False,
    )

    assert node_result.returncode == 0, node_result.stderr
    assert node_result.stdout == "synthetic env preserved"
