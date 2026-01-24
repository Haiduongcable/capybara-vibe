#!/usr/bin/env bash

PKG="capybara-vibe"   # change to any heavy package if you want
LOOPS=1000

CPU_CORES=$(getconf _NPROCESSORS_ONLN)

echo "Using $CPU_CORES CPU cores"

stress_install() {
    while true; do
        python -m pip install --no-cache-dir --force-reinstall $PKG >/dev/null 2>&1
        python -m pip uninstall -y $PKG >/dev/null 2>&1
    done
}

export -f stress_install

for i in $(seq 1 $CPU_CORES); do
    bash -c stress_install &
done

wait
