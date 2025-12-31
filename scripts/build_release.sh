#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status.

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting Build & Test Process...${NC}"

# 1. Code Quality Checks
echo -e "\n${YELLOW}[1/4] Running Code Quality Checks...${NC}"

echo "Running ruff format..."
ruff format .

echo "Running ruff check..."
ruff check .

echo "Running mypy..."
mypy .

echo "Running pytest..."
pytest

echo -e "${GREEN}✓ All quality checks passed!${NC}"

# 2. Clean previous builds
echo -e "\n${YELLOW}[2/4] Cleaning previous build artifacts...${NC}"
rm -rf dist/ build/ *.egg-info
echo -e "${GREEN}✓ Cleaned dist/, build/ and egg-info directories.${NC}"

# 3. Build Distribution
echo -e "\n${YELLOW}[3/4] Building distribution packages...${NC}"
# Check if build tool is installed
if ! python -c "import build" &> /dev/null; then
    echo "Installing build tool..."
    python -m pip install build
fi

python -m build
echo -e "${GREEN}✓ Build complete!${NC}"

# 4. Verify Distribution
echo -e "\n${YELLOW}[4/4] Verifying distribution metadata...${NC}"
# Check if twine is installed
if ! command -v twine &> /dev/null; then
    echo "Installing twine..."
    python -m pip install twine
fi

twine check dist/*
echo -e "${GREEN}✓ Distribution verification passed!${NC}"

echo -e "\n${GREEN}==============================================${NC}"
echo -e "${GREEN}SUCCESS! Artifacts are ready in dist/${NC}"
echo -e "${GREEN}==============================================${NC}"
echo -e "To upload to PyPI, run: twine upload dist/*"
