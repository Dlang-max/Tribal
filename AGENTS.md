# Agent guidance

These instructions apply to this repository and its subdirectories.

## Project context

Tribal manages shared context for AI agents within and across repositories.

Before beginning any task, read the relevant notes in the `../UB Hacking 2026/`
Obsidian vault. For now, this vault holds the current context for Tribal.

Keep changes small and practical for the hackathon. Build on existing files
and dependencies, and introduce new infrastructure only when the task needs it.

Do not write tests unless explicitly instructed to do so.

## Code comments

Start every code file with a short description of what the code in that file
implements. For Python, use a module docstring at the top of the file (after a
shebang or encoding declaration, if present).

Include a one-line purpose comment immediately above every Python function
definition, before any decorators. This applies to regular and async functions,
methods, nested helper functions, fixtures, and tests. Describe what the function
does rather than restating its name.

## Repository layout and commits

Use descriptive names for all files and folders.

Place all source code in `src/` and all test code in `tests/`, relative to the
Tribal repository root.

Place all Kubernetes code in `k8s/` and all Docker/container image code in
`docker/`, relative to the Tribal repository root.

Use descriptive branch names and commit titles. Commit messages should clearly
break down what the agent implemented and why.

