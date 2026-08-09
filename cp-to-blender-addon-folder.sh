#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

# This script copies the LxrBaker addon to the user's local blender folder and thus installs the addon.
# After you have executed the script you still have to enalbe the addon in Blender.
# Go to Preferences -> Add-ons and enable LxrBaker

readonly addon_dir="BlenderLxrBakerAddon"
readonly blender_version="5.2"
readonly blender_addon_dir="${HOME}/.config/blender/${blender_version}/scripts/addons"

for file in ${blender_addon_dir}/${addon_dir}/*.py; do
    [ -e "${file}" ] || continue
    rm -v "${file}"
done
mkdir -p "${blender_addon_dir}/${addon_dir}"
for file in ${addon_dir}/*.py; do
    [ -e "${file}" ] || continue
    cp -v "${file}" "${blender_addon_dir}/${file}"
done
