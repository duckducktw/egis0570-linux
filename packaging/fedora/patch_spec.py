#!/usr/bin/env python3
"""Add the egis0570touch patches + OpenCV to Fedora's libfprint.spec (in place)."""
import re, sys
p = sys.argv[1]
s = open(p).read()
if 'egis0570touch' in s:
    sys.exit(0)
patches = ['0001-egis0570-pixman.patch', '0002-egis0570-touch.patch',
           '0003-egis0570-verify-early-exit.patch', '0004-egis0570-touch-cleanup.patch',
           '0005-egis0570touch-ncc-multiframe-adaptive.patch',
           '0006-tests-drop-legacy-egis0570-0570-replay.patch',
           '0007-egis0570touch-opencv5-geometry-include.patch',
           '0008-egis0570touch-faster-verify.patch']
lines = ''.join('Patch%d:         %s\n' % (100 + i, n) for i, n in enumerate(patches))
s = re.sub(r'(Source0:[^\n]*\n)', r'\1\n# egis0570touch: https://github.com/duckducktw/egis0570-linux\n' + lines.replace('\\', '\\\\'), s, count=1)
s = s.replace('BuildRequires:  libgudev-devel\n',
              'BuildRequires:  libgudev-devel\nBuildRequires:  opencv-devel\n', 1)
s = re.sub(r'^(Release:\s*)%autorelease', r'\1%autorelease -e egis1', s, count=1, flags=re.M)
open(p, 'w').write(s)
print('spec patched')
