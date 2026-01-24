import subprocess
import multiprocessing
from tqdm import tqdm
import time
import os

ENV_PREFIX = "stress_env_"
ENV_COUNT = 8
PYTHON_VERSION = "3.12"

PACKAGES = ["capybara-vibe"]  # you can add more heavy packages here

def run(cmd):
    return subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def create_env(env):
    run(f"conda create -y -n {env} python={PYTHON_VERSION}")

def install_packages(env):
    pkgs = " ".join(PACKAGES)
    run(
        f"conda run -n {env} python -m pip install --no-cache-dir --force-reinstall {pkgs}"
    )

def remove_env(env):
    run(f"conda remove -y -n {env} --all")

def worker(env):
    install_packages(env)

if __name__ == "__main__":
    envs = [f"{ENV_PREFIX}{i}" for i in range(ENV_COUNT)]

    # print("\n🚀 Creating conda environments...\n")
    # for env in tqdm(envs):
    #     create_env(env)

    # print("\n🔥 Running pip install in parallel...\n")

    # pool = multiprocessing.Pool(processes=ENV_COUNT)

    # list(tqdm(pool.imap_unordered(worker, envs), total=len(envs)))

    # pool.close()
    # pool.join()

    print("\n🧹 Removing conda environments...\n")
    for env in tqdm(envs):
        remove_env(env)

    print("\n✅ DONE. All envs removed.\n")
