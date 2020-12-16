# -*- coding: utf-8 -*-
from __future__ import division
import fontforge
import os
import glob
import parse
import base64

def array_ucs(ustr):
    work = []
    for uch in ustr:
        n = ord(uch)
        if n >= 0xDC00 and n <= 0xDFFF:
            p = ord(work[-1])
            if p >= 0xD800 and p <= 0xDBFF:
                work[-1] = (((p & 0x03FF) << 10) | (n & 0x03FF)) + 0x10000
            else:
                raise Exception("surrogate nonpair")
        else:
            work.append(uch)
    return work


fnames = sorted(glob.glob('../generated/characters/char_*.svg'))

characters = []
for fname in fnames:
    # Sample filename: char_L2_P2_x378_y1471_x766_y1734_RQ==?.svg
    
    pattern = 'char_L{line:d}_P{position:d}_x{x0:d}_y{y0:d}_x{x1:d}_y{y1:d}_{b64_str}.svg'
    result = parse.parse(pattern, os.path.basename(fname))
    chars = tuple(array_ucs(base64.b64decode(result['b64_str'].encode()).decode('utf-8')))
    bbox = (result['x0'], result['y0'], result['x1'], result['y1'])
    characters.append([result['line'], result['position'], bbox, fname, chars])


def basic_font():
    font = fontforge.font()
    font.familyname = font.fontname = 'XKCD'
    font.encoding = "UnicodeFull"

    font.version = '1.080';
    font.weight = 'Regular';
    font.fontname = 'xkcdScript'
    font.familyname = 'xkcd Script'
    font.fullname = 'xkcd-Script-Regular'
    font.copyright = 'Copyright (c) ipython/xkcd-font contributors, Creative Commons Attribution-NonCommercial 3.0 License'
    # As per guidelines in https://fontforge.github.io/fontinfo.html, xuid is no longer needed.
    font.uniqueid = -1

    font.em = 1024;
    font.ascent = 768;
    font.descent = 256;

    # We create a ligature lookup table.
    font.addLookup('ligatures', 'gsub_ligature', (), [['liga',
                                                       [['latn',
                                                         ['dflt']]]]])
    font.addLookupSubtable('ligatures', 'liga')

    font.addLookup('contextual', 'gsub_contextchain', (), [['calt',
                                                            [['latn',
                                                              ['dflt']]]]])
    font.addLookup('subst_after_T', 'gsub_single', (), [['ss01',
                                                         [['latn',
                                                           ['dflt']]]]])
    font.addLookupSubtable('subst_after_T', 'ss01')

    font.addLookup('anchors', 'gpos_mark2base', (), [['mark',
                                                      [['latn',
                                                        ['dflt']]]]])
    font.addLookupSubtable('anchors', 'dtop')
    font.addAnchorClass('dtop', 'top')
    font.addLookupSubtable('anchors', 'dbottom')
    font.addAnchorClass('dbottom', 'bottom')
    font.addLookupSubtable('anchors', 'dupperright')
    font.addAnchorClass('dupperright', 'upperright')
    font.addLookupSubtable('anchors', 'dlowerrightend')
    font.addAnchorClass('dlowerrightend', 'lowerrightend')
    font.addLookup('mkmk', 'gpos_mark2mark', (), [['mkmk',
                                                      [['latn',
                                                        ['dflt']]]]], 'anchors')
    font.addLookupSubtable('mkmk', 'dtop1')
    font.addAnchorClass('dtop1', 'top1')

    return font



from contextlib import contextmanager
import tempfile
import shutil
import os
import sys


@contextmanager
def tmp_symlink(fname):
    """
    Create a temporary symlink to a file, so that applications that can't handle
    unicode filenames don't barf (I'm looking at you font-forge)
    
    """
    target = tempfile.mktemp(suffix=os.path.splitext(fname)[1])
    fname = os.path.normpath(os.path.abspath(fname))
    try:
        if os.name == 'nt':
            if sys.version_info.major == 2:
                shutil.copy(fname, target)
            else:
                os.link(fname, target)
        else:
            os.symlink(fname, target)
        yield target
    finally:
        if os.path.exists(target):
            os.remove(target)


def create_char(font, chars, fname):
    if len(chars) == 1:
        # A single unicode character, so I create a character in the font for it.

        # Because I'm using an old & narrow python (<3.5) I need to handle the unicode
        # characters that couldn't be converted to ordinals (so I kept them as integers). 
        if isinstance(chars[0], int):
            c = font.createMappedChar(chars[0])
        else:
            c = font.createMappedChar(ord(chars[0]))
    elif len(chars) >= 3 and chars[1] == '.':
        # variant glyph.
        variant_name = ''.join(chars)
        
        c = font.createChar(-1, variant_name)
    else:
        # Multiple characters - this is a ligature. We need to register this in the
        # ligature lookup table we created. Not all font-handling libraries will do anything
        # with ligatures (e.g. matplotlib doesn't at vn <=2)
        char_names = [charname(char) for char in chars]
        ligature_name = '_'.join(char_names)
        ligature_tuple = tuple([character.encode('ascii') for character in chars])
        ligature_tuple = tuple([character for character in char_names])
        
        c = font.createChar(-1, ligature_name)

        c.addPosSub('liga', ligature_tuple)

    c.clear()
        
    # Use the workaround to have non-unicode filenames.
    with tmp_symlink(fname) as tmp_fname:
        # At last, bring in the SVG image as an outline for this glyph.
        c.importOutlines(tmp_fname)

    return c


baseline_chars = ['a' 'e', 'm', 'A', 'E', 'M', '&', '@', '.', u'‽']
caps_chars = ['S', 'T', 'J', 'k', 't', 'l', 'b', 'd', '1', '2', u'3', u'≪', u'‽', '?', '!']

line_stats = {}
for line, position, bbox, fname, chars in characters:
    if len(chars) == 1:
        this_line = line_stats.setdefault(line, {})
        char = chars[0]
        if char in baseline_chars:
            this_line.setdefault('baseline', []).append(bbox[3])
        if char in caps_chars:
            this_line.setdefault('cap-height', []).append(bbox[1])


def mean(a):
    return sum(a) / len(a)

import psMat

def scale_glyph(c, char_bbox, baseline, cap_height):
    # TODO: The code in this function is convoluted - it can be hugely simplified.
    # Essentially, all this function does is figure out how much
    # space a normal glyph takes, then looks at how much space *this* glyph takes.
    # With that magic ratio in hand, I now look at how much space the glyph *currently*
    # takes, and scale it to the full EM. On second thoughts, this function really does
    # need to be convoluted, so maybe the code isn't *that* bad...
    
    # Get hold of the bounding box information for the imported glyph.
    import_bbox = c.boundingBox()
    import_width, import_height = import_bbox[2] - import_bbox[0], import_bbox[3] - import_bbox[1]
    
    # Note that timportOutlines doesn't guarantee glyphs will be put in any particular location,
    # so translate to the bottom and middle.
    
    target_baseline = c.font.descent
    top = c.font.ascent
    top_ratio = top / (top + target_baseline)
    
    y_base_delta_baseline = char_bbox[3] - baseline
    
    width, height = char_bbox[2] - char_bbox[0], char_bbox[3] - char_bbox[1]

    # This is the scale factor that font forge will have used for normal glyphs...
    scale_factor = (top + target_baseline) / (cap_height - baseline)
    glyph_ratio = (cap_height - baseline) / height
    
    # A nice glyph size, in pixels. NOTE: In pixel space, cap_height is smaller than baseline, so make it positive.
    full_glyph_size = -(cap_height - baseline) / top_ratio
    
    to_canvas_coord_from_px = full_glyph_size / c.font.em
    
    anchor_ratio = (top + target_baseline) / height
    
    # pixel scale factor
    px_sf = (top + target_baseline) / c.font.em
    
    frac_of_full_size = (height / full_glyph_size)
    import_frac_1000 = c.font.em / import_height
    
    t = psMat.scale(frac_of_full_size * import_frac_1000)
    c.transform(t)


large_arm_chars = ['C', 'F', 'J', 'Q', 'T', 'f', 'q', 'r', 'five']
more_large_arm_chars = ['T_T']
large_tail_chars = ['y', 'comma', 'semicolon']
more_large_tail_chars = ['g', 'j']

def translate_glyph(c, char_bbox, cap_height, baseline):
    # Put the glyph in the middle, and move it relative to the baseline.

    # Compute the proportion of the full EM that cap_height - baseline should consume.
    top_ratio = c.font.ascent / (c.font.ascent + c.font.descent)
    
    # In the original pixel coordinate space, compute how big a nice full sized glyph
    # should be.
    full_glyph_size = -(cap_height - baseline) / top_ratio
    
    # We know that the scale of the glyph is now good. But it is probably way off in terms of x & y, so we
    # need to fix up its position.
    glyph_bbox = c.boundingBox()
    # No matter where it is currently, take the glyph to x=0 and a y based on its positioning in
    # the original handwriting sample.
    t = psMat.translate(-glyph_bbox[0], -glyph_bbox[1] + ((baseline - char_bbox[3]) * c.font.em / full_glyph_size))
    c.transform(t)

    # Put horizontal padding around the glyph. I choose a number here that looks reasonable,
    # there are far more sophisticated means of doing this (like looking at the original image,
    # and calculating how much space there should be).
    space = 20
    scaled_width = glyph_bbox[2] - glyph_bbox[0]
    if c.glyphname == 'one':
        c.width = scaled_width + 4 * space
    elif c.glyphname in large_arm_chars:
        c.width = scaled_width
    elif c.glyphname in more_large_arm_chars:
        c.width = scaled_width - 2 * space
    else:
        c.width = scaled_width + 2 * space
    if c.glyphname == 'one':
        t = psMat.translate(3 * space, 0)
    elif c.glyphname == 'f':
        t = psMat.translate(0 * space, 0)
    elif c.glyphname in large_tail_chars:
        t = psMat.translate(-space, 0)
    elif c.glyphname in more_large_tail_chars:
        t = psMat.translate(-3 * space, 0)
    else:
        t = psMat.translate(space, 0)
    c.transform(t)


def weight_glyph(c, stroke_width):
    # Dilate the glyph with bottom keeping.

    c.simplify(1.0)
    c.stroke('circular', stroke_width, 'round', 'round', ('removeinternal',))
    t = psMat.translate(stroke_width / 2, stroke_width / 2)
    c.transform(t)
    c.width = c.width + stroke_width / 2


import math

def rotate_glyph(c, theta=180):
    import_bbox = c.boundingBox()
    
    t = psMat.translate(-(import_bbox[0] + import_bbox[2]) / 2, -(import_bbox[1] + import_bbox[3]) / 2)
    if theta == 180 or theta == -180:
        c.transform(psMat.compose(psMat.compose(t, psMat.scale(-1)), psMat.inverse(t)))
    else:
        c.simplify(1.0)
        c.transform(psMat.compose(psMat.compose(t, psMat.rotate(math.radians(theta))), psMat.inverse(t)))
        c.addExtrema('only_good_rm')


def rotate_and_onto_baseline(c, theta):
    c.simplify(1.0)
    c.transform(psMat.rotate(math.radians(theta)))
    c.addExtrema('only_good_rm')
    _, ymin, _, ymax = c.boundingBox()
    c.transform(psMat.translate(0, -ymin))
    space = 20
    c.left_side_bearing = space
    c.right_side_bearing = 2 * space


def addanchor(font, char):
    c = font.__getitem__(char)
    xmin, ymin, xmax, ymax = c.boundingBox()
    if xmin < 20:
        xmin = 20
    if xmax > c.width - 40:
        xmax = c.width - 40
    if char == 'I':
        ymax = 620
    if char in ['Eacute', 'Ograve', 'Aring']:
        ymax = ymax - 35
    c.addAnchorPoint('top', 'base', (xmin + xmax) / 2, ymax)
    c.addAnchorPoint('bottom', 'base', (xmin + xmax) / 2, ymin)
    if c.glyphname == 'L':
        c.addAnchorPoint('upperright', 'base', xmax - 100, ymax)
    elif c.glyphname == 't':
        c.addAnchorPoint('upperright', 'base', xmax - 80, ymax)
    else:
        c.addAnchorPoint('upperright', 'base', xmax, ymax)
    l45 = c.foreground.dup()
    l45.transform(psMat.scale(2**0.5,2**0.5))
    l45.transform(psMat.rotate(math.radians(-45)))
    yx = l45.yBoundsAtX(-1000, 1000)
    if yx:
        yx = yx[0]
        xymin, xymax = l45.xBoundsAtY(yx-20, yx+20)
        xy = xymin
        c.addAnchorPoint('lowerrightend', 'base', (xy - yx) / 2, (xy + yx) / 2)
    


def getcontours(c, y, below=False):
    if type(c) is fontforge.layer:
        lfrom = c
    else:
        lfrom = c.foreground
    l1 = fontforge.layer()
    l2 = fontforge.layer()
    i = 0
    while i < len(lfrom):
        _, ymin, _, ymax = lfrom[i].boundingBox()
        if (not below) and ymin >= y or below and ymax <= y:
            l1 += lfrom[i]
        else:
            l2 += lfrom[i]
        i = i + 1
    return (l1, l2)


def getaccent(font, src, glyph, comb, scale=1.0, anchorclass='top'):
    csrc = font.__getitem__(src)
    cglyph = font.createMappedChar(glyph)
    cglyph.width = csrc.width
    xmin, _, xmax, _ = csrc.boundingBox()
    ytop = 0
    (lbase, lto) = getcontours(csrc, 540, below=(anchorclass == 'top' or anchorclass == 'upperright'))
    _, ymin, _, ymax = lbase.boundingBox()
    #print(src, ymax)
    if ymax > ytop:
        ytop = ymax
    _, ymin, _, ymax = lto.boundingBox()
    #print(src, 0.2 * ymax + 0.8 * ymin - (65 / scale))
    if 0.2 * ymax + 0.8 * ymin - (65 / scale) > ytop:
        ytop = 0.2 * ymax + 0.8 * ymin - (65 / scale)
    t = psMat.translate(-(xmin + xmax) / 2, -ytop)
    lto.transform(psMat.compose(psMat.compose(t, psMat.scale(scale)), psMat.inverse(t)))
    ccomb = font.createMappedChar(comb)
    ccomb.foreground = lto.dup()
    if src == 'j' or src == 'Emacron' or src == 'Udieresis':
        xmin, _, xmax, _ = ccomb.boundingBox()
    space = 20
    if anchorclass == 'upperright':
        rspace = -2 * space
        _, ymin, _, ymax = ccomb.boundingBox()
        ccomb.addAnchorPoint(anchorclass, 'mark', xmin, ymax)
    elif anchorclass == 'bottom':
        rspace = 2 * space
        _, ymin, _, ymax = ccomb.boundingBox()
        ccomb.addAnchorPoint(anchorclass, 'mark', (xmin + xmax) / 2, ymax)
    else:
        rspace = 2 * space
        ccomb.addAnchorPoint(anchorclass, 'mark', (xmin + xmax) / 2, ytop)
        if anchorclass == 'top':
            ccomb.addAnchorPoint('top1', 'mark', (xmin + xmax) / 2, ytop)
            _, ymin, _, ymax = ccomb.boundingBox()
            if comb in ['gravecomb', 'acutecomb', 'uni030A']:
                ymax = ymax - 35
            ccomb.addAnchorPoint('top1', 'basemark', (xmin + xmax) / 2, ymax)
    t = psMat.translate(-xmax - rspace, 0)
    ccomb.transform(t)
    ccomb.width = 0
    cglyph.foreground = lto
    cglyph.left_side_bearing = space
    cglyph.right_side_bearing = 2 * space


def getbase(cfrom, cto, lowercase=False):
    cto.width = cfrom.width
    xmin, _, xmax, _ = cfrom.boundingBox()
    ytop = 350
    (lto, laccent) = getcontours(cfrom, (420 if lowercase else 540), below=True)
    _, ymin, _, ymax = lto.boundingBox()
    if ymax > ytop:
        ytop = ymax
    if cfrom.glyphname == 'j':
        xmin, _, xmax, _ = laccent.boundingBox()
    cto.foreground = lto
    cto.addAnchorPoint('top', 'base', (xmin + xmax) / 2, ytop)


def makecedilla(font):
    c = font.createMappedChar('cedilla')
    l1 = font.__getitem__('five').foreground.dup()
    l2 = font.__getitem__('plus').foreground.dup()
    l2.transform(psMat.translate(-18, 400))
    l2.exclude(l1)
    (_, l3) = getcontours(l2, 500)
    c.foreground = l3
    c.transform(psMat.translate(0, -560))
    c.transform(psMat.scale(0.6, 0.35))
    c.simplify(1.0)
    c.stroke('circular', 10, 'round', 'round', ('removeinternal',))
    c.simplify(1.0)
    c.stroke('circular', 10, 'round', 'round', ('removeinternal',))
    c.addExtrema('only_good_rm')
    l3 = c.foreground.dup()
    space = 20
    c.left_side_bearing = space
    c.right_side_bearing = 2 * space
    c = font.createMappedChar('uni0327')
    c.foreground = l3
    c.transform(psMat.translate(-120, 0))
    c.addAnchorPoint('bottom', 'mark', 0, 0)
    c.transform(psMat.translate(-210, 0))
    c.width = 0


def makecombslash(font):
    c = font.createMappedChar('uni0337')
    (_, l1) = getcontours(font.__getitem__('percent'), 200)
    (_, l2) = getcontours(l1, 300, below=True)
    c.foreground = l2
    _, ymin, _, ymax = c.boundingBox()
    c.transform(psMat.translate(0, -ymin))
    space = 20
    c.right_side_bearing = 1 * space
    c.transform(psMat.translate(-c.width, 0))
    c = font.createMappedChar('uni0338')
    c.foreground = font.__getitem__('slash').foreground.dup()
    rotate_and_onto_baseline(c, -10)
    c.transform(psMat.translate(-c.width, 0))


def makebreve(font):
    c = font.createMappedChar('breve')
    l1 = font.__getitem__('G').foreground.dup()
    l2 = font.__getitem__('minus').foreground.dup()
    l2.transform(psMat.translate(-100, 0))
    l2.transform(psMat.scale(2, 1))
    l2.exclude(l1)
    (_, l3) = getcontours(l2, 300)
    c.foreground = l3
    c.transform(psMat.scale(0.6, 0.5))
    c.transform(psMat.translate(0, 500))
    c.simplify(1.0)
    c.stroke('circular', 10, 'round', 'round', ('removeinternal',))
    c.simplify(1.0)
    c.stroke('circular', 10, 'round', 'round', ('removeinternal',))
    c.addExtrema('only_good_rm')
    l3 = c.foreground.dup()
    space = 20
    c.left_side_bearing = space
    c.right_side_bearing = 2 * space
    c = font.createMappedChar('uni0306')
    c.foreground = l3
    c.transform(psMat.translate(-140, 0))
    c.addAnchorPoint('top', 'mark', 0, 460)
    c.addAnchorPoint('top1', 'mark', 0, 460)
    _, ymin, _, ymax = c.boundingBox()
    c.addAnchorPoint('top1', 'basemark', 0, ymax)
    c.transform(psMat.translate(-210, 0))
    c.width = 0


def makeogonek(font):
    c = font.createMappedChar('ogonek')
    l1 = font.__getitem__('c').foreground.dup()
    l2 = font.__getitem__('plus').foreground.dup()
    l2.transform(psMat.translate(-18, 250))
    l2.exclude(l1)
    (_, l3) = getcontours(l2, 300)
    c.foreground = l3
    c.transform(psMat.translate(0, -370))
    c.transform(psMat.scale(0.5, 0.5))
    c.simplify(1.0)
    c.stroke('circular', 10, 'round', 'round', ('removeinternal',))
    c.simplify(1.0)
    c.stroke('circular', 10, 'round', 'round', ('removeinternal',))
    c.addExtrema('only_good_rm')
    l3 = c.foreground.dup()
    space = 20
    c.left_side_bearing = space
    c.right_side_bearing = 2 * space
    c = font.createMappedChar('uni0328')
    c.foreground = l3
    c.transform(psMat.translate(-105, 0))
    c.addAnchorPoint('lowerrightend', 'mark', 0, 0)
    c.transform(psMat.translate(-210, 0))
    c.width = 0


import unicodedata

def makeaccented(font, charto):
    if sys.version_info.major == 2:
        ua = unicodedata.decomposition(unichr(fontforge.unicodeFromName(charto))).decode('utf-8').split()
    else:
        ua = unicodedata.decomposition(chr(fontforge.unicodeFromName(charto))).decode('utf-8').split()
    d = {
        'Oslash': ['004F', '0338'],
        'oslash': ['006F', '0337'],
    }
    if charto in d:
        ua = d[charto]
    if len(ua) <= 0:
        return
    if ua[0] == '<compat>':
        return
    if ua[0] == '0069' and (ua[1] in ['0' + format(i, 'X') for i in range(0x300, 0x314+1)]):
        ua[0] = '0131'  # i to dotlessi
    if ua[0] == '006A' and (ua[1] in ['0' + format(i, 'X') for i in range(0x300, 0x314+1)]):
        ua[0] = '0237'  # j to dotlessj
    if ua[1] == '030C' and (ua[0] in ['0064', '004C', '006C', '0074']):
        ua[1] = '0315'  # caron to comma above right
    if ua[1] == '0327' and (ua[0] == '0067'):
        ua[1] = '0312'  # cedilla to turned comma above
    elif ua[1] == '0327' and not (ua[0] in ['0043', '0063', '0045', '0065', '0053', '0073', '0054', '0074']):
        ua[1] = '0326'  # cedilla to comma below
    charbase = fontforge.nameFromUnicode(int(ua[0], base=16))
    characcent = fontforge.nameFromUnicode(int(ua[1], base=16))
    if not font.__contains__(charbase) or not font.__contains__(characcent):
        #print('not match:' + str([charto] + ua))
        return
    c = font.createMappedChar(charto)
    
    c.width = font.__getitem__(charbase).width
    c.addReference(charbase)
    c.appendAccent(characcent)
    # appendAccent don't reproduce unused anchor points.
    ca = font.__getitem__(charbase).anchorPoints
    caa = font.__getitem__(characcent).anchorPoints
    c.anchorPoints = ca
    for i in ca:
        if i[0] == 'top' and i[1] == 'base':
            x1, y1 = i[2:4]
            for j in caa:
                if j[0] == 'top' and j[1] == 'mark':
                    x2, y2 = j[2:4]
                    for k in caa:
                        if k[0] == 'top1' and k[1] == 'basemark':
                            x3, y3 = k[2:4]
                            c.addAnchorPoint('top', 'base', x1-x2+x3, y1-y2+y3)
                            break
                    break
            break
    #
    if charbase == 'dotlessi':
        wadd = c.width
        space = 20
        c.left_side_bearing = space
        c.right_side_bearing = 2 * space
        wadd = c.width - wadd
        font.__getitem__(charbase).addPosSub('sacc', characcent, wadd // 2, 0, wadd, 0, 0, 0, 0, 0)
    if characcent == 'uni0315' and (charto == 'dcaron' or charto == 'lcaron'):
        c.width = c.width + 80
        font.__getitem__(charbase).addPosSub('sacc', 'uni0315', 0, 0, 80, 0, 0, 0, 0, 0)
    


def makedigraph(font, chara, charb, charto, kerning=-120):
    c = font.createMappedChar(charto)
    
    # simulate pasteAppend
    c.width = font.__getitem__(chara).width
    c.addReference(chara)
    pushwidth = c.width + kerning
    c.transform(psMat.translate(-pushwidth, 0))
    c.addReference(charb)
    c.width = font.__getitem__(charb).width
    c.transform(psMat.translate(pushwidth, 0))


def makeaccent(font):
    getaccent(font, 'Ograve', 'grave', 'gravecomb')
    getbase(font.__getitem__('Ograve'), font.createChar(-1, 'O.sc'))
    getaccent(font, 'Udieresis', 'dieresis', 'uni0308')
    getbase(font.__getitem__('Udieresis'), font.createChar(-1, 'U.sc'))
    getaccent(font, 'Aring', 'degree', 'uni030A')
    getbase(font.__getitem__('Aring'), font.createChar(-1, 'A.sc'))
    getaccent(font, 'Eacute', 'acute', 'acutecomb')
    getbase(font.__getitem__('Eacute'), font.createChar(-1, 'E.sc'))
    getaccent(font, 'Emacron', 'macron', 'uni0304')
    font.__getitem__('asciicircum').transform(psMat.translate(0, 100))
    getaccent(font, 'asciicircum', 'circumflex', 'uni0302', scale=0.8)
    rotate_glyph(font.__getitem__('asciicircum'))
    getaccent(font, 'asciicircum', 'caron', 'uni030C', scale=0.8)
    rotate_glyph(font.__getitem__('asciicircum'))
    font.__getitem__('asciicircum').transform(psMat.translate(0, -100))
    font.__getitem__('asciitilde').transform(psMat.translate(0, 200))
    getaccent(font, 'asciitilde', 'tilde', 'tildecomb', scale=0.8)
    font.__getitem__('asciitilde').transform(psMat.translate(0, -200))
    font.__getitem__('minute').transform(psMat.translate(0, -80))
    getaccent(font, 'minute', 'uni02BC', 'uni0315', anchorclass='upperright')
    font.__getitem__('minute').transform(psMat.translate(0, 80))
    getaccent(font, 'Ohungarumlaut', 'hungarumlaut', 'uni030B')
    getaccent(font, 'j', 'dotaccent', 'uni0307')
    rotate_glyph(font.__getitem__('comma'))
    font.__getitem__('comma').transform(psMat.translate(0, 600))
    getaccent(font, 'comma', 'uni02BB', 'uni0312')
    font.__getitem__('comma').transform(psMat.translate(0, -600))
    rotate_glyph(font.__getitem__('comma'))
    getaccent(font, 'comma', 'uni02CF', 'uni0326', anchorclass='bottom')
    font.removeGlyph('uni02CF')  # temporary use
    
    makecedilla(font)
    makecombslash(font)
    makebreve(font)
    makeogonek(font)
    
    getbase(font.__getitem__('i'), font.createMappedChar('dotlessi'), lowercase=True)
    getbase(font.__getitem__('j'), font.createMappedChar('uni0237'), lowercase=True)
    c = font.createMappedChar('longs')
    c.foreground = font.__getitem__('uni0237').foreground.dup()
    rotate_and_onto_baseline(c, 175)
    c = font.createMappedChar('IJ')
    c.width = font.__getitem__('J').width
    c.foreground = font.__getitem__('J').foreground.dup()
    c.transform(psMat.translate(60, 0))
    l = font.__getitem__('dotlessi').foreground.dup()
    l.transform(psMat.compose(psMat.scale(1, 1.4), psMat.translate(-30, 160)))
    c.foreground += l
    for i in range(ord('A'), ord('Z')+1):
        addanchor(font, i)
    for i in range(ord('a'), ord('z')+1):
        addanchor(font, i)
    addanchor(font, 'Udieresis')
    addanchor(font, 'Aring')
    
    font.addLookup('sideaccents', 'gpos_pair', (), [['mark', [['latn', ['dflt']]]]])
    font.addLookupSubtable('sideaccents', 'sacc')
    
    makedigraph(font, 'A', 'E', 'AE')  # U+00C6
    addanchor(font, 'AE')
    makedigraph(font, 'longs', 's', 'germandbls', -180)  # U+00DF
    makedigraph(font, 'a', 'e', 'ae')  # U+00E6
    addanchor(font, 'ae')
    makedigraph(font, 'i', 'j', 'ij')  # U+0133
    makedigraph(font, 'O', 'E', 'OE')  # U+0152
    makedigraph(font, 'o', 'e', 'oe')  # U+0153
    for i in range(0x00C0, 0x01FF+1):
        charto = fontforge.nameFromUnicode(i)
        if not font.__contains__(charto):
            makeaccented(font, charto)
    makedigraph(font, 'D', 'Zcaron', 'uni01C4')  # U+01C4
    makedigraph(font, 'D', 'zcaron', 'uni01C5')  # U+01C5
    makedigraph(font, 'd', 'zcaron', 'uni01C6')  # U+01C6
    makedigraph(font, 'D', 'Z', 'uni01F1')  # U+01F1
    makedigraph(font, 'D', 'z', 'uni01F2')  # U+01F2
    makedigraph(font, 'd', 'z', 'uni01F3')  # U+01F3
    
    font.__getitem__('L_L').addPosSub('sacc', 'uni0315', 0, 0, 0, 0, -80, 0, 0, 0)
    font.__getitem__('t_t').addPosSub('sacc', 'uni0315', 0, 0, 0, 0, -80, 0, 0, 0)


def charname(char):
    # Give the fontforge name for the given character.
    return fontforge.nameFromUnicode(ord(char))


def autokern(font):
    # Let fontforge do some magic and figure out automatic kerning for groups of glyphs.

    all_glyphs = [glyph.glyphname for glyph in font.glyphs()
                  if not glyph.glyphname.startswith(' ')]    

    #print('\n'.join(sorted(all_glyphs)))
    ligatures = [name for name in all_glyphs if len(name) < 8 and '_' in name]
    upper_ligatures = [ligature for ligature in ligatures if ligature.upper() == ligature]
    lower_ligatures = [ligature for ligature in ligatures if ligature.lower() == ligature]
    
    caps = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ') + upper_ligatures
    lower = list('abcdefghijklmnopqrstuvwxyz') + lower_ligatures
    all_chars = caps + lower
    
    accented = [name for name in all_glyphs if len(name) > 3 and name[1:] in ['grave', 'acute', 'circumflex', 'tilde', 'dieresis', 'ring', 'cedilla', 'macron', 'caron', 'hungarumlaut', 'dotaccent', 'breve', 'ogonek']]
    variants = [name for name in all_glyphs if len(name) > 3 and name[1] == '.' and name[2:] in ['sc', 'ss01']]
    lvbar = list('BDEFHIKLMNPRbhklmnr')
    lvbar = lvbar + [name for name in ligatures if name[0] in lvbar] + [name for name in accented if name[0] in lvbar] + [name for name in variants if name[0] in lvbar]
    lbowl = list('ACGOQUacdeoqyu')
    lbowl = lbowl + [name for name in ligatures if name[0] in lbowl] + [name for name in accented if name[0] in lbowl] + [name for name in variants if name[0] in lbowl]
    lcmplx = list('JSTVWXYZfgijpstvwxz')
    lcmplx = lcmplx + [name for name in ligatures if name[0] in lcmplx] + [name for name in accented if name[0] in lcmplx] + [name for name in variants if name[0] in lcmplx]
    rvbar = list('HIMNdhlmn')
    rvbar = rvbar + [name for name in ligatures if name[-1] in rvbar] + [name for name in accented if name[0] in rvbar] + [name for name in variants if name[0] in rvbar]
    rbowl = list('ABDOSUbgjopsuy')
    rbowl = rbowl + [name for name in ligatures if name[-1] in rbowl] + [name for name in accented if name[0] in rbowl] + [name for name in variants if name[0] in rbowl]
    rcmplx = list('CEFGJKLPQRTVWXYZacefikqrtvwxz')
    rcmplx = rcmplx + [name for name in ligatures if name[-1] in rcmplx] + [name for name in accented if name[0] in rcmplx] + [name for name in variants if name[0] in rcmplx]
    
    t = psMat.translate(0, -30)
    font.__getitem__('T').transform(t)
    font.__getitem__('T_T').transform(t)

    # Add a kerning lookup table.
    font.addLookup('kerning', 'gpos_pair', (), [['kern', [['latn', ['dflt']]]]])
    
    font.addKerningClass('kerning', 'kern0', [rvbar, rbowl, rcmplx], [[], lvbar, lbowl, lcmplx], [0, 0, -20, -30, 0, -20, -25, -30, 0, -30, -30, -30])
    font.addLookupSubtable('kerning', 'kern')
    
    # Everyone knows that two slashes together need kerning... (even if they didn't realise it)
    font.autoKern('kern', 150, [charname('/'), charname('\\')], [charname('/'), charname('\\')])

    # 
    font.__getitem__(charname('1')).addPosSub('kern', charname('1'), 80)
    
    #
    for char, kern in [('D', -60), ('F', -60), ('G', -60), ('J', -60), ('O', -60), ('P', -60), ('T', -60), ('V', -60), ('W', -60), ('Y', -60), ('T_T', -60), ('e', -60), ('f', -60), ('o', -60), ('p', -60), ('r', -60), ('v', -60)]:
        font.__getitem__(char).addPosSub('kern', charname(','), kern)
        font.__getitem__(char).addPosSub('kern', charname('.'), kern)
    for char, kern in [('U.ss01', -40), ('H.ss01', -80), ('I.ss01', -40), ('W.ss01', -80), ('Y.ss01', -80)]:
        font.__getitem__('T').addPosSub('kern', char, kern)
        font.__getitem__('T_T').addPosSub('kern', char, kern)
    
    # ascending order in 'separation.'
    font.autoKern('kern', 30, ['C'], all_chars, minKern=30)
    font.autoKern('kern', 60, ['r'], all_chars, minKern=30, onlyCloser=True)
    font.autoKern('kern', 80, ['R', 'C_R', 'E_R', 'R_R', 'X'], all_chars, minKern=30, onlyCloser=True)
    font.autoKern('kern', 80, all_chars, ['X', 'f', 't', 't_t'], minKern=30, onlyCloser=True)
    font.autoKern('kern', 90, all_chars, ['g'], minKern=30, onlyCloser=True)
    font.autoKern('kern', 90, ['V', 'v'], all_chars, minKern=30, onlyCloser=True)
    font.autoKern('kern', 100, ['K', 'k'], all_chars, minKern=30, onlyCloser=True)
    font.autoKern('kern', 120, all_chars, ['T', 'Y', 'Z'], minKern=30, onlyCloser=True)
    font.autoKern('kern', 120, ['Y', 'Z', 'P'], all_chars, minKern=30, onlyCloser=True)
    font.autoKern('kern', 130, ['J', 'T', 'f'], all_chars, minKern=30, onlyCloser=True)
    font.autoKern('kern', 130, all_chars, ['T_O', 'T_T'], minKern=30, onlyCloser=True)
    font.autoKern('kern', 140, ['r_r'], all_chars, minKern=30, onlyCloser=True)
    font.autoKern('kern', 150, ['F'], all_chars, minKern=30, onlyCloser=True)
    font.autoKern('kern', 180, all_chars, ['j'], minKern=30, onlyCloser=True)
    font.autoKern('kern', 200, ['T_T'], all_chars, minKern=30, onlyCloser=True)
    
    # minKern not affect when touch=True?
    font.autoKern('kern', 20, ['L', 'L_L', 'E', 'E_E'], all_chars, minKern=30, onlyCloser=True, touch=True)
    font.autoKern('kern', 110, ['L', 'L_L'], ['j', 'Y'], touch=True)
    font.autoKern('kern', 60, ['E', 'E_E'], ['V', 'v'], touch=True)
    font.autoKern('kern', 80, ['E', 'E_E'], ['j'], touch=True)
    font.autoKern('kern', 70, ['a', 'G'], ['t', 't_t'], touch=True)
    font.autoKern('kern', 30, ['i', 'r_i'], ['f', 't'], touch=True)
    font.autoKern('kern', 60, ['X', 'Z'], ['f', 't', 't_t'], touch=True)
    font.autoKern('kern', 60, ['r'], ['T', 'T_O', 'T_T', 'X', 'j'], touch=True)
    font.autoKern('kern', 100, ['r_r'], ['T', 'T_O', 'T_T', 'X', 'j'], touch=True)
    font.autoKern('kern', 60, ['P'], ['g'], touch=True)
    font.autoKern('kern', 40, ['C'], ['V', 'v'], touch=True)
    font.autoKern('kern', 140, ['T'], ['V', 'v'], touch=True)
    font.autoKern('kern', 40, ['V', 'v'], ['J'], touch=True)
    font.autoKern('kern', 150, ['F'], ['z'], touch=True)
    font.autoKern('kern', 30, ['r'], ['i'], touch=True)
    font.__getitem__('T_T').addPosSub('kern', 'O', -70)
    
    t = psMat.translate(0, 30)
    font.__getitem__('T').transform(t)
    font.__getitem__('T_T').transform(t)


for line, line_features in line_stats.items():
    print(line, mean(line_features['cap-height']) - mean(line_features['baseline']))

font = basic_font()
font.ascent = 600;

# Pick out particular glyphs that are more pleasant than their latter alternatives.
special_choices = {('C', ): dict(line=4),
                   ('G',): dict(line=4),
                   # Get rid of the "as" ligature - it's not very good.
                   ('a', 's'): dict(line=None),
                   # A nice tall I.
                   ('I', ): dict(line=4),
                   }

# Special case - add a vertial pipe by re-using an I, and stretching it a bit.
for line, position, bbox, fname, chars in characters:
    if chars == ('I',) and line == 4:
        characters.append([4, None, bbox, fname, ('|',)])
    if chars == ('-',):
        characters.append([line, None, bbox, fname, (u'‐',)])
    if chars == ('.',):
        characters.append([line, None, bbox, fname, (u'·',)])
    if chars == ('!',):
        characters.append([line, None, bbox, fname, (u'¡',)])
    if chars == ('?',):
        characters.append([line, None, bbox, fname, (u'¿',)])
    if chars == (u'≪',):
        characters.append([line, None, bbox, fname, (u'«',)])
    if chars == (u'≫',):
        characters.append([line, None, bbox, fname, (u'»',)])

for line, position, bbox, fname, chars in characters:
    if chars in special_choices:
        spec = special_choices[chars]
        spec_line = spec.get('line', any)
        if spec_line is not any and spec_line != line:
            continue
        
    c = create_char(font, chars, fname)
    c.comment = os.path.basename(fname)

    # Get the linestats for this character.
    line_features = line_stats[line]

    scale_glyph(
        c, bbox,
        baseline=mean(line_features['baseline']),
        cap_height=mean(line_features['cap-height']))
    
    translate_glyph(
        c, bbox,
        baseline=mean(line_features['baseline']),
        cap_height=mean(line_features['cap-height']))
    
    _, ymin, _, ymax = c.boundingBox()
    if line == 0:
        weight_glyph(c, 10)
    if chars == ('U', '.', 's', 's', '0', '1'):
        c.transform(psMat.scale(0.9))
        weight_glyph(c, 8)
    if chars == ('I', '.', 's', 'c'):
        c.transform(psMat.translate(0, -30))
    if chars == ('I', '.', 's', 's', '0', '1'):
        c.transform(psMat.translate(0, -40))
        rotate_glyph(c, -2)
    if chars == ('|',):
        c.transform(psMat.compose(psMat.scale(1, 1.3), psMat.translate(0, -100)))
    if chars == ('-',) or chars == (u'‐',):
        c.transform(psMat.scale(0.9, 1.0))
    if chars == (u'‐',):
        c.transform(psMat.translate(0, -70))
    if chars == (u'·',):
        c.transform(psMat.translate(0, 220))
    if chars == (u'«',) or chars == (u'»',):
        c.transform(psMat.scale(0.8, 1.0))
    if chars == (u'‘',):
        rotate_glyph(c, 15)
    if chars == (u'’',):
        rotate_glyph(c, -15)
    if chars == (u'¿',) or chars == (u'¡',):
        rotate_glyph(c)
        c.transform(psMat.translate(0, -120))
    if chars == (u'‽',):
        c.transform(psMat.translate(0, -30))

    # Simplify, then put the vertices on rounded coordinate positions.
    c.simplify(0.5, ['ignoreslopes', 'ignoreextrema', 'smoothcurves'])
    c.addExtrema('only_good_rm')
    c.round()
    c.simplify(0.5, ['ignoreslopes', 'ignoreextrema', 'smoothcurves'])
    c.addExtrema('only_good_rm')
    c.round()

c = font.createMappedChar(32)
c.width = 256

c = font.createChar(-1, 'W.ss01')
c.width = font.__getitem__('W').width
c.foreground = font.__getitem__('W').foreground.dup()
c.transform(psMat.translate(0, -20))
c = font.createChar(-1, 'Y.ss01')
c.foreground = font.__getitem__('Y').foreground.dup()
rotate_and_onto_baseline(c, 5)
c.transform(psMat.translate(0, -20))
font.__getitem__('U').addPosSub('ss01', 'U.ss01')
font.__getitem__('H').addPosSub('ss01', 'H.ss01')
font.__getitem__('I').addPosSub('ss01', 'I.ss01')
font.__getitem__('W').addPosSub('ss01', 'W.ss01')
font.__getitem__('Y').addPosSub('ss01', 'Y.ss01')
font.addContextualSubtable('contextual', 'calt', 'coverage', '[T] | [H I U W Y] @<subst_after_T> |')


makeaccent(font)
autokern(font)
font.os2_typoascent = 256
font.os2_typodescent = 0
font.os2_panose = (3, 0, 5, 2, 0, 0, 0, 0, 0, 0)
font.os2_codepages = (0x2000009F, 0)
font.private.guess('BlueValues')
font.private['BlueValues'] = font.private['BlueValues'][2:]
font_fname = '../font/xkcd-script.sfd'

if not os.path.exists(os.path.dirname(font_fname)):
    os.makedirs(os.path.dirname(font_fname))
if os.path.exists(font_fname):
    os.remove(font_fname)
font.save(font_fname)

font.close()
