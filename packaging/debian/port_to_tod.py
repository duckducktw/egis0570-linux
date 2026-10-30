#!/usr/bin/env python3
"""Port egis0570touch onto Ubuntu's libfprint "+tod" source tree.

Ubuntu/Debian ship libfprint from the Ubuntu "tod" branch (1.95.x+tod1). Its
meson layout differs from upstream, so patches 0001-0005 do not apply there.
The driver sources apply unchanged; only build glue and hwdb are re-done here.

usage: port_to_tod.py <patched-upstream-tree> <tod-tree>
"""
import os, re, shutil, sys

UP, TOD = sys.argv[1], sys.argv[2]

NEW_FILES = [
    'libfprint/drivers/egis0570touch.c',
    'libfprint/drivers/egis0570touch-match.cpp',
    'libfprint/drivers/egis0570touch-match.h',
    'libfprint/drivers/egis0570touch-proto.h',
    'tests/test-egis0570touch.cpp',
    'tests/test-egis0570touch-driver.c',
]
# egis0570.c is byte-identical between upstream and tod, so take it as patched
COPY_FILES = NEW_FILES + ['libfprint/drivers/egis0570.c']


def edit(path, fn):
    p = os.path.join(TOD, path)
    s = open(p).read()
    t = fn(s)
    if t == s:
        sys.exit('no change applied to ' + path)
    open(p, 'w').write(t)


def once(s, old, new):
    if s.count(old) != 1:
        sys.exit('anchor not unique/found: %r' % old[:60])
    return s.replace(old, new, 1)


for f in COPY_FILES:
    shutil.copy(os.path.join(UP, f), os.path.join(TOD, f))

# 1) top-level meson.build: driver list + opencv helper mapping + dependency
def top(s):
    s = once(s, "    'egis0570',\n    'egismoc',\n    'egis_etu905',\n    'vcom5s',",
             "    'egis0570',\n    'egis0570touch',\n    'egismoc',\n    'egis_etu905',\n    'vcom5s',")
    s = once(s, "    'aes4000' : [ 'aeslib', 'aes3k' ],\n",
             "    'aes4000' : [ 'aeslib', 'aes3k' ],\n    'egis0570touch' : [ 'egis-touch-opencv' ],\n")
    s = once(s, "    if i == 'aes3k'\n",
             "    if i == 'egis-touch-opencv'\n"
             "        # pkg-config file only ships with the full libopencv-dev; core +\n"
             "        # imgproc headers/libs are enough, so fall back to a direct lookup\n"
             "        opencv = dependency('opencv4', required: false)\n"
             "        if opencv.found()\n"
             "            opencv_inc = opencv.get_variable(pkgconfig: 'includedir')\n"
             "        else\n"
             "            opencv_inc = get_option('prefix') / get_option('includedir') / 'opencv4'\n"
             "        endif\n"
             "        if not cpp.has_header('opencv2/imgproc.hpp', args: ['-I' + opencv_inc])\n"
             "            error('OpenCV (core, imgproc) is required for egis0570touch')\n"
             "        endif\n"
             "        optional_deps += declare_dependency(include_directories: include_directories(opencv_inc, is_system: true))\n"
             "        foreach module : ['core', 'imgproc']\n"
             "            optional_deps += cpp.find_library('opencv_' + module)\n"
             "        endforeach\n"
             "    elif i == 'aes3k'\n")
    return s
edit('meson.build', top)

# 2) libfprint/meson.build: sources, helper, C++17
def lib(s):
    s = once(s, "    'egis0570': files('drivers/egis0570.c'),\n",
             "    'egis0570': files('drivers/egis0570.c'),\n"
             "    'egis0570touch': files('drivers/egis0570touch.c', 'drivers/egis0570touch-match.cpp'),\n")
    s = once(s, "    'aes3k': files('drivers/aes3k.c'),\n",
             "    'aes3k': files('drivers/aes3k.c'),\n    'egis-touch-opencv': files(),\n")
    s = once(s, "    c_args: drivers_cflags,\n    dependencies: deps,\n    link_with: libfprint_private,\n",
             "    c_args: drivers_cflags,\n    override_options: ['cpp_std=c++17'],\n"
             "    dependencies: deps,\n    link_with: libfprint_private,\n")
    return s
edit('libfprint/meson.build', lib)

# 3) hwdb: move 0570 into its own block (0571 stays on legacy egis0570)
def hw(s):
    s = once(s, "# Supported by libfprint driver egis0570\nusb:v1C7Ap0570*\nusb:v1C7Ap0571*\n ID_AUTOSUSPEND=1\n ID_PERSIST=0\n",
             "# Supported by libfprint driver egis0570\nusb:v1C7Ap0571*\n ID_AUTOSUSPEND=1\n ID_PERSIST=0\n\n"
             "# Supported by libfprint driver egis0570\nusb:v1C7Ap0570*\n ID_AUTOSUSPEND=1\n ID_PERSIST=0\n")
    return s
edit('data/autosuspend.hwdb', hw)

# 4) tests: unit tests (replay tool needs local captures, not shipped)
def tests(s):
    block = ("\nif 'egis0570touch' in drivers\n"
             "    egis_touch_test = executable('test-egis0570touch',\n"
             "        'test-egis0570touch.cpp',\n"
             "        dependencies: libfprint_private_dep,\n"
             "        link_with: libfprint_drivers,\n"
             "        override_options: ['cpp_std=c++17'])\n"
             "    test('egis0570touch-storage', egis_touch_test, suite: 'unit-tests')\n"
             "    egis_driver_test = executable('test-egis0570touch-driver',\n"
             "        'test-egis0570touch-driver.c',\n"
             "        dependencies: libfprint_private_dep,\n"
             "        link_with: libfprint_drivers)\n"
             "    test('egis0570touch-driver', egis_driver_test, suite: 'unit-tests')\n"
             "endif\n")
    if "egis0570touch" in s:
        return s
    # tests/egis0570 replays a 1c7a:0570 capture through the legacy swipe
    # driver; 0570 is now owned by egis0570touch, so that recording no longer
    # applies (legacy egis0570 keeps 0571 only).
    s = once(s, "    'egis0570',\n    'egismoc',\n", "    'egismoc',\n")
    return s + block
edit('tests/meson.build', tests)
print('ported OK')
