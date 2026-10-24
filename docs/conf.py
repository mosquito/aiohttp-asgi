"""Sphinx configuration for the aiohttp-asgi documentation."""

import sys
from datetime import date
from pathlib import Path


try:
    import tomllib
except ImportError:                                  # pragma: no cover
    import tomli as tomllib                           # type: ignore[no-redef]


# autodoc imports the package, therefore the project root must be importable.
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

with (ROOT / "pyproject.toml").open("rb") as fp:
    pyproject = tomllib.load(fp)

metadata = pyproject["project"]

# -- Project information -----------------------------------------------------

project = metadata["name"]
author = metadata["authors"][0]["name"]
copyright = f"{date.today().year}, {author}"
release = metadata["version"]
version = ".".join(release.split(".")[:2])

# -- General configuration ---------------------------------------------------

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",
    "sphinx_copybutton",
    "sphinx_design",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# GitHub Pages serves the documentation under this address.
html_baseurl = "https://mosquito.github.io/aiohttp-asgi/"

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
]
myst_heading_anchors = 3

# -- Options for HTML output -------------------------------------------------

html_theme = "furo"
html_title = f"{project} {release}"
html_static_path: list = []

html_theme_options = {
    "source_repository": metadata["urls"]["Source"],
    "source_branch": "master",
    "source_directory": "docs/",
    "navigation_with_keys": True,
    "top_of_page_buttons": ["view", "edit"],
}

# -- Extension configuration -------------------------------------------------

autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "show-inheritance": True,
}

autodoc_typehints = "description"
autodoc_typehints_format = "short"

typehints_fully_qualified = False
always_document_param_types = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "aiohttp": ("https://docs.aiohttp.org/en/stable", None),
}

copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_regexp = True
