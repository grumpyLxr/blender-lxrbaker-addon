#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

readonly addon_dir="BlenderLxrBakerAddon"
readonly blender_version="4.5"
readonly blender_addon_dir="${HOME}/.config/blender/${blender_version}/scripts/addons"

for file in ${blender_addon_dir}/${addon_dir}/*.py; do
    [ -e "${file}" ] || continue
    rm -v "${file}"
done
for file in ${addon_dir}/*.py; do
    [ -e "${file}" ] || continue
    cp -v "${file}" "${blender_addon_dir}/${file}"
done
