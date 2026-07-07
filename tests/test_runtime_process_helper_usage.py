import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _module_tree(relative_path: str) -> ast.Module:
    return ast.parse((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))


def _function_names(tree: ast.Module) -> set[str]:
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def _imports_runtime_helpers(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "scripts.runtime_process_helpers":
            return True
    return False


def test_p3_runtime_verifiers_use_shared_process_helpers():
    """
    Startup stability is only real if every P3 browser verifier uses the same
    port release and process ownership checks instead of local copies.
    """
    for script in [
        "scripts/verify_p3_2_strategy_result_visibility.py",
        "scripts/verify_p3_3_strategy_rejection_registry.py",
    ]:
        tree = _module_tree(script)

        assert _imports_runtime_helpers(tree), f"{script} must import runtime_process_helpers"

        local_functions = _function_names(tree)
        assert "release_port" not in local_functions, f"{script} must not define local release_port"
        assert "kill_port" not in local_functions, f"{script} must not define local kill_port"
        assert "start_backend" not in local_functions, f"{script} must not define local start_backend"
        assert "start_frontend" not in local_functions, f"{script} must not define local start_frontend"

