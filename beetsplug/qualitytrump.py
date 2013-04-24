from beets.plugins import BeetsPlugin
from beets import ui, util
from beets import config

from beets.mediafile import MediaFile

from pprint import pprint

_TRUMP_FORMAT, _TRUMP_PRESET, _TRUMP_BITRATE = (0,1,2)
_DEFAULT_TRUMP_ORDER = (
    "FLAC", "V0", "320", "V2", "192", "MP3", "AAC"
)
TRUMP_WEIGHT = 4.0


# Source: hydrogenaudio.org's LAME article
mp3_br_ranges = {"320": (320, 320),
                 "v0": (220, 260),
                 "v2": (170, 210),
                 "bigv0": (220, 319)}
def guess_bitrate(abr):
    for bitrate, rng in mp3_br_ranges.iteritems():
        if abr >= rng[0] and abr <= rng[1]:
            return bitrate
    return "???"

def f():
    while True:
        item = yield
        print item

_CONSTANT_BITRATES = {320000: "320", 192000: "192"}

def get_canon_preset_name(preset):
    """ Get a canonical human readable name for LAME presets.
    Right now we just make, e.g., '-V0n', into 'V0', as is common
    notation among format enthusiasts.
    """

    if "-V" in preset:
        return "V%s"%preset[2+preset.index("-V")]
    return preset

def get_item_quality(item):
    preset = None
    if item.format == u'MP3':
        audio_file = MediaFile(item.path)
        preset = audio_file.mgfile.info.lame_preset
        if preset is None:
            # VBR preset is absent, try to use CBR as quality
            # Presently I'm not certain there's any way to assert that
            # the bitrate returned is ABR or an actual CBR
            if item.bitrate in _CONSTANT_BITRATES:
                preset = _CONSTANT_BITRATES[item.bitrate]
    return {"preset": preset,
            "bitrate": item.bitrate,
            "format": item.format}

def get_items_quality(items):
    formats = []
    bitrates = []
    presets = []
    for track in items:
        q = get_item_quality(track)
        presets.append(q["preset"])
        formats.append(q["format"])
        bitrates.append(q["bitrate"])
    return {"bitrate": sum(bitrates)/len(bitrates),
            "format": (formats[0] if formats.count(formats[0]) == len(formats)
                       else "Mutt"),
            "preset": (presets[0] if presets.count(presets[0]) == len(presets)
                       else "Mutt")}

def get_album_quality(album):
    return get_items_quality(album.items())

fmt_cmd = ui.Subcommand('fmt', help="do some format nonsense")
def fmt(lib, opts, args):
    threads = 3
    ui.commands.list_items(lib, ui.decargs(args), opts.album, None)
    if opts.album:
        albums = lib.albums(ui.decargs(args))
    else:
        albums = []
        items = lib.items(ui.decargs(args))

    # Try to determine the quality of the album
    if albums:
        for album in albums:
            print album.album
            print get_album_quality(album)
            print _tmpl_quality(album.items().next())
    elif items:
        for item in items:
            print item.title
            print get_item_quality(item)
            print _tmpl_quality(item)

fmt_cmd.func = fmt
fmt_cmd.parser.add_option("-a", "--album", action="store_true", help="poop")

class QualityTrumper(BeetsPlugin):
    def __init__(self):
        super(QualityTrumper, self).__init__()

    def commands(self):
        return [fmt_cmd]

    def track_score(self, item):
        return (0.0, 0.0)

    def album_score(self, items):
        return score_quality(get_items_quality(items))

    def duplicates(self, items):
        return []

    def item_duplicates(self, item):
        return []

@QualityTrumper.template_field('quality')
def _tmpl_quality(item):
    """Expand to the encode quality of the track. Anything but MP3s
    will expand to their media type (e.g. FLAC, AAC), or Mutt if they
    are a combination of multiple formats. MP3s will expand to 'MP3
    $preset', where $preset is the LAME preset, Mutt if the album
    consists of multiple presets, or None if the album has no preset
    data.
    """
    if item.album:
        q = get_item_quality(item)
    else:
        q = get_item_quality(item)

    if q["format"] == u'MP3':
        return u"MP3 %s"%("None" if not q["preset"] else q["preset"])
    else:
        return u"None" if not q["format"] else q["format"]

def score_quality(quality):
    # Calculate preset score
    preset = quality["preset"]
    fmt = quality["format"]
    order = _DEFAULT_TRUMP_ORDER

    # Try to calculate preset score
    if preset is not None and preset.upper() in order:
        preset_score = order.index(preset.upper())
    else:
        preset_score = len(order)
    # Calculate format score
    if fmt is not None and fmt.upper() in order:
        format_score = order.index(fmt.upper())
    else:
        format_score = len(order)

    print preset_score, format_score
    return len(order) - min(preset_score, format_score), len(order)

def comp_quality(qual1, qual2):
    """ Take two qualities (a dict {format, preset, bitrate}) and
    compare them.
    """

    return score_quality(qual2) - score_quality(qual1)

@QualityTrumper.listen('import_task_duplicate')
def _trump_by_quality(session, task):

    dupeinfo = get_album_quality(task.duplicates[0])
    newinfo = get_items_quality(task.items)
    print config["qualitytrump"]["order"].get()
    print comp_quality(dupeinfo, newinfo)