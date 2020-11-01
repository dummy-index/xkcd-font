# -*- coding: utf-8 -*-
from __future__ import division
import fontforge
import os
import glob
import parse
import base64

def len_ucs(ustr):
    len(ustr.encode('utf-32')) // 4


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

    font.version = '1.0';
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

    font.addLookup('anchors', 'gpos_mark2base', (), [['mark',
                                                      [['latn',
                                                        ['dflt']]]]])
    font.addLookupSubtable('anchors', 'dtop')
    font.addAnchorClass('dtop', 'top')

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


baseline_chars = ['a' 'e', 'm', 'A', 'E', 'M', '&', '@', '.', u'≪', u'É']
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


large_arm_chars = ['C', 'F', 'J', 'T', 'T_T', 'f', 'r', 'five']
large_tail_chars = ['g', 'j', 'y']

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
    if c.glyphname in large_arm_chars:
        c.width = scaled_width
    else:
        c.width = scaled_width + 2 * space
    if c.glyphname in large_tail_chars:
        t = psMat.translate(-space, 0)
    else:
        t = psMat.translate(space, 0)
    c.transform(t)


def weight_glyph(c, stroke_width):
    # Dilate the glyph with bottom keeping.

    c.simplify(0.5, ['smoothcurves'])
    c.changeWeight(stroke_width, 'CJK')
    t = psMat.translate(stroke_width / 2, stroke_width / 2)
    c.transform(t)
    c.width = c.width + stroke_width / 2


def rotate_glyph(c):
    import_bbox = c.boundingBox()
    
    t = psMat.translate(-(import_bbox[0] + import_bbox[2]) / 2, -(import_bbox[1] + import_bbox[3]) / 2)
    c.transform(psMat.compose(psMat.compose(t, psMat.scale(-1)), psMat.inverse(t)))


def addanchor(font, char):
    c = font.__getitem__(char)
    xmin, _, xmax, ymax = c.boundingBox()
    c.addAnchorPoint('top', 'base', (xmin + xmax) / 2, ymax)


def getaccent(cfrom, cto):
    cto.width = cfrom.width
    lfrom = cfrom.foreground
    lto = cto.foreground
    xmin, _, xmax, _ = cfrom.boundingBox()
    ytop = 0
    i = 0
    while i < len(lfrom):
        _, _, _, ymax = lfrom[i].boundingBox()
        if ymax >= 540:
            lto += lfrom[i]
        else:
            if ymax > ytop:
                ytop = ymax
        i = i + 1
    cto.layers[1] = lto
    cto.addAnchorPoint('top', 'mark', (xmin + xmax) / 2, ytop)

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
    
    lvbar = list('BDEFHIKLMNPRbhklmnr')
    lvbar = lvbar + [name for name in ligatures if name[0] in lvbar]
    lbowl = list('ACGOQUacdeoqyu')
    lbowl = lbowl + [name for name in ligatures if name[0] in lbowl]
    lcmplx = list('JSTVWXYZfgijpstvwxz')
    lcmplx = lcmplx + [name for name in ligatures if name[0] in lcmplx]
    rvbar = list('HIMNdhlmn')
    rvbar = rvbar + [name for name in ligatures if name[-1] in rvbar]
    rbowl = list('ABDOSUbgjopsuy')
    rbowl = rbowl + [name for name in ligatures if name[-1] in rbowl]
    rcmplx = list('CEFGJKLPQRTVWXYZacefikqrtvwxz')
    rcmplx = rcmplx + [name for name in ligatures if name[-1] in rcmplx]
    
    t = psMat.translate(0, -30)
    font.__getitem__('T').transform(t)
    font.__getitem__('T_T').transform(t)

    # Add a kerning lookup table.
    font.addLookup('kerning', 'gpos_pair', (), [['kern', [['latn', ['dflt']]]]])
    
    font.addKerningClass('kerning', 'kern0', [rvbar, rbowl, rcmplx], [[], lvbar, lbowl, lcmplx], [0, 0, -20, -30, 0, -20, -20, -30, 0, -30, -30, -30])
    font.addLookupSubtable('kerning', 'kern')
    
    # Everyone knows that two slashes together need kerning... (even if they didn't realise it)
    font.autoKern('kern', 150, [charname('/'), charname('\\')], [charname('/'), charname('\\')])

    # 
    font.__getitem__(charname('1')).addPosSub('kern', charname('1'), 160)
    
    # ascending order in 'separation.'
    font.autoKern('kern', 30, ['C'], all_chars, minKern=30)
    font.autoKern('kern', 60, ['r'], lower, minKern=30, onlyCloser=True)
    font.autoKern('kern', 80, all_chars, ['g'], minKern=30)
    font.autoKern('kern', 100, ['V', 'K', 'k'], all_chars, minKern=30, onlyCloser=True)
    font.autoKern('kern', 120, all_chars, ['T', 'T_O', 'T_T', 'Y'], minKern=30, onlyCloser=True)
    font.autoKern('kern', 120, ['Y', 'f'], all_chars, minKern=30, onlyCloser=True)
    font.autoKern('kern', 130, ['J'], all_chars, minKern=30, onlyCloser=True)
    font.autoKern('kern', 150, ['T', 'F'], all_chars, minKern=30, onlyCloser=True)
    font.autoKern('kern', 180, all_chars, ['j'], minKern=30, onlyCloser=True)
    font.autoKern('kern', 200, ['T_T'], all_chars, minKern=30, onlyCloser=True)
    
    # minKern not affect when touch=True?
    #font.autoKern('kern', 30, all_chars, ['f', 't', 't_t'], minKern=30, onlyCloser=True, touch=True)
    #font.autoKern('kern', 60, ['r_r'], lower, minKern=30, onlyCloser=True, touch=True)
    font.autoKern('kern', 30, [char for char in all_chars if char not in ['r', 'r_r']], ['f', 't', 't_t'], minKern=30, onlyCloser=True, touch=True)
    font.autoKern('kern', 60, ['r_r'], [char for char in lower if char not in lvbar + ['f', 't', 't_t', 'p', 's', 'u', 'y']], minKern=30, onlyCloser=True, touch=True)
    font.autoKern('kern', 60, ['a', 'G'], ['t', 't_t'], touch=True)
    font.autoKern('kern', 60, ['C'], ['V', 'v'], touch=True)
    font.autoKern('kern', 150, ['F'], ['z'], touch=True)
    font.autoKern('kern', 0, ['T_T'], ['T_T', 'T'], touch=True)
    
    t = psMat.translate(0, 30)
    font.__getitem__('T').transform(t)
    font.__getitem__('T_T').transform(t)


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
    if chars == ('!',):
        characters.append([line, None, bbox, fname, (u'¡',)])
    if chars == ('?',):
        characters.append([line, None, bbox, fname, (u'¿',)])

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
    
    if line == 0:
        weight_glyph(c, 10)
    if chars == ('|',):
        c.transform(psMat.compose(psMat.scale(1, 1.3), psMat.translate(0, -100)))
    if chars == ('-',) or chars == (u'‐',):
        c.transform(psMat.scale(0.9, 1.0))
    if chars == (u'‐',):
        c.transform(psMat.translate(0, -70))
    if chars == (u'’',) or chars == (u'‘',):
        rotate_glyph(c)
    if chars == (u'¿',) or chars == (u'¡',):
        rotate_glyph(c)
        c.transform(psMat.translate(0, -120))

    # Simplify, then put the vertices on rounded coordinate positions.
    c.simplify()
    c.round()

c = font.createMappedChar(32)
c.width = 256
getaccent(font.createMappedChar('Ograve'), font.createMappedChar('grave'))
c = font.createMappedChar(0x00C0)
addanchor(font, 'A')
addanchor(font, 'E')
c.addReference('A')
c.appendAccent('grave')
c = font.createMappedChar(0x00C8)
c.addReference('E')
c.appendAccent('grave')
autokern(font)
font_fname = '../font/xkcd-script.sfd'

if not os.path.exists(os.path.dirname(font_fname)):
    os.makedirs(os.path.dirname(font_fname))
if os.path.exists(font_fname):
    os.remove(font_fname)
#font.generate(font_fname) => GSUB/GPOS don't saved
#font.generate(font_fname, flags=['opentype']) => arbitrarily [Populate]d
font.save(font_fname)

font.close()
