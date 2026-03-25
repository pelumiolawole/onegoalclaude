cat > TODO_SWEEP.md << 'EOF'
# Claude Code — Project Sweep Instructions

You are being asked to conduct a full audit of this codebase.

## Your task

Read every file in this repository and produce a structured report covering:

### 1. What has been fully built and is working
List every feature, endpoint, component, and system that appears complete and functional.

### 2. What is partially built / halfway done
List every file, function, or feature that exists but appears incomplete — missing logic, 
TODO comments, placeholder returns, empty functions, unconnected components, or dead imports.

### 3. What is referenced but does not exist
List any imports, function calls, or references to files/modules that cannot be found 
in the codebase.

### 4. What exists but appears unused / orphaned
List any files, functions, or components that are defined but never imported or called.

### 5. Known issues visible in code
List any obvious bugs, deprecated patterns, hardcoded values that should be env vars,
or dangerous patterns (e.g. no error handling on critical paths).

### 6. Full file tree
Produce a complete annotated file tree of the project.

### 7. Environment variables
List every env var referenced across the codebase (frontend and backend).

## Output format
Produce a markdown file. Be exhaustive. Do not summarise — list everything you find.
Save your output to: docs/CODEBASE_AUDIT.md
EOF