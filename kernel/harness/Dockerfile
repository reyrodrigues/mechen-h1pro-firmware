# Build environment for the MECHEN H1-Pro (MT6750) Linux 3.18.119 kernel.
# x86_64 image because the matching AOSP GCC 4.9 toolchain only ships x86_64 Linux binaries
# (runs under Rosetta/qemu on Apple Silicon via colima).
FROM --platform=linux/amd64 ubuntu:18.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        bc bison flex make gcc libc6-dev libssl-dev perl python python3 \
        git ca-certificates cpio kmod xz-utils gzip openssl device-tree-compiler \
    && rm -rf /var/lib/apt/lists/*

# Same compiler family as the stock kernel ("gcc version 4.9.x 20150123 (prerelease)").
ARG TC_TAG=android-9.0.0_r61
RUN git clone --depth 1 -b ${TC_TAG} \
        https://android.googlesource.com/platform/prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9 \
        /opt/gcc-aarch64 && rm -rf /opt/gcc-aarch64/.git

ENV PATH=/opt/gcc-aarch64/bin:$PATH \
    ARCH=arm64 \
    CROSS_COMPILE=aarch64-linux-android-

WORKDIR /src
