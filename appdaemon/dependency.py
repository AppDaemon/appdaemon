import ast
import logging
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("AppDaemon._app_management")


def get_full_module_name(file_path: Path) -> str:
    """Get the full module name of a single file by iterating backwards through its parents looking for __init__.py files.

    Args:
        file_path (Path): _description_

    Returns:
        Full module name, delimited with periods
    """
    file_path = file_path if isinstance(file_path, Path) else Path(file_path)
    # assert file_path.is_file(), f"{file_path} is not a file"
    assert file_path.suffix == ".py", f"{file_path} is not a Python file"

    def _gen():
        if file_path.name != "__init__.py":
            yield file_path.stem
        for parent in file_path.parents:
            if (parent / "__init__.py").exists():
                yield parent.name
            else:
                break

    parts = list(_gen())[::-1]
    return ".".join(parts)


def resolve_relative_import(node: ast.ImportFrom, path: Path):
    assert isinstance(node, ast.ImportFrom)
    path = path if isinstance(path, Path) else Path(path)

    full_module_name = get_full_module_name(path)
    parts = full_module_name.split(".")

    if node.level:
        levels_to_remove = node.level
        if path.name == "__init__.py":
            levels_to_remove -= 1
        for _ in range(levels_to_remove):
            parts.pop(-1)
    else:
        parts = node.module.split(".")

    if node.module:
        parts.append(node.module)

    res = ".".join(parts)
    # assert res in sys.modules
    return res


class DependencyResolutionFail(Exception):
    base_exception: Exception

    def __init__(self, base_exception: Exception, *args: object) -> None:
        super().__init__(*args)
        self.base_exception = base_exception


def get_file_deps(file_path: Path) -> set[str]:
    """Parses the content of the Python file to find which modules and/or packages it imports.

    Args:
        file_path (Path): Path to the Python file to parse

    Returns:
        Set of importable module names that this file depends on
    """
    file_path = file_path if isinstance(file_path, Path) else Path(file_path)

    with file_path.open("r") as file:
        file_content = file.read()

    def gen_modules():
        try:
            tree = ast.parse(file_content, filename=file_path)
        except Exception as e:
            logger.error(f"{e}")
        else:
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    yield from (alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        abs_module = resolve_relative_import(node, file_path)
                        yield abs_module
                    else:
                        yield node.module

    return set(gen_modules())


def get_dependency_graph(files: Iterable[Path]):
    graph = {get_full_module_name(f): get_file_deps(f) for f in files}

    for mod, deps in graph.items():
        if mod in deps:
            deps.remove(mod)

    return graph


def get_all_nodes(deps: dict[str, set[str]]) -> set[str]:
    """Retrieve all unique nodes present in the graph, whether they appear as keys (nodes)
    or values (edges).

    Args:
        deps (dict[str, set[str]]): A dictionary representing the graph where keys are node names and values are sets of dependent node names.

    Returns:
        A set containing all unique nodes in the graph.
    """

    def _gen():
        for node, node_deps in deps.items():
            yield node
            if node_deps:
                yield from node_deps

    return set(_gen())


def reverse_graph(graph: dict[str, set[str]]) -> dict[str, set[str]]:
    """Reverse the direction of edges in the given graph.

    Args:
        graph (Graph): A dictionary representing the graph where keys are node names and values are sets of dependent node names.

    Returns:
        Graph: A new graph with the direction of all edges reversed.
    """
    reversed_graph = {n: set() for n in get_all_nodes(graph)}

    for module, dependencies in graph.items():
        if dependencies:
            for dependency in dependencies:
                reversed_graph[dependency].add(module)

    return reversed_graph


def find_all_dependents(
    base_nodes: Iterable[str], reversed_deps: dict[str, set[str]], visited: set[str] = None
) -> set[str]:
    """Recursively find all nodes that depend on the specified base nodes.

    Args:
        base_nodes (Iterable[str]): A list or set of base node names to start the search from.
        reversed_deps (Graph): A dictionary representing the reversed graph where keys are node names and values are sets of nodes that depend on the key node.
        visited (set[str], optional): A set of nodes that have already been visited. Defaults to None.

    Returns:
        A set of all nodes that depend on the base nodes either directly or indirectly.
    """
    base_nodes = [base_nodes] if isinstance(base_nodes, str) else base_nodes
    visited = visited or set()

    for base_node in base_nodes:
        if base_node not in reversed_deps:
            continue

        for dependent in reversed_deps[base_node]:
            if dependent not in visited:
                visited.add(dependent)
                find_all_dependents([dependent], reversed_deps, visited)

    return visited


class CircularDependency(Exception):
    pass


def topo_sort(graph: dict[str, set[str]]) -> list[str]:
    """Topological sort

    Args:
        graph (Mapping[str, set[str]]): Dependency graph

    Raises:
        CircularDependency: Raised if a cycle is detected

    Returns:
        list[str]: Ordered list of the nodes
    """
    visited = list()
    stack = list()
    rec_stack = set()  # Set to track nodes in the current recursion stack
    cycle_detected = False  # Flag to indicate cycle detection

    def _node_gen():
        for node, edges in graph.items():
            yield node
            if edges:
                yield from edges

    nodes = set(_node_gen())

    def visit(node: str):
        nonlocal cycle_detected
        if node in rec_stack:
            cycle_detected = True
            return
        elif node in visited:
            return

        visited.append(node)
        rec_stack.add(node)

        adjacent_nodes = graph.get(node) or set()
        for adj_node in adjacent_nodes:
            visit(adj_node)

        rec_stack.remove(node)
        stack.append(node)

    for node in nodes:
        if node not in visited:
            visit(node)
            if cycle_detected:
                raise CircularDependency(f"Visited {visited} already and was going visit {node} again")

    return stack
