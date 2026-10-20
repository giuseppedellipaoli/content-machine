"""Prepare a user-owned font for libass, or select an installed system family.

FONT_PATH / --font points to a font the user is licensed to use. No font is
downloaded or redistributed. Variable fonts retain the original conversion
to a static weight for libass. Without a path only family.txt is written;
libass resolves the installed system font, with its normal font fallback.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

import _bootstrap

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', default=os.environ.get('FONT_PATH'))
    parser.add_argument('--family', default=os.environ.get('FONT_FAMILY'))
    parser.add_argument('--weight', type=float, default=600)
    args = parser.parse_args()
    destination = ROOT / 'fonts'
    destination.mkdir(exist_ok=True)
    if not args.font:
        family = args.family or ('Arial' if sys.platform == 'win32' else 'DejaVu Sans')
        (destination / 'family.txt').write_text(family, encoding='utf-8')
        print(f'System font: {family}. No font file copied or downloaded.')
        return 0
    source = Path(args.font).expanduser().resolve()
    if not source.is_file():
        parser.error(f'Font not found: {source}')
    from fontTools import ttLib
    from fontTools.varLib import instancer

    font = ttLib.TTFont(source)
    font.flavor = None
    if 'fvar' in font:
        axes = {axis.axisTag: axis for axis in font['fvar'].axes}
        if 'wght' in axes:
            axis = axes['wght']
            weight = max(axis.minValue, min(axis.maxValue, args.weight))
            font = instancer.instantiateVariableFont(font, {'wght': weight})
    family = args.family or font['name'].getDebugName(16) or font['name'].getDebugName(1)
    if not family:
        parser.error('Font has no readable family name; specify --family.')
    suffix = '.otf' if 'CFF ' in font or 'CFF2' in font else '.ttf'
    output = destination / f'user-font{suffix}'
    font.save(output)
    (destination / 'family.txt').write_text(family, encoding='utf-8')
    print(f'Prepared {output.name}; family={family!r}. Keep the original font license.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
