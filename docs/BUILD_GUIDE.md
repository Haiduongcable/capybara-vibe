# Cross-Platform Build Guide

This guide explains how to build Capybara Vibe binaries for multiple platforms using GitHub Actions.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Build Outputs](#build-outputs)
- [Triggering Builds](#triggering-builds)
- [Downloading Artifacts](#downloading-artifacts)
- [Local Development Builds](#local-development-builds)
- [Troubleshooting](#troubleshooting)

---

## Overview

Capybara Vibe uses **GitHub Actions** to automatically build binaries for multiple platforms:

- **Linux** (x86_64): Binary + .deb + .rpm packages
- **macOS** (ARM64/Intel): Native binary
- **Windows** (x64): .exe executable

**Benefits:**
- ✅ No need for multiple machines or VMs
- ✅ Free for public repositories (2000 minutes/month)
- ✅ Builds run in parallel (faster)
- ✅ Automated release creation
- ✅ Consistent build environment

---

## Prerequisites

1. **Git repository** pushed to GitHub
2. **GitHub account** with repository access
3. **Git** installed locally
4. **Proper permissions** to create tags and releases

---

## Build Outputs

### Platform-Specific Artifacts

| Platform | Output Files | Size (approx) | Use Case |
|----------|-------------|---------------|----------|
| **Linux** | `capybara` | ~150MB | Direct binary execution |
| **Linux** | `capybara-vibe_*.deb` | ~150MB | Debian/Ubuntu installation |
| **Linux** | `capybara-vibe_*.rpm` | ~150MB | Fedora/RHEL/CentOS installation |
| **macOS** | `capybara` | ~150MB | Direct binary execution |
| **Windows** | `capybara.exe` | ~150MB | Direct executable |

### Installation Methods by Platform

**Debian/Ubuntu (.deb):**
```bash
sudo dpkg -i capybara-vibe_0.2.1_amd64.deb
capybara --version
```

**Fedora/RHEL/CentOS (.rpm):**
```bash
sudo rpm -i capybara-vibe-0.2.1-1.x86_64.rpm
capybara --version
```

**macOS/Linux (Binary):**
```bash
chmod +x capybara
./capybara --version
# Optional: Move to PATH
sudo mv capybara /usr/local/bin/
```

**Windows (.exe):**
```powershell
# Double-click or run from PowerShell
.\capybara.exe --version
```

---

## Triggering Builds

### Method 1: Create a Release Tag (Recommended)

This triggers a **full release** with all platforms built and a GitHub Release created.

```bash
# 1. Ensure you're on the main/master branch
git checkout master
git pull origin master

# 2. Create a version tag (use semantic versioning)
git tag v0.2.1

# 3. Push the tag to GitHub
git push origin v0.2.1
```

**What happens:**
1. GitHub Actions starts building on 3 runners in parallel
2. Linux runner builds: binary + .deb + .rpm
3. macOS runner builds: macOS binary
4. Windows runner builds: .exe
5. All artifacts are uploaded
6. A GitHub Release is created with all files attached

**Timeline:** ~15-20 minutes for all platforms

### Method 2: Push to Main Branch

This builds binaries but **does not create a release**.

```bash
git add .
git commit -m "your commit message"
git push origin master
```

**What happens:**
- All 3 platforms build
- Artifacts are uploaded to GitHub Actions (but not released)
- No GitHub Release is created

**Use case:** Testing builds before making a release

### Method 3: Manual Workflow Dispatch

Trigger builds manually from GitHub UI.

**Steps:**
1. Go to your repository on GitHub
2. Click **Actions** tab
3. Select **Build and Release** workflow
4. Click **Run workflow** button
5. Select branch (e.g., `master`)
6. Click **Run workflow**

**What happens:**
- Same as Method 2 (builds but no release)
- Useful for testing or rebuilding

---

## Downloading Artifacts

### From GitHub Releases (for tagged builds)

1. Go to: `https://github.com/Haiduongcable/CapybaraVibeCLI/releases`
2. Find your release (e.g., `v0.2.1`)
3. Download the file for your platform:
   - Linux users: `.deb` or `.rpm` or `capybara` (Linux binary)
   - macOS users: `capybara` (macOS binary)
   - Windows users: `capybara.exe`

### From GitHub Actions (for non-tagged builds)

1. Go to: `https://github.com/Haiduongcable/CapybaraVibeCLI/actions`
2. Click on the workflow run
3. Scroll down to **Artifacts** section
4. Download:
   - `linux-artifacts.zip` - Contains binary, .deb, .rpm
   - `mac-artifacts.zip` - Contains macOS binary
   - `windows-artifacts.zip` - Contains .exe

**Note:** GitHub Actions artifacts expire after 90 days

---

## Local Development Builds

### macOS (Your Current Platform)

```bash
# Install PyInstaller
pip install pyinstaller

# Build binary
bash scripts/package_binaries.sh

# Test binary
./dist/capybara --version
```

**Output:** `dist/capybara` (macOS ARM64 binary)

**Limitations:**
- ⚠️ Cannot build .deb/.rpm on macOS
- ⚠️ Cannot build .exe on macOS
- ⚠️ macOS binary only works on macOS

### Linux (using Docker)

If you want to build Linux packages locally:

```bash
# Pull Ubuntu Docker image
docker pull ubuntu:22.04

# Run container with project mounted
docker run -it -v $(pwd):/workspace ubuntu:22.04 bash

# Inside container:
cd /workspace
apt-get update
apt-get install -y python3 python3-pip ruby ruby-dev build-essential
pip3 install .
pip3 install pyinstaller
gem install fpm

# Build
pyinstaller capybara.spec --clean --noconfirm
./dist/capybara --version

# Create .deb
VERSION=0.2.1
mkdir -p package/usr/local/bin
cp dist/capybara package/usr/local/bin/
fpm -s dir -t deb \
  -n capybara-vibe \
  -v ${VERSION} \
  -a amd64 \
  -m "Your Name <your.email@example.com>" \
  --url "https://github.com/Haiduongcable/CapybaraVibeCLI" \
  --description "Multi-Agent AI CLI Coding Assistant" \
  package/usr/local/bin/capybara=/usr/local/bin/capybara
```

### Windows (requires Windows machine/VM)

**Not recommended** - use GitHub Actions instead.

If you must build locally on Windows:

```powershell
# Install Python and pip
# Install PyInstaller
pip install pyinstaller

# Build
pyinstaller capybara.spec --clean --noconfirm

# Test
.\dist\capybara.exe --version
```

---

## Troubleshooting

### Build Fails on GitHub Actions

**Check the logs:**
1. Go to Actions tab
2. Click on failed workflow run
3. Click on failed job (e.g., `build-linux`)
4. Review error messages

**Common issues:**

#### Qt Bindings Error
```
ERROR: Aborting build process due to attempt to collect multiple Qt bindings
```

**Solution:** Already fixed in `capybara.spec` with Qt exclusions.

#### Missing Dependencies
```
ModuleNotFoundError: No module named 'litellm'
```

**Solution:** Ensure all dependencies are in `pyproject.toml` dependencies list.

#### Binary Won't Run
```
./dist/capybara: Permission denied
```

**Solution:**
```bash
chmod +x dist/capybara
```

### GitHub Release Fails with 403 Error

**Symptom:** Release job fails with error:
```
⚠️ GitHub release failed with status: 403 undefined
Error: Too many retries
```

**Cause:** The `GITHUB_TOKEN` lacks `contents: write` permission

**Solution:** Add permissions to the `release` job in `.github/workflows/deploy.yml`:

```yaml
release:
  needs: [build-linux, build-mac, build-windows]
  if: startsWith(github.ref, 'refs/tags/v')
  runs-on: ubuntu-latest
  permissions:
    contents: write  # ← Add this line
  steps:
    # ... rest of the job
```

**Alternative:** Go to GitHub → Settings → Actions → General → Workflow permissions → Select "Read and write permissions"

**Note:** The fix above is already applied to this repository.

### GitHub Release Not Created

**Symptom:** Build succeeds but no release appears

**Cause:** Only tag pushes create releases (not branch pushes)

**Solution:**
```bash
# Create and push a tag
git tag v0.2.1
git push origin v0.2.1
```

### Artifact Download Issues

**Symptom:** Cannot find artifacts after build

**For tagged builds:**
- Check: `https://github.com/Haiduongcable/CapybaraVibeCLI/releases`

**For non-tagged builds:**
- Go to Actions → Click workflow run → Scroll to Artifacts section

### Binary Size Too Large

**Current size:** ~150MB per binary (due to bundled dependencies)

**Why so large:**
- PyInstaller bundles entire Python runtime
- All dependencies included (litellm, pydantic, rich, etc.)
- Scientific libraries (numpy, scipy) from transitive dependencies

**Solutions to reduce size:**

1. **Exclude unused packages** (already done for Qt, matplotlib)
2. **Use UPX compression** (add `upx=True` in capybara.spec - may break on some platforms)
3. **Strip debug symbols** (add `strip=True` in capybara.spec)

**Example optimization:**
```python
# In capybara.spec, modify EXE section:
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='capybara',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,        # ← Strip debug symbols
    upx=True,          # ← Compress with UPX (test thoroughly!)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
)
```

⚠️ **Warning:** Test thoroughly after enabling UPX - it can break binaries on some systems.

---

## Workflow Configuration

The build workflow is defined in `.github/workflows/deploy.yml`.

### Key Configuration Points

**Triggers:**
```yaml
on:
  push:
    tags:
      - 'v*'         # Trigger on version tags (v0.2.1, v1.0.0, etc.)
    branches:
      - main         # Also trigger on main branch pushes
  workflow_dispatch: # Allow manual triggering
```

**Python Version:**
```yaml
python-version: "3.10"  # Can be changed to 3.11, 3.12, 3.13
```

**Caching:**
```yaml
cache: 'pip'  # Speeds up builds by caching pip packages
```

### Customizing the Workflow

To modify build behavior, edit `.github/workflows/deploy.yml`:

**Example: Change Python version to 3.11:**
```yaml
- name: Set up Python
  uses: actions/setup-python@v4
  with:
    python-version: "3.11"  # ← Change here
    cache: 'pip'
```

**Example: Add custom build steps:**
```yaml
- name: Run Tests Before Build
  run: |
    pip install pytest
    pytest tests/
```

---

## Best Practices

### Version Numbering

Use [Semantic Versioning](https://semver.org/):
- **MAJOR.MINOR.PATCH** (e.g., v1.2.3)
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

### Release Checklist

Before creating a release:

- [ ] All tests pass locally
- [ ] Version bumped in `pyproject.toml`
- [ ] CHANGELOG.md updated
- [ ] Documentation updated
- [ ] Commit all changes
- [ ] Create and push tag
- [ ] Monitor GitHub Actions build
- [ ] Test downloaded artifacts
- [ ] Update release notes if needed

### Testing Pre-Release Builds

**Use pre-release tags for testing:**
```bash
git tag v0.2.1-beta.1
git push origin v0.2.1-beta.1
```

Mark as pre-release on GitHub:
1. Go to Releases
2. Edit the release
3. Check "This is a pre-release"
4. Save

---

## Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [PyInstaller Documentation](https://pyinstaller.org/en/stable/)
- [FPM (Package Builder)](https://github.com/jordansissel/fpm)
- [Semantic Versioning](https://semver.org/)

---

## Support

**Issues with builds?**
1. Check workflow logs in GitHub Actions
2. Review this guide's Troubleshooting section
3. Open an issue: `https://github.com/Haiduongcable/CapybaraVibeCLI/issues`

---

## Quick Reference

```bash
# Create a release
git tag v0.2.1
git push origin v0.2.1

# Build locally (macOS/Linux)
bash scripts/package_binaries.sh

# Check workflow status
# Visit: https://github.com/Haiduongcable/CapybaraVibeCLI/actions

# Download releases
# Visit: https://github.com/Haiduongcable/CapybaraVibeCLI/releases
```
