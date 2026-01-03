#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}Starting Local Binary Build Process...${NC}"

# Check PyInstaller
if ! command -v pyinstaller &> /dev/null; then
    echo "PyInstaller not found. Installing..."
    pip install pyinstaller
fi

# Clean previous builds
echo -e "\n${YELLOW}[1/3] Cleaning previous builds...${NC}"
rm -rf dist/ build/

# Build Binary
echo -e "\n${YELLOW}[2/3] Building Binary with PyInstaller...${NC}"
pyinstaller capybara.spec --clean --noconfirm

# Verify Build
echo -e "\n${YELLOW}[3/3] Verifying Binary...${NC}"
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    ./dist/capybara.exe --version
    echo -e "${GREEN}✓ Windows Binary created at: dist/capybara.exe${NC}"
else
    ./dist/capybara --version
    echo -e "${GREEN}✓ Binary created at: dist/capybara${NC}"
fi

# Linux Packaging (Only works on Linux)
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if command -v fpm &> /dev/null; then
        echo -e "\n${YELLOW}[Optional] Packaging for Linux (.deb, .rpm)...${NC}"
        VERSION=$(./dist/capybara --version | awk '{print $NF}')
        
        # Deb
        fpm -s dir -t deb \
            -n capybara-vibe \
            -v ${VERSION} \
            -a amd64 \
            -m "Hai Duong <haiduong.nguyen2712@gmail.com>" \
            --url "https://github.com/Haiduongcable/CapybaraVibeCLI" \
            --description "Multi-Agent AI CLI Coding Assistant" \
            package/usr/local/bin/capybara=/usr/local/bin/capybara
            
        echo -e "${GREEN}✓ .deb package created${NC}"
        
        # Rpm
        fpm -s dir -t rpm \
            -n capybara-vibe \
            -v ${VERSION} \
            -a x86_64 \
            -m "Hai Duong <haiduong.nguyen2712@gmail.com>" \
            --url "https://github.com/Haiduongcable/CapybaraVibeCLI" \
            --description "Multi-Agent AI CLI Coding Assistant" \
            package/usr/local/bin/capybara=/usr/local/bin/capybara
            
        echo -e "${GREEN}✓ .rpm package created${NC}"
    else
        echo -e "\n${YELLOW}Skipping .deb/.rpm packaging (fpm not installed).${NC}"
        echo "To install fpm: gem install fpm"
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
     echo -e "\n${YELLOW}Note: .deb/.rpm and .exe building is not supported natively on macOS.${NC}"
     echo -e "Use the GitHub Actions workflow (git push tag) to build for all platforms."
fi
