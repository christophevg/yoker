#!/bin/bash
# Run yoker with demo plugin
#
# The demo plugin is in examples/plugins/demo which needs to be in the Python path
# This script sets up the environment and runs yoker with the plugin

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Add examples directory to Python path
export PYTHONPATH="${SCRIPT_DIR}/examples${PYTHONPATH:+:$PYTHONPATH}"

# Run yoker with the demo plugin
# Use plugins.demo as the package name (not examples.plugins.demo)
echo "Starting yoker with demo plugin..."
echo "Plugin package: plugins.demo"
echo "PYTHONPATH includes: ${SCRIPT_DIR}/examples"
echo ""
echo "Available skills from demo plugin:"
echo "  - example: A simple example skill for demonstration"
echo "  - sing: Use this skill when asked to sing or reply with a song."
echo ""
echo "Type /skills to see all available skills"
echo ""

uv run yoker --with plugins.demo "$@"