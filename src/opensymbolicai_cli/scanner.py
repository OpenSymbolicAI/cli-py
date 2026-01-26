"""Agent scanner utility to discover PlanExecute subclasses."""

import ast
import json
from pathlib import Path

from pydantic import BaseModel, Field


class DiscoveredMethod(BaseModel):
    """Information about a discovered method."""

    name: str = Field(description="Method name")
    method_type: str = Field(description="Type: 'primitive' or 'decomposition'")
    docstring: str = Field(default="", description="Method docstring")
    signature: str = Field(default="", description="Method signature")
    source: str = Field(default="", description="Full source code of the method")
    line_number: int = Field(default=0, description="Line number in source file")
    read_only: bool = Field(default=False, description="Whether primitive is read-only")
    intent: str = Field(default="", description="Decomposition intent")
    expanded_intent: str = Field(default="", description="Decomposition expanded intent")


class DiscoveredAgent(BaseModel):
    """Information about a discovered agent."""

    name: str = Field(description="Human-readable name of the agent")
    class_name: str = Field(description="Python class name")
    file_path: Path = Field(description="Path to the Python file containing the agent")
    description: str = Field(default="", description="Agent description")
    version: str = Field(default="", description="Agent version")
    base_class: str = Field(
        default="PlanExecute",
        description="Base class: 'PlanExecute' or 'Planner'",
    )
    methods: list[DiscoveredMethod] = Field(
        default_factory=list, description="List of primitive and decomposition methods"
    )


class ManifestMetadata(BaseModel):
    """Metadata extracted from a manifest file."""

    name: str = Field(default="", description="Agent name from manifest")
    description: str = Field(default="", description="Agent description from manifest")
    version: str = Field(default="", description="Agent version from manifest")


def _get_method_signature(func_def: ast.FunctionDef, source_lines: list[str]) -> str:
    """Extract method signature from AST node."""
    start_line = func_def.lineno - 1
    signature_parts = []

    # Collect lines until we find the closing parenthesis and colon
    for i in range(start_line, min(start_line + 10, len(source_lines))):
        line = source_lines[i]
        signature_parts.append(line.rstrip())
        if "):" in line or ") ->" in line:
            break

    signature = "\n".join(signature_parts)
    return signature.strip()


def _get_method_source(func_def: ast.FunctionDef, source_lines: list[str]) -> str:
    """Extract full method source from AST node."""
    start_line = func_def.lineno - 1
    end_line = func_def.end_lineno if func_def.end_lineno else start_line + 1
    return "\n".join(source_lines[start_line:end_line])


def _load_manifest_metadata(file_path: Path, manifest_name: str | None = None) -> ManifestMetadata:
    """Load metadata from a manifest file.

    Args:
        file_path: Path to the Python source file.
        manifest_name: Optional manifest filename. If not provided, uses
            {source_file_stem}.manifest.json.

    Returns:
        ManifestMetadata with name, description, and version from the manifest.
        Returns empty values if manifest doesn't exist or can't be parsed.
    """
    if manifest_name is None:
        manifest_name = f"{file_path.stem}.manifest.json"
    manifest_path = file_path.parent / manifest_name

    if not manifest_path.exists():
        return ManifestMetadata()

    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        return ManifestMetadata(
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", ""),
        )
    except (json.JSONDecodeError, OSError):
        return ManifestMetadata()


def _extract_manifest_filename(class_node: ast.ClassDef) -> str | None:
    """Extract manifest filename from load_manifest() call in __init__.

    Looks for patterns like:
        - load_manifest(__file__)  -> returns None (use default)
        - load_manifest(__file__, "custom.manifest.json") -> returns custom name

    Args:
        class_node: The AST class definition node.

    Returns:
        The manifest filename if explicitly specified, None for default naming.
        Returns empty string if no load_manifest call found.
    """
    for item in ast.walk(class_node):
        if not isinstance(item, ast.Call):
            continue

        # Look for load_manifest(...) calls
        func = item.func
        if isinstance(func, ast.Name) and func.id == "load_manifest":
            # Check if there's a second argument (custom manifest name)
            if len(item.args) >= 2 and isinstance(item.args[1], ast.Constant):
                return str(item.args[1].value)
            # Check for manifest_name keyword argument
            for keyword in item.keywords:
                if keyword.arg == "manifest_name" and isinstance(keyword.value, ast.Constant):
                    return str(keyword.value.value)
            # load_manifest(__file__) with default naming
            return None

    # No load_manifest call found
    return ""


def _extract_decorated_methods(
    class_node: ast.ClassDef, source_lines: list[str]
) -> list[DiscoveredMethod]:
    """Extract @primitive and @decomposition decorated methods from a class."""
    methods: list[DiscoveredMethod] = []

    for item in class_node.body:
        if not isinstance(item, ast.FunctionDef):
            continue

        method_type = None
        read_only = False
        intent = ""
        expanded_intent = ""

        for decorator in item.decorator_list:
            # Handle @primitive or @primitive(read_only=True)
            if isinstance(decorator, ast.Name) and decorator.id == "primitive":
                method_type = "primitive"
            elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
                if decorator.func.id == "primitive":
                    method_type = "primitive"
                    # Check for read_only argument
                    for keyword in decorator.keywords:
                        if keyword.arg == "read_only" and isinstance(keyword.value, ast.Constant):
                            read_only = bool(keyword.value.value)
                elif decorator.func.id == "decomposition":
                    method_type = "decomposition"
                    # Extract intent and expanded_intent from decorator
                    if len(decorator.args) >= 1 and isinstance(decorator.args[0], ast.Constant):
                        intent = str(decorator.args[0].value)
                    for keyword in decorator.keywords:
                        if keyword.arg == "intent" and isinstance(keyword.value, ast.Constant):
                            intent = str(keyword.value.value)
                        elif keyword.arg == "expanded_intent" and isinstance(
                            keyword.value, ast.Constant
                        ):
                            expanded_intent = str(keyword.value.value)

        if method_type:
            docstring = ast.get_docstring(item) or ""
            methods.append(
                DiscoveredMethod(
                    name=item.name,
                    method_type=method_type,
                    docstring=docstring,
                    signature=_get_method_signature(item, source_lines),
                    source=_get_method_source(item, source_lines),
                    line_number=item.lineno,
                    read_only=read_only,
                    intent=intent,
                    expanded_intent=expanded_intent,
                )
            )

    return methods


def _extract_agent_info_from_ast(file_path: Path) -> list[DiscoveredAgent]:
    """Extract agent information using AST parsing.

    Args:
        file_path: Path to the Python file to analyze.

    Returns:
        List of discovered agents in the file.
    """
    agents: list[DiscoveredAgent] = []

    try:
        source = file_path.read_text(encoding="utf-8")
        source_lines = source.splitlines()
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, OSError):
        return agents

    # Valid base class names for PlanExecute agents
    valid_base_names = {"PlanExecute", "Planner"}

    for class_node in ast.walk(tree):
        if not isinstance(class_node, ast.ClassDef):
            continue

        # Check if class inherits from PlanExecute or Planner
        base_class_name = None
        for base in class_node.bases:
            if isinstance(base, ast.Name) and base.id in valid_base_names:
                base_class_name = base.id
                break
            if isinstance(base, ast.Attribute) and base.attr in valid_base_names:
                base_class_name = base.attr
                break

        if not base_class_name:
            continue

        # Extract class name
        class_name = class_node.name

        # Try to extract name, description, and version from __init__ super().__init__ call
        name = class_name
        description = ""
        version = ""

        for item in ast.walk(class_node):
            if isinstance(item, ast.Call):
                # Look for super().__init__(...) calls
                func = item.func
                if isinstance(func, ast.Attribute) and func.attr == "__init__":
                    for keyword in item.keywords:
                        if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                            name = str(keyword.value.value)
                        elif keyword.arg == "description" and isinstance(
                            keyword.value, ast.Constant
                        ):
                            description = str(keyword.value.value)
                        elif keyword.arg == "version" and isinstance(keyword.value, ast.Constant):
                            version = str(keyword.value.value)

        # Try to load metadata from manifest file if load_manifest() is used
        manifest_filename = _extract_manifest_filename(class_node)
        if manifest_filename != "":  # Empty string means no load_manifest call
            manifest_meta = _load_manifest_metadata(file_path, manifest_filename)
            if manifest_meta.name:
                name = manifest_meta.name
            if manifest_meta.description:
                description = manifest_meta.description
            if manifest_meta.version:
                version = manifest_meta.version

        # Also try to get description from class docstring
        if not description and ast.get_docstring(class_node):
            docstring = ast.get_docstring(class_node)
            if docstring:
                # Use first line of docstring
                description = docstring.split("\n")[0].strip()

        # Extract decorated methods
        methods = _extract_decorated_methods(class_node, source_lines)

        agents.append(
            DiscoveredAgent(
                name=name,
                class_name=class_name,
                file_path=file_path,
                description=description,
                version=version,
                base_class=base_class_name,
                methods=methods,
            )
        )

    return agents


def scan_directory_for_agents(directory: Path) -> list[DiscoveredAgent]:
    """Scan a directory for Python files containing PlanExecute/Planner subclasses.

    Args:
        directory: The directory to scan.

    Returns:
        List of discovered agents.
    """
    if not directory.exists() or not directory.is_dir():
        return []

    agents = []

    for py_file in directory.rglob("*.py"):
        # Skip __pycache__ directories
        if "__pycache__" in py_file.parts:
            continue

        discovered = _extract_agent_info_from_ast(py_file)
        agents.extend(discovered)

    return agents


def scan_file_for_agents(file_path: Path) -> list[DiscoveredAgent]:
    """Scan a single Python file for PlanExecute/Planner subclasses.

    Args:
        file_path: Path to the Python file to scan.

    Returns:
        List of discovered agents in the file.
    """
    if not file_path.exists() or not file_path.is_file():
        return []

    return _extract_agent_info_from_ast(file_path)
